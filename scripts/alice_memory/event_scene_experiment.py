"""Two simultaneous activities of one participant, finite neural memory tests."""
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
from .grounded_language import learned_digest
from .grounded_mind import load as load_grounded
from .scene_binding import EventBinding, event_data, event_source, evaluate, train
from .scene_experiment import drive, query
from .scene_memory import ConcurrentEventSession, load, save
from .scene_signals import packets, scene
from .process_metrics import memory_usage


def create(perception, boundary, binding, capacity=64):
    return ConcurrentEventSession(EpisodicSession(perception, boundary, EpisodicMemory(capacity)), binding, event_source(perception))


def runtime(perception, boundary, binding, seed):
    rng = random.Random(seed + 910000)
    correct = swaps = revisions = changed_events = conflicts = missing = crossmodal = erased_facts = 0
    for trial in range(16):
        values = ((trial % 4, 0, trial % 4, trial % 4), ((trial + 1) % 4, 1, trial % 4, trial % 4))
        agent = create(perception, boundary, binding)
        for frame in range(6):
            drive(agent, values if frame % 2 == 0 else tuple(reversed(values)), rng)
            if frame:
                swaps += int(len(agent.memory.blocks) == 2)
        window = (.1, agent.clock)
        for value in values:
            recalled = query(agent, value, rng, window)["recall"]
            correct += int(recalled is not None and recalled["autor"] == WORDS[2][value[2]] and recalled["impressao"] == WORDS[1][value[1]])
        cue_image, cue_audio = samples(values[0], rng, (True, False, False, True))
        evidence_image, evidence_audio = samples((values[0][0], 2, values[0][2], values[0][3]), rng, (False, True, False, False))
        change = agent.base.revise(single_packets(cue_image, cue_audio, agent.clock, 0),
                                   single_packets(evidence_image, evidence_audio, agent.clock, 2), 1, 0., window)
        current, initial, other = (query(agent, values[0], rng, window), query(agent, values[0], rng, window, "initial"),
                                   query(agent, values[1], rng, window))
        revisions += int(change["revised"] and current["recall"]["impressao"] == WORDS[1][2]
                         and initial["recall"]["impressao"] == WORDS[1][0] and other["recall"]["impressao"] == WORDS[1][1])
        new_values = (((trial + 2) % 4, 0, trial % 4, trial % 4), values[1])
        drive(agent, new_values, rng)
        changed_events += int(len(agent.memory.blocks) == 3 and query(agent, values[0], rng, window)["recall"]["impressao"] == WORDS[1][2])
        lost = drive(agent, new_values, rng, ((False, True, True, True), (True,) * 4))
        missing += int(0 in lost["unassigned_regions"] and all(item["region"] != 0 for item in lost["events"]))
        image, audio = scene(new_values, rng)
        count = len(agent.memory.blocks)
        result = agent.step(packets(image, audio.flip(0), agent.clock + .1, agent.base.steps * 2), .1)
        conflicts += int(not result["events"] and len(agent.memory.blocks) == count)
        for write, read in (("image", "audio"), ("audio", "image")):
            single_sense = create(perception, boundary, binding)
            for _ in range(3):
                drive(single_sense, values, rng, modality=write)
            sense_window = (.1, single_sense.clock)
            for value in values:
                recall = query(single_sense, value, rng, sense_window, modality=read)["recall"]
                crossmodal += int(recall is not None and recall["autor"] == WORDS[2][value[2]] and recall["impressao"] == WORDS[1][value[1]])
            with torch.no_grad():
                for block in single_sense.memory.blocks:
                    for bank in block.banks:
                        bank.weights.zero_()
            for value in values:
                recall = query(single_sense, value, rng, sense_window, modality=read)["recall"]
                erased_facts += int(recall is not None and any(item is not None for item in recall.values()))
    return {"correct_events": correct, "event_cases": 32, "preserved_position_changes": swaps,
            "position_changes": 80, "isolated_revisions": revisions, "activity_changes_preserved_past": changed_events,
            "missing_anchor_abstentions": missing, "modality_conflict_abstentions": conflicts,
            "crossmodal_correct": crossmodal, "crossmodal_cases": 64, "facts_after_erasing_weights": erased_facts,
            "accepted": correct == 32 and swaps == 80 and revisions == changed_events == missing == conflicts == 16
                        and crossmodal == 64 and erased_facts == 0}


def run(checkpoint: Path, output: Path, seed=17):
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    output.mkdir(parents=True, exist_ok=False)
    original = None
    started = time.perf_counter()
    report = {"accepted": False, "completed": False, "seed": seed,
              "scope": "two_localized_synthetic_events_same_participant"}
    write_report(output / "report.json", report)
    try:
        original = load_grounded(checkpoint)
        source_digest = learned_digest(original)
        base = original.mind.actor.session
        binding = EventBinding()
        training = event_data(base.perception, seed + 920000)
        held_out = event_data(base.perception, seed + 930000, 1024, evaluation=True)
        report["before"] = evaluate(binding, held_out)
        train(binding, training, seed + 940000, steps=1800)
        report["binding"] = evaluate(binding, held_out)
        zero = copy.deepcopy(binding)
        with torch.no_grad():
            for weight in zero.parameters():
                weight.zero_()
        report["zero_weights"] = evaluate(zero, held_out)
        report["runtime"] = runtime(base.perception, base.boundary, binding, seed)
        agent = create(base.perception, base.boundary, binding)
        rng = random.Random(seed)
        values = ((0, 0, 3, 0), (2, 1, 3, 0))
        drive(agent, values, rng)
        save(output / "session.pt", agent)
        resumed = load(output / "session.pt")
        image, audio = scene(tuple(reversed(values)), rng)
        left = agent.step(packets(image, audio, agent.clock + .1, agent.base.steps * 2), .1)
        right = resumed.step(packets(image, audio, resumed.clock + .1, resumed.base.steps * 2), .1)
        equal = left == right and all(torch.equal(weight, resumed.memory.state_dict()[name]) for name, weight in agent.memory.state_dict().items())
        report.update(completed=True, source=event_source(base.perception), resume_next_frame_equal=equal,
                      source_learned_weights_preserved=learned_digest(original) == source_digest,
                      seconds=time.perf_counter() - started, process=memory_usage())
        score = report["binding"]
        report["accepted"] = score["match_recall"] >= .98 and score["false_match_rate"] <= .02 and report["zero_weights"]["match_recall"] < .5 and report["runtime"]["accepted"] and equal and report["source_learned_weights_preserved"]
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
