"""Finite learned binding and concurrent neural-memory curriculum."""
from __future__ import annotations

import argparse
import copy
import json
import random
import time
from pathlib import Path

import torch

from .episodic_experiment import packets as single_packets
from .episodic_language import write_report
from .episodic_memory import EpisodicMemory
from .episodic_session import EpisodicSession
from .experience_signals import WORDS, samples
from .grounded_mind import load as load_grounded
from .grounded_language import learned_digest
from .process_metrics import memory_usage
from .scene_binding import ParticipantBinding, data, evaluate, source, train
from .scene_memory import ConcurrentSession, load, save
from .scene_signals import packets, scene


def create(perception, boundary, binding, capacity=64):
    return ConcurrentSession(EpisodicSession(perception, boundary, EpisodicMemory(capacity)), binding, source(perception))


def drive(session, values, rng, masks=((True,) * 4, (True,) * 4), modality="both"):
    image, audio = scene(values, rng, masks)
    return session.step(packets(image, audio, session.clock + .1, session.base.steps * 2, modality), .1)


def query(session, values, rng, window, view="current", modality="both"):
    image, sound = samples(values, rng, (True, False, False, True))
    return session.base.query(single_packets(image, sound, session.clock, 0, modality), view, window)


def runtime(perception, boundary, binding, seed):
    rng = random.Random(seed + 810000)
    successful, swapped, corrected, unassigned, evidence_conflicts = 0, 0, 0, 0, 0
    for trial in range(16):
        first = (trial % 4, rng.randrange(4), trial % 4, 0)
        second = ((trial + 1) % 4, rng.randrange(4), (trial + 1) % 4, 1)
        agent = create(perception, boundary, binding)
        expected = [first, second]
        for frame in range(6):
            order = expected if frame % 2 == 0 else list(reversed(expected))
            result = drive(agent, tuple(order), rng)
            actual = {item["region"]: item["track"] for item in result["events"]}
            if frame:
                swapped += int(len(agent.memory.blocks) == 2 and len(actual) == 2)
        window = (.1, agent.clock)
        for value in expected:
            answer = query(agent, value, rng, window)
            successful += int(answer["recall"] is not None and answer["recall"]["autor"] == WORDS[2][value[2]])
        # Directed correction has a unique activity/context cue. Other simultaneous
        # participants must retain their own current and initial interpretations.
        cue_image, cue_audio = samples(first, rng, (True, False, False, True))
        changed = (*first[:2], (first[2] + 2) % 4, first[3])
        evidence_image, evidence_audio = samples(changed, rng, (False, False, True, False))
        revision = agent.base.revise(single_packets(cue_image, cue_audio, agent.clock, 0),
                                     single_packets(evidence_image, evidence_audio, agent.clock, 2), 2, 0., window)
        current, initial = query(agent, first, rng, window), query(agent, first, rng, window, "initial")
        other = query(agent, second, rng, window)
        corrected += int(revision["revised"] and current["recall"]["autor"] == WORDS[2][changed[2]]
                         and initial["recall"]["autor"] == WORDS[2][first[2]]
                         and other["recall"]["autor"] == WORDS[2][second[2]])
        missing = drive(agent, tuple(expected), rng, ((True, True, False, True), (True,) * 4))
        unassigned += int(0 in missing["unassigned_regions"] and all(item["region"] != 0 for item in missing["events"]))
        # Conflicting modality ownership is not a new autobiographical assertion.
        image, audio = scene(tuple(expected), rng)
        count = len(agent.memory.blocks)
        conflict = agent.step(packets(image, audio.flip(0), agent.clock + .1, agent.base.steps * 2), .1)
        evidence_conflicts += int(len(agent.memory.blocks) == count and not conflict["events"])
    return {"simultaneous_recall_correct": successful, "simultaneous_recall_cases": 32,
            "position_changes_preserved": swapped, "position_changes_cases": 80,
            "directed_revisions_preserved_other": corrected, "revision_cases": 16,
            "missing_participant_abstained": unassigned, "modality_conflicts_abstained": evidence_conflicts,
            "accepted": successful == 32 and swapped == 80 and corrected == unassigned == evidence_conflicts == 16}


def _evaluate(original, checkpoint, output, seed, started):
    original_digest = learned_digest(original)
    base = original.mind.actor.session
    binding = ParticipantBinding()
    training = data(base.perception, seed + 820000)
    held_out = data(base.perception, seed + 830000, evaluation=True)
    before = evaluate(binding, held_out)
    train(binding, training, seed + 840000)
    learned = evaluate(binding, held_out)
    control = copy.deepcopy(binding)
    with torch.no_grad():
        for value in control.parameters():
            value.zero_()
    erased = evaluate(control, held_out)
    results = runtime(base.perception, base.boundary, binding, seed)
    instance = create(base.perception, base.boundary, binding)
    rng = random.Random(seed)
    drive(instance, ((0, 0, 0, 0), (1, 1, 1, 1)), rng)
    drive(instance, ((1, 1, 1, 1), (0, 0, 0, 0)), rng)
    save(output / "session.pt", instance)
    resumed = load(output / "session.pt")
    next_frame = scene(((0, 0, 0, 0), (1, 1, 1, 1)), rng)
    left = instance.step(packets(*next_frame, instance.clock + .1, instance.base.steps * 2), .1)
    right = resumed.step(packets(*next_frame, resumed.clock + .1, resumed.base.steps * 2), .1)
    equal = left == right and all(torch.equal(value, resumed.memory.state_dict()[name]) for name, value in instance.memory.state_dict().items())
    preserved = learned_digest(original) == original_digest
    report = {"seed": seed, "acceptance_scope": "localized_simultaneous_synthetic_episodic_subsystem",
              "before": before, "binding": learned, "zero_weights": erased, "runtime": results,
              "resume_next_frame_equal": equal, "source": source(base.perception),
              "source_checkpoint": str(checkpoint.resolve()), "source_old_memory_modified": not preserved,
              "seconds": time.perf_counter() - started, "process": memory_usage(),
              "accepted": learned["match_recall"] >= .98 and learned["false_match_rate"] <= .02
                          and erased["match_recall"] < .5 and results["accepted"] and equal and preserved}
    return report


def run(checkpoint: Path, output: Path, seed=17):
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    original = None
    report = {"seed": seed, "accepted": False, "completed": False}
    write_report(output / "report.json", report)
    try:
        original = load_grounded(checkpoint)
        report.update(_evaluate(original, checkpoint, output, seed, started), completed=True)
        return report
    except (Exception, KeyboardInterrupt) as error:
        report["error"] = type(error).__name__ + ": " + str(error)
        raise
    finally:
        if original is not None and hasattr(original.mind.actor.session.memory, "close"):
            original.mind.actor.session.memory.close()
        write_report(output / "report.json", report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()
    result = run(args.checkpoint, args.output, args.seed)
    print(json.dumps({"accepted": result["accepted"], "output": str(args.output.resolve())}))
    if not result["accepted"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
