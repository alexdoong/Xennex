"""Causal retention/plasticity comparison with bounded neural reactivation."""
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

from .adaptive_memory import AdaptiveMemory, recalled_pair, restore as restore_adaptive
from .adaptive_memory_experiment import assessment, curriculum, make_queries
from .episodic_experiment import packets
from .episodic_session import EpisodicSession, load as load_source, save as save_source
from .experience_signals import samples
from .grounded_mind import load as load_grounded
from .loop_checkpoint import atomic_write
from .neural_consolidation import consolidation_cycle
from .paged_memory import PagedMemory
from .process_metrics import Budget, memory_usage, quantiles
from .protected_memory import ProtectedMemory, restore as restore_protected
from .reactivation_index import ReactivationIndex, restore as restore_index


CONFIGURATIONS = {
    "baseline8": (dict(inner_steps=8), None, 0, "representatives"),
    "baseline16": (dict(inner_steps=16), None, 0, "representatives"),
    "baseline32": (dict(inner_steps=32), None, 0, "representatives"),
    "protected8": (dict(inner_steps=8), dict(stability=8.), 0, "representatives"),
    "protected64": (dict(inner_steps=8), dict(stability=64.), 0, "representatives"),
    "representatives1": (dict(inner_steps=8), None, 1, "representatives"),
    "representatives3": (dict(inner_steps=8), None, 3, "representatives"),
    "history3": (dict(inner_steps=8), None, 3, "history"),
    "protected_representatives3": (dict(inner_steps=8), dict(stability=8.), 3, "representatives"),
}


def restore_model(payload):
    return restore_protected(payload) if payload.get("format") == 37 else restore_adaptive(payload)


def consolidate(model, index, memory, episode, replay_limit=3, policy="representatives"):
    return consolidation_cycle(model, index, memory, episode, replay_limit, policy)["reactivated"]


def resume_child(source_path, model_path, index_path, output):
    source = load_source(source_path)
    try:
        model = restore_model(torch.load(model_path, map_location="cpu", weights_only=True))
        index = restore_index(torch.load(index_path, map_location="cpu", weights_only=True), source.memory)
        selected = consolidate(model, index, source.memory, len(source.memory.blocks) - 1)
        atomic_write(output / "resumed-model.pt", model.snapshot())
        atomic_write(output / "resumed-index.pt", index.snapshot())
        (output / "resumed-selection.json").write_text(json.dumps(selected), encoding="utf-8")
    finally:
        source.memory.close()


def fresh_process_check(session, model, index, output, timeout=60.):
    save_source(output / "source.pt", session)
    atomic_write(output / "candidate-model.pt", model.snapshot())
    atomic_write(output / "candidate-index.pt", index.snapshot())
    uninterrupted = restore_model(model.snapshot())
    routes = restore_index(index.snapshot(), session.memory)
    selected = consolidate(uninterrupted, routes, session.memory, len(session.memory.blocks) - 1)
    # The subprocess must reconstruct source weights from the checkpoint, without
    # access to the original page database, not just reload a cached target vector.
    session.memory.close()
    command = [sys.executable, "-m", "scripts.alice_memory.stability_experiment", "--resume-source",
               str(output / "source.pt"), "--resume-model", str(output / "candidate-model.pt"),
               "--resume-index", str(output / "candidate-index.pt"), "--output", str(output)]
    subprocess.run(command, check=True, capture_output=True, timeout=timeout, cwd=Path(__file__).resolve().parents[2])
    resumed = restore_model(torch.load(output / "resumed-model.pt", map_location="cpu", weights_only=True))
    resumed_index = torch.load(output / "resumed-index.pt", map_location="cpu", weights_only=True)
    selected_again = json.loads((output / "resumed-selection.json").read_text(encoding="utf-8"))
    return (selected == selected_again and
            all(torch.equal(value, resumed.state_dict()[name]) for name, value in uninterrupted.state_dict().items()) and
            all(torch.equal(value, resumed_index["state"][name]) for name, value in routes.state_dict().items()) and
            torch.equal(routes.generator.get_state(), resumed_index["generator"]))


