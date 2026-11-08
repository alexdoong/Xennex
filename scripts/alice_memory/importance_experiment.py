"""Causal learned importance versus recency/manual and surprise-only controls."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from pathlib import Path

import torch

from .contracts import Observation
from .continuous_mind import ContinuousMind, load, save
from .episodic_experiment import packets
from .episodic_session import EpisodicSession
from .experience_signals import samples
from .experience_perception import semantic
from .importance import Consequence
from .memory_actor import MemoryActor, load as load_actor
from .process_metrics import Budget, memory_usage, quantiles


class ConsequenceWorld:
    """Simulator keeps its own facts and evaluates what the recipient heard.

The agent receives raw cues/motor returns plus numeric progress/social/effort.
Expected codes, noisy-channel flag and oracle episode labels are never inputs.
"""
    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)

    def encounter(self, mind: ContinuousMind, truth: tuple[int, ...]) -> tuple[int, tuple[float, float]]:
        started = mind.clock + 3.
        episode = None
        for step in range(8):
            elapsed = 3. if step == 0 else .2
            image, sound = samples(truth, self.rng)
            result = mind.perceive(packets(image, sound, mind.clock + elapsed, mind.actor.session.steps * 2), elapsed)
            episode = result["episode"]
        if episode is None:
            raise ValueError("Simulator encounter was not perceived.")
        return episode, (started, mind.clock)

    def ask(self, mind: ContinuousMind, truth: tuple[int, ...], window: tuple[float, float],
            noisy: bool = False) -> dict:
        image, sound = samples(truth, self.rng, (True, False, False, True))
        cues = packets(image, sound, mind.clock, 0)
        mind.request(cues, 2, window)
        response = mind.tick(.1)
        action = response["action"]
        if action is None or action["kind"] != "emit":
            raise ValueError("The curriculum could not obtain an emission within its work budget.")
        perceived = self.rng.randrange(4) if noisy else action["signal"]
        values = list(truth)
        values[2] = perceived
        _, returned = samples(tuple(values), self.rng, (False, False, True, False))
        feedback = Observation("audio", returned, mind.clock + .1, action["sequence"],
                               origin="self", action_id=action["sequence"])
        heard = mind.hear([feedback], .1)
        # Recipient progress follows the consequence of the performed action,
        # not a manual importance parameter supplied to the memory.
        succeeded = perceived == truth[2]
        outcome = Consequence(action["sequence"], mind.clock + .1, float(succeeded),
                              .5 if succeeded else 0., 1. if noisy else .1, "person")
        credited = mind.consequences([outcome], .1)
        return {"succeeded": succeeded, "heard": heard["accepted"], "credited": credited["accepted"],
                "error": heard["error"]}


def build(template: MemoryActor, seed: int, budget: Budget, reversed_channels: bool = False):
    mind = ContinuousMind(MemoryActor(EpisodicSession(template.session.perception, template.session.boundary), template.policy))
    world = ConsequenceWorld(seed)
    author = world.rng.randrange(4)
    old_truth = (0, 0, author, 0)
    old, old_window = world.encounter(mind, old_truth)
    for step in range(24):
        budget.check(step)
        world.ask(mind, old_truth, old_window, reversed_channels)
    mind.unobserved_gap(40.)
    noisy_truth = (0, 2, (author + 1) % 4, 0)
    distractor, distractor_window = world.encounter(mind, noisy_truth)
    trials = []
    for step in range(64):
        budget.check(step + 24)
        trials.append(world.ask(mind, noisy_truth, distractor_window, not reversed_channels))
    irrelevant_truth = (3, 3, (author + 2) % 4, 3)
    irrelevant, irrelevant_window = world.encounter(mind, irrelevant_truth)
    for step in range(12):
        budget.check(step + 88)
        world.ask(mind, irrelevant_truth, irrelevant_window)
    image, sound = samples(old_truth, world.rng, (True, False, False, True))
    cues = packets(image, sound, mind.clock, 0)
    cue, _ = semantic(mind.actor.session.interpret(cues)[0])
    return mind, world, {"old": old, "distractor": distractor, "irrelevant": irrelevant,
                         "old_window": old_window, "old_truth": old_truth, "cues": cues, "cue": cue,
                         "noisy_channel_success": sum(item["succeeded"] for item in trials) / len(trials)}


def evaluate(template: MemoryActor, seed: int, budget: Budget) -> tuple[ContinuousMind, dict, dict]:
    mind, world, data = build(template, seed, budget)
    rankings = {mode: mind.importance.rank(mind.actor.session.memory, data["cue"], 2, mind.clock, mode, 1)
                for mode in ("learned", "fixed", "surprise")}
    selected = {mode: items[0]["episode"] if items else None for mode, items in rankings.items()}
    # A one-slot active working set is a retrieval-budget comparison. No claim
    # of physical eviction or smaller total RAM is made in this M5 experiment.
    later = {}
    for mode, chosen in selected.items():
        if chosen != data["old"]:
            later[mode] = 0.
            continue
        result = mind.actor.respond(data["cues"], 2, data["old_window"])
        later[mode] = float(result["action"]["signal"] == data["old_truth"][2])
        # Clean up this measured action through the same causal feedback path.
        emitted = mind.actor.last_action
        _, sound = samples(data["old_truth"], world.rng, (False, False, True, False))
        mind.hear([Observation("audio", sound, mind.clock + .1, emitted.sequence,
                               origin="self", action_id=emitted.sequence)], .1)
    old_trace = mind.actor.session.memory.traces[data["old"]]
    occurred = (old_trace.started, old_trace.ended)
    before = {name: tensor.clone() for name, tensor in mind.actor.session.memory.blocks[data["old"]].state_dict().items()}
    value_before = mind.importance.durable(data["old"], 2)
    mind.request(data["cues"], 2, data["old_window"])
    resumed = mind.tick(.1)
    proactive = []
    for _ in range(40):
        tick = mind.tick(.1)
        if tick["evoked"] is not None:
            proactive.append(tick["evoked"]["episode"])
    trace = mind.actor.session.memory.traces[data["old"]]
    original_age_preserved = occurred == (trace.started, trace.ended)
    facts_preserved = all(torch.equal(tensor, mind.actor.session.memory.blocks[data["old"]].state_dict()[name]) for name, tensor in before.items())
    no_truth_reinforcement = facts_preserved and value_before == mind.importance.durable(data["old"], 2)
    swapped, _, reversed_data = build(template, seed + 100000, budget, True)
    reversed_rank = swapped.importance.rank(swapped.actor.session.memory, reversed_data["cue"], 2, swapped.clock, limit=1)
    reversed_selected = reversed_rank[0]["episode"] if reversed_rank else None
    retained_bytes = sum(tensor.numel() * tensor.element_size() for tensor in mind.actor.session.memory.blocks[data["old"]].state_dict().values())
    report = {"selected": selected, "ranking": rankings, "episode_roles_evaluator_only": {name: data[name] for name in ("old", "distractor", "irrelevant")},
              "later_answer_success_with_one_slot": later, "active_slot_bytes": retained_bytes,
              "useful_episode_per_active_byte": {mode: int(chosen == data["old"]) / retained_bytes for mode, chosen in selected.items()},
              "noisy_channel_success": data["noisy_channel_success"], "proactive_evocations": proactive,
              "pending_task_resumed": bool(resumed.get("resumed_pending")), "original_age_preserved": original_age_preserved,
              "reactivation_does_not_retrain_truth_or_value": no_truth_reinforcement,
              "reversed_consequences_selected": reversed_selected,
              "reversed_reliable_episode": reversed_data["distractor"],
              "accepted": selected["learned"] == data["old"] and selected["fixed"] != data["old"]
                          and selected["surprise"] != data["old"] and data["irrelevant"] not in selected.values()
                          and later["learned"] == 1 and original_age_preserved and no_truth_reinforcement
                          and bool(proactive) and all(index == data["old"] for index in proactive)
                          and reversed_selected == reversed_data["distractor"]}
    return mind, report, {"truth": data["old_truth"], "window": data["old_window"]}


def soak(mind: ContinuousMind, seed: int, budget: Budget, fixture: dict, steps: int = 10000) -> dict:
    world = ConsequenceWorld(seed)
    # Simulator truth is retained by the evaluator from the original encounter,
    # not reconstructed from the agent's index or predictions.
    old = mind.actor.session.memory.traces[0]
    window, truth = fixture["window"], fixture["truth"]
    latency, evoked = [], []
    largest_credits, largest_pending, useful_answers = 0, 0, 0
    ages = (old.started, old.ended)
    starting_value_writes = mind.importance.values.writes.item()
    for step in range(steps):
        budget.check(step + 200)
        started = time.perf_counter()
        image, _ = samples(truth, world.rng)
        interference = list(truth)
        interference[2] = world.rng.randrange(4)
        _, noisy_sound = samples(tuple(interference), world.rng, (False, False, True, False))
        mind.perceive(packets(image, noisy_sound, mind.clock + .1, mind.actor.session.steps * 2), .1)
        tick = mind.tick(0.)
        if tick["evoked"] is not None:
            evoked.append(tick["evoked"]["episode"])
        if step % 1000 == 999:
            result = world.ask(mind, truth, window)
            useful_answers += int(result["succeeded"])
        largest_credits = max(largest_credits, len(mind.credits))
        largest_pending = max(largest_pending, len(mind.actor.pending))
        latency.append((time.perf_counter() - started) * 1000)
    useful = sum(index == 0 for index in evoked) / max(len(evoked), 1)
    report = {"steps": steps, "evocations": len(evoked), "useful_evocation_fraction": useful,
              "later_answers": useful_answers, "later_questions": steps // 1000,
              "max_credits": largest_credits, "max_motor_pending": largest_pending,
              "episodes": len(mind.actor.session.memory.blocks), "latency_ms": quantiles(latency),
              "original_occurrence_preserved": ages == (old.started, old.ended),
              "consequence_updates": mind.importance.values.writes.item() - starting_value_writes,
              "scope": "stable image plus conflicting random author tones; simultaneous opinions abstain; no new scene identities",
              "accepted": useful >= .9 and useful_answers == steps // 1000 and bool(evoked)
                          and largest_credits <= 32 and largest_pending <= 32
                          and ages == (old.started, old.ended) and len(mind.actor.session.memory.blocks) <= 4}
    return report


def run(checkpoint: Path, output: Path, seed: int, seconds: float) -> dict:
    if type(seed) is not int or not 0 <= seed <= 100000:
        raise ValueError("Invalid importance seed.")
    budget = Budget(100000, seconds)
    torch.set_num_threads(2)
    template = load_actor(checkpoint)
    output.mkdir(parents=True, exist_ok=False)
    mind, report, fixture = evaluate(template, seed + 53000, budget)
    report["soak"] = soak(mind, seed + 63000, budget, fixture)
    save(output / "mind.pt", mind)
    resumed = load(output / "mind.pt")
    report["checkpoint_next_tick_equal"] = mind.tick(2.) == resumed.tick(2.)
    report.update(seed=seed, world_seed=seed + 53000, soak_seed=seed + 63000, format=18,
                  source_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                  scope="goal-specific RLS consequences; modelled internal signals; noisy motor feedback; one-slot activation, no physical eviction",
                  learned_value_state_bytes=sum(tensor.numel() * tensor.element_size() for tensor in mind.importance.state_dict().values()),
                  episodes=len(mind.actor.session.memory.blocks), internal=asdict_internal(mind),
                  raw_history_stored=False, memory=memory_usage(),
                  accepted=report["accepted"] and report["checkpoint_next_tick_equal"] and report["soak"]["accepted"])
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def asdict_internal(mind: ContinuousMind) -> dict:
    return mind.snapshot()["internal"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--max-seconds", type=float, default=120)
    args = parser.parse_args()
    report = run(args.checkpoint, args.output, args.seed, args.max_seconds)
    print(json.dumps({"output": str(args.output.resolve()), "accepted": report["accepted"],
                      "selected": report["selected"], "reversed_consequences_selected": report["reversed_consequences_selected"]}))
    raise SystemExit(0 if report["accepted"] else 2)


if __name__ == "__main__":
    main()
