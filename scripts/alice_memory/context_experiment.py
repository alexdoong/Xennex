"""Continuous temporal keys select bounded associative memory with access priority."""
from __future__ import annotations

import json
import random
import time
from pathlib import Path

import torch

from .context_memory import ContextMemory, load_checkpoint, save_checkpoint
from .experiment import learn_perception
from .network import Perception
from .online_memory import make_value, describe
from .signals import bank, synthetic_image, synthetic_audio, save_audio
from .temporal import train
from .temporal_core import TemporalCore, TemporalSession

PROFILES = (([5, 6, 7, 0], .5), ([3, 2, 1, 0], .5),
            ([5, 6, 7, 0], 4.), ([3, 2, 1, 0], 4.))


def observe(session: TemporalSession, features: torch.Tensor, history: list[int],
            gap: float, variant: int) -> tuple[torch.Tensor, torch.Tensor, float]:
    elapsed = 0.
    for index, identity in enumerate(history):
        duration = gap if index == len(history) - 1 else .5
        signal = features[identity * 12 + variant].unsqueeze(0)
        session.advance(signal, duration)
        elapsed += duration
    return session.hidden[0], signal[0], elapsed


@torch.no_grad()
def evaluate(core: TemporalCore, memory: ContextMemory, features: dict,
             targets: torch.Tensor, now: float, control: str = "") -> dict:
    scores, reads = {}, []
    for modality in ("image", "audio", "mixed"):
        session = TemporalSession(core)
        matches = []
        for profile, (history, gap) in enumerate(PROFILES):
            for variant in range(12):
                elapsed = .5 if control == "remove_time" else gap
                source = features["audio" if modality == "mixed" and variant % 2 else
                                  "image" if modality == "mixed" else modality]
                if control == "reset_state":
                    session = TemporalSession(core)
                    session.advance(source[variant].unsqueeze(0), elapsed)
                    context, signal = session.hidden[0], source[variant]
                else:
                    context, signal, _ = observe(session, source, history, elapsed, variant)
                result = memory.read(context, signal, now)
                matches.append(result["recall"] == describe(targets[profile].tolist()))
                reads.append(result["blocks_read"])
        scores[modality] = sum(matches) / len(matches)
    return {"accuracy": scores, "max_blocks_read": max(reads),
            "mean_blocks_read": sum(reads) / len(reads)}


def heat_checks(core: TemporalCore, features: torch.Tensor) -> dict:
    """Policy controls independent of the main episodic stream."""
    signal = features[0]
    first, _ = PROFILES[0]
    other, _ = PROFILES[1]
    old = TemporalSession(core)
    current = TemporalSession(core)
    old_context, _, _ = observe(old, features, first, .5, 0)
    other_context, _, _ = observe(current, features, other, .5, 0)
    memory = ContextMemory()
    old_id = memory.write(old_context, signal, make_value(torch.tensor([1, 0, 0])), 0, .9)
    memory.write(other_context, signal, make_value(torch.tensor([2, 2, 1])), 600, .1)
    result = memory.read(old_context, signal, 600)
    before = memory.heat(600)[old_id].item()
    memory.read(old_context, signal, 600, activate=True)
    after = memory.heat(600)[old_id].item()
    # Close artificial addresses test ranking only, not learned event semantics.
    near = torch.nn.functional.normalize(old_context.double(), dim=0)
    noise = torch.arange(48, dtype=torch.float64) - 23.5
    tangent = torch.nn.functional.normalize(noise - (noise @ near) * near, dim=0)
    tied = ContextMemory()
    tied.write(near, signal, make_value(torch.tensor([1, 0, 0])), 0, .1)
    # Separate controlled blocks bypass write clustering to expose a near tie.
    tied.blocks.append(type(tied.blocks[0])(key_size=16))
    tied.blocks[1].write(signal, make_value(torch.tensor([2, 2, 1])))
    tied.addresses[1] = torch.nn.functional.normalize(near + .05 * tangent, dim=0)
    tied.observations[1], tied.importance[1], tied.activation[1] = 1, .9, 1
    tied.last_access[1], tied.last_observed[1] = 600, 600
    tied.clock.fill_(600)
    warm_preference = tied.read(near, signal, 600)["block"] == 1
    return {"cold_relevant_beats_hot_unrelated": result["block"] == old_id,
            "old_memory_freshness": result["freshness"], "old_memory_importance": result["importance"],
            "heat_before_successful_access": before, "heat_after_successful_access": after,
            "warm_preferred_between_near_matches": warm_preference}


