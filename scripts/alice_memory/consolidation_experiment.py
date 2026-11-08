"""Shared regularities, changed regularity and preserved episodic facts."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

import torch

from .consolidating_mind import ConsolidatingMind, load, save
from .continuous_mind import ContinuousMind
from .episodic_experiment import packets
from .episodic_memory import EpisodicMemory
from .episodic_session import EpisodicSession
from .experience_signals import WORDS, samples
from .memory_actor import MemoryActor, load as load_actor
from .process_metrics import Budget, memory_usage
from .temporal_mind import TemporalMind, load_models


def make_agent(template, source, core, forgetting):
    session = EpisodicSession(template.session.perception, template.session.boundary, EpisodicMemory(64))
    base = ContinuousMind(MemoryActor(session, template.policy))
    return ConsolidatingMind(TemporalMind(base, core, source), forgetting=forgetting)


def assess(agent, mapping, contexts, seed, details=False):
    rng = random.Random(seed)
    results, abstentions, contextual = [], [], []
    for context in contexts:
        for activity in range(4):
            for appraisal in range(4):
                if (activity + appraisal) % 2 != 1:
                    continue
                truth = (activity, appraisal, mapping[context], context)
                image, sound = samples(truth, rng, (True, True, False, True))
                result = agent.expect(packets(image, sound, agent.clock, 0))
                results.append(result["supported"] and result["value"] == WORDS[2][truth[2]])
                abstentions.append(not result["supported"])
                contextual.append(result.get("selected_source_field") == "contexto")
    scores = {"accuracy": sum(results) / len(results), "abstention": sum(abstentions) / len(results),
              "context_selected": sum(contextual) / len(results)}
    return scores if details else scores["accuracy"]


def run(checkpoint: Path, models: Path, output: Path, seed: int, seconds: float = 120) -> dict:
    torch.set_num_threads(1)
    budget = Budget(10000, seconds)
    template = load_actor(checkpoint)
    source, core = load_models(models)
    output.mkdir(parents=True, exist_ok=False)
    rng = random.Random(seed + 223000)
    mapping = list(range(4))
    rng.shuffle(mapping)
    revised = mapping.copy()
    revised[1] = mapping[2]
    phases = []
    for contexts, rule, repeats in (((0, 1), mapping, 1), ((2, 3), mapping, 1), ((1,), revised, 2)):
        truths = [(activity, appraisal, rule[context], context) for _ in range(repeats)
                  for context in contexts for activity in range(4) for appraisal in range(4)
                  if (activity + appraisal) % 2 == 0]
        rng.shuffle(truths)
        phases.append([{"truth": truth, "frames": [samples(truth, rng) for _ in range(4)]} for truth in truths])
    controls, last_agent = {}, None
    for control, forgetting in (("adaptive", .9), ("cumulative", 1.), ("none", .9)):
        agent = make_agent(template, source, core, forgetting)
        remembered = []
        phase_scores = []
        early_unknown = assess(agent, mapping, (2, 3), seed + 183000, details=True)
        unknown_after_first = None
        for stage, records in enumerate(phases):
            for record in records:
                budget.check(agent.mind.actor.session.steps)
                start = agent.clock + 3.
                for index, (image, sound) in enumerate(record["frames"]):
                    elapsed = 3. if index == 0 else .2
                    agent.perceive(packets(image, sound, agent.clock + elapsed,
                                          agent.mind.actor.session.steps * 2), elapsed)
                remembered.append((record["truth"], (start, agent.clock)))
            agent.consolidate_current()
            if control == "none":
                agent.semantic.bank.weights.zero_()
                agent.semantic.bank.precision.copy_(torch.eye(15, dtype=torch.float64) * 1000)
            rule = mapping if stage < 2 else revised
            if stage == 0:
                unknown_after_first = assess(agent, mapping, (2, 3), seed + 233000, details=True)
            phase_scores.append({"new_context_accuracy": assess(agent, rule, (0, 1) if stage == 0 else ((2, 3) if stage == 1 else (1,)), seed + 193000 + stage),
                                 "unchanged_old_context_accuracy": assess(agent, mapping, (0,) if stage == 0 else ((0, 1) if stage == 1 else (0, 2, 3)), seed + 203000 + stage)})
        episodic_correct = 0
        query_rng = random.Random(seed + 213000)
        for truth, window in remembered:
            image, sound = samples(truth, query_rng, (True, True, False, True))
            recalled = agent.mind.actor.session.query(packets(image, sound, agent.clock, 0), window=window)
            episodic_correct += recalled["recall"] is not None and recalled["recall"].get("autor") == WORDS[2][truth[2]]
        controls[control] = {"phases": phase_scores, "unknown_before_learning": early_unknown,
                             "unknown_after_first_phase": unknown_after_first,
                             "old_episode_accuracy": episodic_correct / len(remembered),
                             "episodic_recall_count": len(remembered),
                             "episodes": len(agent.mind.actor.session.memory.blocks),
                             "semantic_writes": int(agent.semantic.bank.writes),
                             "semantic_tensor_bytes": sum(value.numel() * value.element_size() for value in agent.semantic.state_dict().values())}
        if control == "adaptive":
            last_agent = agent
    save(output / "agent.pt", last_agent)
    restored = load(output / "agent.pt")
    resume_equal = last_agent.tick(.1) == restored.tick(.1) and torch.equal(last_agent.temporal.hidden, restored.temporal.hidden)
    scores = controls["adaptive"]["phases"]
    accepted = (scores[0]["new_context_accuracy"] >= .95 and scores[1]["new_context_accuracy"] >= .95
                and scores[2]["new_context_accuracy"] >= .9
                and all(score["unchanged_old_context_accuracy"] >= scores[0]["unchanged_old_context_accuracy"] - .05 for score in scores[1:])
                and controls["adaptive"]["old_episode_accuracy"] == 1.
                and controls["adaptive"]["unknown_after_first_phase"]["abstention"] == 1.
                and scores[2]["new_context_accuracy"] > controls["cumulative"]["phases"][2]["new_context_accuracy"]
                and scores[0]["new_context_accuracy"] > controls["none"]["phases"][0]["new_context_accuracy"]
                and resume_equal)
    report = {"seed": seed, "world_seed": seed + 223000, "format": 23, "controls": controls,
              "next_tick_equal": resume_equal, "accepted": accepted, "memory": memory_usage(),
              "source_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
              "model_sha256": hashlib.sha256(models.read_bytes()).hexdigest(),
              "scope": "global conditional RLS from recalled episodic weights; raw supervised synthetic senses; half nuisance combinations held out; hypotheses, no reservoir or capacity eviction"}
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--models", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--max-seconds", type=float, default=120)
    args = parser.parse_args()
    report = run(args.checkpoint, args.models, args.output, args.seed, args.max_seconds)
    print(json.dumps({"output": str(args.output.resolve()), "accepted": report["accepted"], "controls": report["controls"]}))
    raise SystemExit(0 if report["accepted"] else 2)


if __name__ == "__main__":
    main()