def run(checkpoint, output, seed=17, seconds=240.):
    torch.set_num_threads(1)
    budget = Budget(100000, seconds)
    started = time.perf_counter()
    source_hash = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    template = load_grounded(checkpoint)
    base = template.mind.actor.session
    perception, boundary = base.perception, base.boundary
    if isinstance(base.memory, PagedMemory):
        base.memory.close()
    output.mkdir(parents=True, exist_ok=False)
    rng = random.Random(seed + 803000)
    mapping = list(range(4))
    rng.shuffle(mapping)
    phases = curriculum(seed, mapping, 8)
    memory = PagedMemory(321, hot_limit=4)
    try:
        session = EpisodicSession(perception, boundary, memory)
        queries, encoded_correct = make_queries(session, mapping, seed)
        models, indexes = {}, {}
        results = {}
        for name, (config, protection, replays, _) in CONFIGURATIONS.items():
            with torch.random.fork_rng(devices=[]):
                torch.manual_seed(seed + 793000)
                options = dict(window=16, **config)
                models[name] = AdaptiveMemory(**options) if protection is None else ProtectedMemory(**protection, **options)
            if replays:
                indexes[name] = ReactivationIndex(memory.capacity, capacity=128, seed=seed + 843000)
            results[name] = {"phases": [], "latencies": [], "recalled_past_pairs": 0,
                             "attempted_past_reads": 0, "skipped_past_reads": 0, "consolidation_source_reads": 0}
        sources, source_failures = [], []
        source_keys_correct, completed = 0, 0
        stream_digest = hashlib.sha256()
        sensory_seconds = 0.
        for phase, records in enumerate(phases):
            for truth in records:
                budget.check(completed)
                sensory_started = time.perf_counter()
                count = len(memory.blocks)
                for frame in range(2):
                    elapsed = 3. if frame == 0 else .1
                    image, sound = samples(truth, rng)
                    observation = session.step(packets(image, sound, session.clock + elapsed, session.steps * 2), elapsed)
                sensory_seconds += time.perf_counter() - sensory_started
                episode = observation["episode"]
                if episode is None or len(memory.blocks) != count + 1:
                    raise ValueError("The curriculum did not create one causal visit.")
                pair = recalled_pair(memory, episode, memory.clock)
                sources.append((episode, truth))
                if pair is None:
                    source_failures.append(episode)
                    continue
                source_keys_correct += all(pair["key"].reshape(3, 4)[group].argmax().item() == truth[field]
                                           for group, field in enumerate((0, 1, 3)))
                stream_digest.update(json.dumps([pair["key"].tolist(), pair["value"].tolist()]).encode())
                for name, model in models.items():
                    budget.check(completed)
                    before = time.perf_counter()
                    selection = consolidation_cycle(model, indexes.get(name), memory, episode,
                                                     CONFIGURATIONS[name][2], CONFIGURATIONS[name][3])
                    results[name]["attempted_past_reads"] += selection["attempted"]
                    results[name]["skipped_past_reads"] += len(selection["skipped"])
                    results[name]["consolidation_source_reads"] += selection["source_reads"]
                    results[name]["recalled_past_pairs"] += len(selection["reactivated"])
                    completed += 1 + len(selection["reactivated"])
                    results[name]["latencies"].append(time.perf_counter() - before)
            contexts = (0, 1) if phase == 0 else ((2, 3) if phase == 1 else (1,))
            old = (0,) if phase == 0 else ((0, 1) if phase == 1 else (0, 2, 3))
            for name, model in models.items():
                results[name]["phases"].append({"new": assessment(model, queries, contexts, revised=phase == 2),
                                                "old_unchanged": assessment(model, queries, old)})
        facts = 0
        for episode, truth in sources:
            recalled = recalled_pair(memory, episode, memory.clock)
            facts += recalled is not None and recalled["value"].argmax().item() == truth[2]
        continued, cleared = True, True
        for name, model in models.items():
            budget.check(completed)
            entry = results[name]
            latencies = entry.pop("latencies")
            entry.update(model.metrics())
            entry["consolidation_seconds"] = sum(latencies)
            entry["consolidation_latency_seconds"] = quantiles(latencies)
            entry["gradient_steps"] = int(model.writes) * model.config["inner_steps"]
            entry["source_index"] = indexes[name].metrics() if name in indexes else None
            atomic_write(output / (name + ".pt"), model.snapshot())
            resumed = restore_model(torch.load(output / (name + ".pt"), map_location="cpu", weights_only=True))
            uninterrupted = restore_model(model.snapshot())
            for candidate in (resumed, uninterrupted):
                candidate.write(pair["key"], pair["value"], memory.clock)
            equal = all(torch.equal(value, resumed.state_dict()[key]) for key, value in uninterrupted.state_dict().items())
            entry["next_write_equal"] = equal
            continued &= equal
            predictions = [resumed.read(query["key"]) for query in queries]
            resumed.clear_working_context()
            unchanged = all(torch.equal(prediction, resumed.read(query["key"])) for prediction, query in zip(predictions, queries))
            entry["clear_working_context_preserves_reads"] = unchanged
            cleared &= unchanged
        budget.check(completed)
        remaining = min(60., budget.seconds - (time.perf_counter() - budget.started))
        fresh_equal = fresh_process_check(session, models["representatives3"], indexes["representatives3"], output, remaining)
        budget.check(completed)
        for name, entry in results.items():
            entry["retention_plasticity_passed"] = all(stage["new"]["top1_accuracy"] >= .9 and stage["old_unchanged"]["top1_accuracy"] >= .9
                                                         for stage in entry["phases"])
        previous = output.parent / f"adaptive-memory-v1-seed{seed}" / "report.json"
        previous_report = json.loads(previous.read_text(encoding="utf-8"))
        matched_stream = stream_digest.hexdigest() == previous_report["recalled_training_stream_sha256"]
        report = {"seed": seed, "completed": True, "format": "stability-v1", "visits": len(sources),
                  "frames": session.steps, "source_keys_correct": source_keys_correct,
                  "source_failures": source_failures, "query_keys_correct": encoded_correct,
                  "old_episode_facts_correct": facts, "variants": results,
                  "fresh_process_reactivation_equal": fresh_equal, "next_write_equal": continued,
                  "clear_working_context_preserves_reads": cleared, "matches_previous_training_stream": matched_stream,
                  "recalled_training_stream_sha256": stream_digest.hexdigest(), "source_sha256": source_hash,
                  "source_sha256_unchanged": source_hash == hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                  "candidate_eligible_for_integration": (results["representatives3"]["retention_plasticity_passed"] and
                       fresh_equal and continued and cleared and matched_stream and facts == 320 and source_keys_correct == 320 and encoded_correct == 32 and not source_failures),
                  "elapsed_seconds": time.perf_counter() - started, "sensory_seconds": sensory_seconds,
                  "memory": memory_usage(), "scope": "Same raw causal curriculum as adaptive-v1, fixed hyperparameters. Parameter sensitivity is a squared data-gradient heuristic, not Fisher or learned gate. Latest representative per learned non-target cue stores routes/digests, no targets; reactivation reads original episodic weights, at most three old pairs per visit. History control may rehearse obsolete generalizations; old facts never rewritten. Baseline16/32 match only the upper bound of gradient-step counts for 1/3 replays, not source reads or runtime cost. Kernel/index remain experimental and uncoupled from the mind."}
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report
    finally:
        memory.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--max-seconds", type=float, default=240.)
    parser.add_argument("--resume-source", type=Path)
    parser.add_argument("--resume-model", type=Path)
    parser.add_argument("--resume-index", type=Path)
    args = parser.parse_args()
    torch.set_num_threads(1)
    if args.resume_source:
        if not args.resume_model or not args.resume_index or args.checkpoint:
            parser.error("Resume requires source/model/index only.")
        resume_child(args.resume_source, args.resume_model, args.resume_index, args.output)
        return
    if not args.checkpoint:
        parser.error("Training requires --checkpoint.")
    report = run(args.checkpoint, args.output, args.seed, args.max_seconds)
    print(json.dumps({"output": str(args.output.resolve()), "completed": report["completed"],
                      "eligible": report["candidate_eligible_for_integration"], "fresh_process_equal": report["fresh_process_reactivation_equal"],
                      "elapsed_seconds": report["elapsed_seconds"], "scores": {name: entry["retention_plasticity_passed"] for name, entry in report["variants"].items()}}))


if __name__ == "__main__":
    main()