def run(output: Path, seed: int = 17) -> dict:
    if not 0 <= seed <= 1_000_000:
        raise ValueError("Seed must be between 0 and 1000000.")
    output.mkdir(parents=True, exist_ok=False)
    torch.manual_seed(seed)
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    started = time.perf_counter()
    perception = Perception()
    images, audio, labels = bank(seed + 100, 24)
    learn_perception(perception, images, audio, labels)
    frozen = {name: value.clone() for name, value in perception.state_dict().items()}
    training, _, _ = bank(seed + 6100, 12)
    held_images, held_audio, _ = bank(seed + 7100, 12)
    with torch.no_grad():
        training = perception.encode(training, "image")
        held = {"image": perception.encode(held_images, "image"),
                "audio": perception.encode(held_audio, "audio")}
    core = TemporalCore()
    train(core, training, seed + 6300)
    memory = ContextMemory()
    session = TemporalSession(core)
    generator = torch.Generator().manual_seed(seed + 7200)
    targets = torch.randint(0, 4, (4, 3), generator=generator)
    targets[0] = torch.tensor([1, 0, 0])
    # Ensure distinct expected records so a constant recall cannot pass.
    targets[:, 2] = torch.arange(4)
    now, growth = 0., []
    for profile, (history, gap) in enumerate(PROFILES):
        for repeat in range(16):
            context, signal, elapsed = observe(session, training, history, gap, repeat % 12)
            now += elapsed
            memory.write(context, signal, make_value(targets[profile]), now, .9 if profile == 0 else .2)
        growth.append({"blocks": len(memory.blocks), "bytes": memory.state_bytes()})
    evaluation_time = now + 600
    scores = evaluate(core, memory, held, targets, evaluation_time)
    reset = evaluate(core, memory, held, targets, evaluation_time, "reset_state")
    no_time = evaluate(core, memory, held, targets, evaluation_time, "remove_time")
    zero = ContextMemory()
    empty = evaluate(core, zero, held, targets, evaluation_time)
    heat = heat_checks(core, held["image"])
    # Save a continuous prefix. Query needs the current signal, not this prefix's raw inputs.
    query_session = TemporalSession(core)
    for identity in PROFILES[0][0][:-1]:
        query_session.advance(held["image"][identity * 12:identity * 12 + 1], .5)
    save_checkpoint(output / "weights.pt", perception, query_session, memory)
    _, restored_session, restored_memory = load_checkpoint(output / "weights.pt")
    restored_session.advance(held["image"][0:1], .5)
    restored = restored_memory.read(restored_session.hidden[0], held["image"][0], evaluation_time)
    report = {"seed": seed, "retrieval": scores, "reset_temporal_control": reset,
              "removed_interval_control": no_time, "empty_memory_control": empty,
              "heat_controls": heat, "growth_by_stage": growth,
              "allocated_blocks": len(memory.blocks), "capacity": memory.capacity,
              "memory_state_bytes": memory.state_bytes(), "clock": memory.clock.item(),
              "query_time": evaluation_time, "expected_query": describe(targets[0].tolist()),
              "restored_query": restored["recall"],
              "perception_unchanged": all(torch.equal(frozen[name], value)
                                          for name, value in perception.state_dict().items()),
              "elapsed_seconds": round(time.perf_counter() - started, 3),
              "scope": "temporal latent routing plus RLS weights and explicit addresses/metadata; synthetic event boundaries"}
    report["accepted"] = (min(scores["accuracy"].values()) >= .9 and scores["max_blocks_read"] <= 2
                           and max(empty["accuracy"].values()) == 0
                           and min(scores["accuracy"][name] - reset["accuracy"][name] for name in held) >= .2
                           and min(scores["accuracy"][name] - no_time["accuracy"][name] for name in held) >= .2
                           and heat["cold_relevant_beats_hot_unrelated"]
                           and heat["warm_preferred_between_near_matches"]
                           and heat["heat_after_successful_access"] > heat["heat_before_successful_access"]
                           and restored["recall"] == report["expected_query"]
                           and report["perception_unchanged"])
    examples = output / "examples"
    examples.mkdir()
    synthetic_image(0, random.Random(seed + 7300)).save(examples / "current.png")
    save_audio(examples / "current.wav", synthetic_audio(0, random.Random(seed + 7400)))
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
