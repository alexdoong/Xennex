"""Reserved sensory queries and exact coupled continuation of neural-v2."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
import time
from pathlib import Path

import torch

from .adaptive_memory import recalled_pair
from .adaptive_memory_experiment import make_queries
from .consolidating_mind import load, save
from .episodic_experiment import packets
from .experience_signals import samples
from .projected_semantic_memory import restore as restore_projected
from .process_metrics import Budget, memory_usage
from .scene_mind_experiment import tensor_tree_equal
from .support_projection import SupportProjection


def attach_projection(agent):
    old = agent.semantic
    projection = SupportProjection()
    projection.fit(old.bank, old.index)
    payload = {**old.snapshot(), "architecture": "neural-v2", "projection": projection.snapshot()}
    agent.semantic = restore_projected(payload, agent.mind.actor.session.memory)
    return all(torch.equal(value, agent.semantic.bank.state_dict()[name]) for name, value in old.bank.state_dict().items())


def continue_visit(agent, seed):
    rng, mapping = random.Random(seed + 803000), list(range(4))
    rng.shuffle(mapping)
    rng = random.Random(seed + 903000)
    # A known rule, fresh sensory draw; no evaluator targets enter consolidation.
    for frame in range(2):
        dt = 3. if frame == 0 else .1
        image, audio = samples((0, 0, mapping[0], 0), rng)
        session = agent.mind.actor.session
        agent.perceive(packets(image, audio, agent.clock + dt, session.steps * 2), dt)
    agent.consolidate_current()
    agent.tick(.1)


def run(checkpoint, output, seed, seconds=120.):
    torch.set_num_threads(1)
    budget, started = Budget(100000, seconds), time.perf_counter()
    output.mkdir(parents=True, exist_ok=False)
    source_hash = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    agent, resumed = load(checkpoint), None
    try:
        session = agent.mind.actor.session
        unchanged = attach_projection(agent)
        rng, mapping = random.Random(seed + 803000), list(range(4))
        rng.shuffle(mapping)
        queries, encoded = make_queries(session, mapping, seed)
        old_correct = supported = correct = 0
        observations = []
        before = agent.semantic.transaction_state()
        for query in queries:
            budget.check(len(observations))
            cue = torch.zeros(4, 4, dtype=torch.float64)
            cue[[0, 1, 3]] = query["key"].reshape(3, 4)
            result = agent.semantic.predict(cue.flatten())
            expected = query["revised"]  # Final source curriculum revised context 1.
            old_correct += int(agent.semantic.bank.read(query["key"]).argmax()) == expected
            supported += result["supported"]
            correct += result["supported"] and int(torch.tensor(result["distribution"]).argmax()) == expected
            observations.append({"expected": expected, "result": result})
        read_only = all(torch.equal(value, agent.semantic.state_dict()[name]) for name, value in before[0].items()) and torch.equal(before[1], agent.semantic.index.generator.get_state())
        facts, stream = 0, hashlib.sha256()
        for episode in range(len(session.memory.blocks)):
            budget.check(len(queries) + episode)
            pair = recalled_pair(session.memory, episode, agent.clock)
            if pair is None:
                raise ValueError("Source weights became unreadable after projection.")
            facts += 1
            stream.update(json.dumps([pair["key"].tolist(), pair["value"].tolist()]).encode())
        save(output / "mind.pt", agent)
        continue_visit(agent, seed)
        save(output / "expected.pt", agent)
        session.memory.close()
        command = [sys.executable, "-m", "scripts.alice_memory.projected_semantic_experiment", "--resume",
                   str(output / "mind.pt"), "--output", str(output / "resumed.pt"), "--seed", str(seed)]
        remaining = seconds - (time.perf_counter() - budget.started)
        if remaining <= 0:
            raise TimeoutError("Projected semantic experiment budget exhausted before resume.")
        child = subprocess.run(command, capture_output=True, text=True, timeout=min(60., remaining))
        if child.returncode:
            raise RuntimeError("Projected semantic child failed: " + child.stderr[-2000:])
        same = tensor_tree_equal(torch.load(output / "expected.pt", weights_only=True),
                                 torch.load(output / "resumed.pt", weights_only=True))
        prior = json.loads((checkpoint.parent / "report.json").read_text(encoding="utf-8"))
        budget.check(1000)
        report = {"format": "projected-semantic-v1", "seed": seed, "completed": True,
                  "supported": supported, "correct": correct, "total": len(queries), "raw_kernel_correct": old_correct,
                  "source_facts_readable": facts, "source_stream_equal": stream.hexdigest() == prior["recalled_training_stream_sha256"],
                  "kernel_unchanged_by_attachment": unchanged, "prediction_read_only": read_only,
                  "fresh_process_complete_state_equal": same, "query_keys_correct": encoded,
                  "projection": {name: value.tolist() for name, value in before[0].items() if name.startswith("projection.")},
                  "source_sha256": source_hash, "source_unchanged": source_hash == hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                  "queries": observations, "elapsed_seconds": time.perf_counter() - started, "memory": memory_usage(),
                  "scope": "Reserved raw sensory inputs encoded by the existing perceptual model. Only unseen values of an empirically low-influence field are projected; retained combinations must have two intact routing witnesses. Output uses neural function, no witness targets. Heuristic support is not calibrated confidence or causal independence. One CPU thread in parent/child."}
        report["passed"] = all((supported / len(queries) >= .9, correct / len(queries) >= .9,
                                 report["source_stream_equal"], unchanged, read_only, same, encoded == 32,
                                 facts == 320, report["source_unchanged"]))
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report
    finally:
        # The memory may already be closed after exporting the full checkpoint.
        agent.mind.actor.session.memory.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()
    if (args.checkpoint is None) == (args.resume is None):
        parser.error("Provide checkpoint or resume, exclusively.")
    torch.set_num_threads(1)
    if args.resume:
        agent = load(args.resume)
        try:
            continue_visit(agent, args.seed)
            save(args.output, agent)
        finally:
            agent.mind.actor.session.memory.close()
        return
    report = run(args.checkpoint, args.output, args.seed)
    print(json.dumps({name: report[name] for name in ("seed", "passed", "supported", "correct", "total", "elapsed_seconds")}))


if __name__ == "__main__":
    main()
