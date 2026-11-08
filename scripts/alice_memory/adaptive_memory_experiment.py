"""Finite causal conjunction curriculum, forgetting and bounded-window ablations."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from pathlib import Path

import torch

from .adaptive_memory import AdaptiveMemory, load, recalled_pair, restore, save
from .episodic_experiment import packets
from .episodic_session import EpisodicSession
from .experience_perception import semantic
from .experience_signals import samples
from .grounded_mind import load as load_grounded
from .online_memory import OnlineMemory
from .paged_memory import PagedMemory
from .process_metrics import Budget, memory_usage, quantiles


VARIANTS = {
    "linear_window1": dict(architecture="linear", window=1),
    "linear_window16": dict(architecture="linear", window=16),
    "mlp_window1": dict(window=1),
    "mlp_window4": dict(window=4),
    "mlp_window8": dict(window=8),
    "mlp_window16": dict(window=16),
    "mlp_huber_window16": dict(window=16, loss="huber"),
    "mlp_no_momentum_window16": dict(window=16, momentum=0.),
    "mlp_decay_window16": dict(window=16, retention=.0001),
    "mlp_shuffled_values_window16": dict(window=16),
}


def assessment(model, queries, contexts, revised=False):
    results = []
    errors = []
    for query in queries:
        if query["context"] not in contexts:
            continue
        output = (model.weights @ query["key"] if isinstance(model, OnlineMemory) else model.read(query["key"]))
        expected = query["revised"] if revised else query["expected"]
        results.append(output.argmax().item() == expected)
        target = torch.nn.functional.one_hot(torch.tensor(expected), num_classes=4).double()
        errors.append((output - target).square().mean().item())
    return {"correct": sum(results), "total": len(results), "top1_accuracy": sum(results) / len(results),
            "mse": sum(errors) / len(errors), "calibrated_confidence": False}


def make_queries(session, mapping, seed):
    queries = []
    rng = random.Random(seed + 823000)
    encoded_correct = 0
    for context in range(4):
        for activity in range(4):
            for appraisal in (1, 3):
                expected = mapping[(activity + context) % 4]
                truth = (activity, appraisal, expected, context)
                image, sound = samples(truth, rng, (True, True, False, True))
                cue, known = semantic(session.interpret(packets(image, sound, 0., 0))[0])
                if not all(known[index] for index in (0, 1, 3)) or known[2]:
                    raise ValueError("Held-out sensory query is missing a key or exposing its target.")
                fields = cue.reshape(4, 4)
                encoded_correct += all(fields[index].argmax().item() == truth[index] for index in (0, 1, 3))
                queries.append({"key": fields[[0, 1, 3]].flatten().clone(), "expected": expected,
                                "revised": mapping[(activity + context + (context == 1)) % 4],
                                "context": context})
    return queries, encoded_correct


def curriculum(seed, mapping, repeats):
    rng = random.Random(seed + 813000)
    phases = []
    for contexts, revision in (((0, 1), False), ((2, 3), False), ((1,), True)):
        records = []
        for _ in range(repeats):
            visit = [(activity, appraisal, mapping[(activity + context + int(revision)) % 4], context)
                     for context in contexts for activity in range(4) for appraisal in (0, 2)]
            rng.shuffle(visit)
            records.extend(visit)
        phases.append(records)
    return phases


def run(checkpoint, output, seed=17, repeats=8, seconds=180.):
    torch.set_num_threads(1)
    if type(repeats) is not int or not 1 <= repeats <= 32:
        raise ValueError("Use one to thirty-two bounded curriculum rounds.")
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
    control_rng = random.Random(seed + 833000)
    mapping = list(range(4))
    rng.shuffle(mapping)
    phases = curriculum(seed, mapping, repeats)
    total_visits = sum(map(len, phases))
    memory = PagedMemory(total_visits + 1, hot_limit=4)
    session = EpisodicSession(perception, boundary, memory)
    models = {}
    for name, configuration in VARIANTS.items():
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(seed + 793000)
            models[name] = AdaptiveMemory(**configuration)
    models["linear_rls"] = OnlineMemory(12, 4)
    try:
        queries, encoded_correct = make_queries(session, mapping, seed)
    except BaseException:
        memory.close()
        raise
    results = {name: {"phases": [], "write_seconds": [], "initial": assessment(model, queries, (0, 1, 2, 3))}
               for name, model in models.items()}
    sources = []
    source_failures = []
    source_keys_correct = 0
    source_digest = hashlib.sha256()
    sensory_started = time.perf_counter()
    sensory_seconds = 0.
    completed = 0
    try:
        for phase, records in enumerate(phases):
            for truth in records:
                budget.check(completed)
                sensory_started = time.perf_counter()
                previous_count = len(memory.blocks)
                for frame in range(2):
                    elapsed = 3. if frame == 0 else .1
                    image, sound = samples(truth, rng)
                    observation = session.step(packets(image, sound, session.clock + elapsed, session.steps * 2), elapsed)
                sensory_seconds += time.perf_counter() - sensory_started
                index = observation["episode"]
                if index is None or len(memory.blocks) != previous_count + 1:
                    raise ValueError("The causal curriculum did not produce exactly one new visit.")
                pair = recalled_pair(memory, index, session.clock)
                sources.append((index, truth))
                if pair is None:
                    source_failures.append(index)
                    continue
                source_keys_correct += all(pair["key"].reshape(3, 4)[group].argmax().item() == truth[field]
                                           for group, field in enumerate((0, 1, 3)))
                source_digest.update(json.dumps([pair["key"].tolist(), pair["value"].tolist()]).encode())
                for name, model in models.items():
                    budget.check(completed)
                    value = pair["value"]
                    if "shuffled" in name:
                        # Independent label reassignment: same keys and number of updates.
                        value = torch.roll(value, control_rng.randrange(4))
                    before = time.perf_counter()
                    if isinstance(model, OnlineMemory):
                        model.write(pair["key"], value)
                    else:
                        model.write(pair["key"], value, session.clock)
                    results[name]["write_seconds"].append(time.perf_counter() - before)
                    completed += 1
            contexts = (0, 1) if phase == 0 else ((2, 3) if phase == 1 else (1,))
            old = (0,) if phase == 0 else ((0, 1) if phase == 1 else (0, 2, 3))
            for name, model in models.items():
                results[name]["phases"].append({"new": assessment(model, queries, contexts, revised=phase == 2),
                                                "old_unchanged": assessment(model, queries, old),
                                                "unseen": assessment(model, queries, (2, 3)) if phase == 0 else None})
        old_fact_correct = 0
        for index, truth in sources:
            pair = recalled_pair(memory, index, session.clock)
            old_fact_correct += pair is not None and pair["value"].argmax().item() == truth[2]
        checkpoint_exact = True
        cleared_read_equal = True
        for name, model in models.items():
            entry = results[name]
            durations = entry.pop("write_seconds")
            entry["write_seconds_total"] = sum(durations)
            entry["write_latency_seconds"] = quantiles(durations) if durations else None
            if isinstance(model, OnlineMemory):
                entry["state_tensor_bytes"] = sum(value.numel() * value.element_size() for value in model.state_dict().values())
                entry["parameters"] = model.weights.numel()
                entry["working_context_bytes"] = 0
                continue
            entry.update(model.metrics())
            save(output / (name + ".pt"), model)
            resumed = load(output / (name + ".pt"))
            uninterrupted = restore(model.snapshot())
            next_key = queries[0]["key"]
            next_value = torch.nn.functional.one_hot(torch.tensor(mapping[0]), num_classes=4).double()
            for candidate in (resumed, uninterrupted):
                candidate.write(next_key, next_value, session.clock + .1)
            equal = all(torch.equal(value, resumed.state_dict()[key]) for key, value in uninterrupted.state_dict().items())
            checkpoint_exact &= equal
            entry["next_write_equal"] = equal
            predictions = [model.read(query["key"]) for query in queries]
            model.clear_working_context()
            unchanged = all(torch.equal(before, model.read(query["key"])) for before, query in zip(predictions, queries))
            cleared_read_equal &= unchanged
            entry["clear_working_context_preserves_reads"] = unchanged
        candidate = results["mlp_window16"]
        scores = candidate["phases"]
        nonlinear_gain = (scores[1]["new"]["top1_accuracy"] > results["linear_rls"]["phases"][1]["new"]["top1_accuracy"] + .1)
        promotion = (encoded_correct == len(queries) and source_keys_correct == total_visits and not source_failures and old_fact_correct == total_visits
                     and all(score["new"]["top1_accuracy"] >= .9 and score["old_unchanged"]["top1_accuracy"] >= .9 for score in scores)
                     and nonlinear_gain and checkpoint_exact and cleared_read_equal)
        report = {"format": 36, "seed": seed, "curriculum_rounds": repeats, "visits": total_visits,
                  "new_sensory_frames": session.steps, "source_failures": source_failures,
                  "recalled_training_keys_correct": source_keys_correct,
                  "held_out_query_keys_correct": encoded_correct, "held_out_queries": len(queries),
                  "old_episode_facts_correct": old_fact_correct, "source_sha256": source_hash,
                  "source_sha256_unchanged": source_hash == hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                  "recalled_training_stream_sha256": source_digest.hexdigest(), "variants": results,
                  "next_write_equal": checkpoint_exact, "clear_working_context_preserves_reads": cleared_read_equal,
                  "candidate_promoted": promotion, "nonlinear_gain_over_rls": nonlinear_gain,
                  "completed": True, "elapsed_seconds": time.perf_counter() - started,
                  "sensory_seconds": sensory_seconds, "memory": memory_usage(),
                  "scope": "New raw audiovisual visits in causal order; keys/targets read from episodic weights; conjunction of activity and context; appraisal 1/3 held out; changed rule in context 1. Fixed SGD hyperparameters, no meta-training or learned gates; top1 capacity experiment, uncalibrated predictions. RLS and SGD have different parameter/FLOP/state budgets, explicitly measured. At most sixteen encoded examples used only in updates; factual episodic store unchanged; not integrated into the mind."}
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report
    finally:
        memory.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--repeats", type=int, default=8)
    parser.add_argument("--max-seconds", type=float, default=180.)
    args = parser.parse_args()
    report = run(args.checkpoint, args.output, args.seed, args.repeats, args.max_seconds)
    print(json.dumps({"output": str(args.output.resolve()), "completed": report["completed"],
                      "candidate_promoted": report["candidate_promoted"], "elapsed_seconds": report["elapsed_seconds"],
                      "old_episode_facts_correct": report["old_episode_facts_correct"], "visits": report["visits"]}))


if __name__ == "__main__":
    main()
