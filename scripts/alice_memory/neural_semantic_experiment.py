"""Finite integration audit against the already measured retention curriculum.

Raw top-1 and supported hypotheses are separate metrics. Exact cue support is
deliberately conservative: the unseen appraisal combinations must abstain.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from pathlib import Path

import torch

from .adaptive_memory import recalled_pair
from .adaptive_memory_experiment import assessment, curriculum, make_queries
from .consolidating_mind import ConsolidatingMind, load, save
from .continuous_mind import ContinuousMind
from .episodic_experiment import packets
from .episodic_session import EpisodicSession
from .experience_signals import samples
from .grounded_mind import load as load_grounded
from .memory_actor import MemoryActor
from .paged_memory import PagedMemory
from .process_metrics import Budget, memory_usage
from .temporal_mind import TemporalMind


def supported_assessment(model, queries):
    answers = []
    for query in queries:
        cue = torch.zeros(4, 4, dtype=torch.float64)
        cue[[0, 1, 3]] = query["key"].reshape(3, 4)
        answers.append(model.predict(cue.flatten()))
    return {"supported": sum(answer["supported"] for answer in answers), "total": len(answers),
            "reasons": sorted(set(answer["reason"] for answer in answers))}


def observed_support(agent):
    """Evaluate taught keys against source weights; targets are evaluator-only."""
    model, memory = agent.semantic, agent.mind.actor.session.memory
    supported, correct, reasons = 0, 0, {}
    for episode in model.index.episodes[:int(model.index.count)].tolist():
        pair = recalled_pair(memory, episode, agent.clock, model.target)
        if pair is None:
            raise ValueError("Saved representative no longer recalls its source.")
        fields = [field for field in range(4) if field != model.target]
        cue = torch.zeros(4, 4, dtype=torch.float64)
        cue[fields] = pair["key"].reshape(3, 4)
        answer = model.predict(cue.flatten())
        supported += answer["supported"]
        correct += answer["supported"] and int(torch.tensor(answer["distribution"]).argmax()) == int(pair["value"].argmax())
        reasons[answer["reason"]] = reasons.get(answer["reason"], 0) + 1
    return {"supported": supported, "correct_when_supported": correct, "total": int(model.index.count),
            "reasons": reasons, "scope": "Observed representative cues recalled from episodic weights; not novel raw sensory queries."}


def run(checkpoint, baseline, output, seed=17, seconds=180.):
    budget = Budget(100000, seconds)
    torch.set_num_threads(1)
    started = time.perf_counter()
    source_hash = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    reference_hash = hashlib.sha256((baseline / "report.json").read_bytes()).hexdigest()
    template = load_grounded(checkpoint)
    old = template.mind.actor.session
    perception, boundary, policy = old.perception, old.boundary, template.mind.actor.policy
    core = template.temporal.core
    if isinstance(old.memory, PagedMemory):
        old.memory.close()
    output.mkdir(parents=True, exist_ok=False)
    memory = PagedMemory(321, hot_limit=4)
    resumed = None
    try:
        session = EpisodicSession(perception, boundary, memory)
        continuous = ContinuousMind(MemoryActor(session, policy))
        temporal = TemporalMind(continuous, core, perception.state_dict())
        agent = ConsolidatingMind(temporal, semantic_backend="neural", seed=seed + 793000)
        # Match both independent initialization streams of stability-v1.
        agent.semantic.index.generator.manual_seed(seed + 843000)
        rng = random.Random(seed + 803000)
        mapping = list(range(4))
        rng.shuffle(mapping)
        queries, encoded = make_queries(session, mapping, seed)
        phases = curriculum(seed, mapping, 8)
        records, scores, stream, reactivations = [], [], hashlib.sha256(), 0
        for phase, visits in enumerate(phases):
            for truth in visits:
                budget.check(len(records))
                count = len(memory.blocks)
                for frame in range(2):
                    dt = 3. if frame == 0 else .1
                    image, audio = samples(truth, rng)
                    agent.perceive(packets(image, audio, agent.clock + dt, session.steps * 2), dt)
                if len(memory.blocks) != count + 1:
                    raise ValueError("Integration curriculum did not create exactly one episode per visit.")
                episode = len(memory.blocks) - 1
                pair = recalled_pair(memory, episode, agent.clock)
                if pair is None:
                    raise ValueError("Unsupported integrated training source.")
                stream.update(json.dumps([pair["key"].tolist(), pair["value"].tolist()]).encode())
                learned = agent.consolidate_current()
                if not learned["learned"]:
                    raise ValueError("Integrated neural source was not consolidated.")
                reactivations += len(learned["reactivated"])
                records.append((episode, truth))
                if agent.clock != session.clock or agent.clock != agent.temporal.clock:
                    raise ValueError("Integrated source/temporal clocks diverged.")
            new = (0, 1) if phase == 0 else ((2, 3) if phase == 1 else (1,))
            old_contexts = (0,) if phase == 0 else ((0, 1) if phase == 1 else (0, 2, 3))
            scores.append({"new": assessment(agent.semantic.bank, queries, new, phase == 2),
                           "old_unchanged": assessment(agent.semantic.bank, queries, old_contexts),
                           "held_out_support": supported_assessment(agent.semantic, queries)})
        budget.check(len(records))
        facts = 0
        for episode, truth in records:
            budget.check(len(records) + episode)
            pair = recalled_pair(memory, episode, agent.clock)
            facts += pair is not None and pair["value"].argmax().item() == truth[2]
        reference = json.loads((baseline / "report.json").read_text(encoding="utf-8"))
        old_kernel = torch.load(baseline / "candidate-model.pt", map_location="cpu", weights_only=True)
        old_index = torch.load(baseline / "candidate-index.pt", map_location="cpu", weights_only=True)
        kernel_equal = all(torch.equal(value, agent.semantic.bank.state_dict()[name]) for name, value in old_kernel["state"].items())
        index_equal = all(torch.equal(value, agent.semantic.index.state_dict()[name]) for name, value in old_index["state"].items()) and torch.equal(old_index["generator"], agent.semantic.index.generator.get_state())
        save(output / "mind.pt", agent)
        resumed = load(output / "mind.pt")
        continuation_equal = agent.tick(.1) == resumed.tick(.1) and torch.equal(agent.temporal.hidden, resumed.temporal.hidden)
        writes = int(agent.semantic.bank.writes)
        duplicate = agent.consolidate_current()
        duplicate_equal = not duplicate["learned"] and int(agent.semantic.bank.writes) == writes
        read_before = [agent.semantic.bank.read(query["key"]) for query in queries]
        agent.semantic.bank.clear_working_context()
        independent = all(torch.equal(value, agent.semantic.bank.read(query["key"])) for value, query in zip(read_before, queries))
        budget.check(len(records) + facts)
        matched = stream.hexdigest() == reference["recalled_training_stream_sha256"]
        report = {"format": "neural-semantic-integration-v1", "seed": seed, "completed": True,
                  "visits": len(records), "frames": agent.temporal.observations,
                  "session_steps_after_idle": session.steps, "phases": scores,
                  "episodic_facts_correct": facts, "query_keys_correct": encoded,
                  "matches_baseline_stream": matched, "kernel_matches_baseline": kernel_equal,
                  "index_and_sampler_match_baseline": index_equal, "next_tick_equal": continuation_equal,
                  "duplicate_does_not_retrain": duplicate_equal, "read_independent_of_working_context": independent,
                  "reactivations": reactivations, "writes": writes,
                  "source_sha256": source_hash, "baseline_report_sha256": reference_hash,
                  "source_unchanged": source_hash == hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                  "recalled_training_stream_sha256": stream.hexdigest(),
                  "pending_sources": agent.semantic.pending_sources(),
                  "same_source_owner": agent.semantic._source() is session.memory,
                  "observed_support": observed_support(agent),
                  "semantic_tensor_bytes": sum(value.numel() * value.element_size() for value in agent.semantic.state_dict().values()),
                  "elapsed_seconds": time.perf_counter() - started, "memory": memory_usage(),
                  "scope": "Integration fidelity only. Conservative full-cue support excludes held-out appraisal combinations; top-1 accuracy does not imply supported or calibrated hypotheses. Numerical continuation uses one CPU thread. Personality and natural-language generation not evaluated."}
        report["integration_passed"] = all((matched, kernel_equal, index_equal, continuation_equal, duplicate_equal,
                                             independent, facts == 320, encoded == 32, report["source_unchanged"],
                                             report["same_source_owner"], not report["pending_sources"]))
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report
    finally:
        if resumed is not None:
            resumed.mind.actor.session.memory.close()
        memory.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--max-seconds", type=float, default=180.)
    args = parser.parse_args()
    result = run(args.checkpoint, args.baseline, args.output, args.seed, args.max_seconds)
    print(json.dumps({name: result[name] for name in ("seed", "integration_passed", "elapsed_seconds")}))


if __name__ == "__main__":
    main()
