"""Learn synthetic order and interval-dependent anticipation from causal streams."""
from __future__ import annotations

import json
import random
import time
from pathlib import Path

import torch
from torch.nn import functional as F

from .experiment import learn_perception
from .network import Perception
from .signals import bank, synthetic_image, synthetic_audio, save_audio
from .temporal_core import STATE_SIZE, TemporalCore, TemporalSession, save_checkpoint, load_checkpoint


def sequences(generator: torch.Generator, count: int, steps: int = 6) -> tuple:
    direction = torch.randint(0, 2, (count, 1), generator=generator) * 2 - 1
    start = torch.randint(0, 8, (count, 1), generator=generator)
    long = torch.randint(0, 2, (count, steps), generator=generator).bool()
    noise = torch.rand(count, steps, generator=generator)
    intervals = torch.where(long, 3 + noise * 3, .3 + noise * .7)
    hops = torch.where(long, 2, 1)
    positions = torch.cat((torch.zeros(count, 1, dtype=torch.int64), hops[:, :-1].cumsum(1)), 1)
    identities = (start + direction * positions) % 8
    targets = (identities + direction * hops) % 8
    return identities, intervals, targets


def observations(features: torch.Tensor, identities: torch.Tensor,
                 generator: torch.Generator) -> torch.Tensor:
    variants = torch.randint(0, 12, identities.shape, generator=generator)
    return features[identities * 12 + variants]


def train(core: TemporalCore, features: torch.Tensor, seed: int, steps: int = 1200) -> None:
    generator = torch.Generator().manual_seed(seed)
    optimizer = torch.optim.Adam(core.parameters(), lr=.004)
    for _ in range(steps):
        identities, intervals, targets = sequences(generator, 64)
        inputs = observations(features, identities, generator)
        hidden = torch.zeros(64, STATE_SIZE)
        losses = []
        for index in range(inputs.shape[1]):
            hidden = core(inputs[:, index], hidden, intervals[:, index, None])
            if index > 0:
                losses.append(F.cross_entropy(core.forecast(hidden), targets[:, index]))
        optimizer.zero_grad(set_to_none=True)
        torch.stack(losses).mean().backward()
        torch.nn.utils.clip_grad_norm_(core.parameters(), 1)
        optimizer.step()
    core.eval()


@torch.no_grad()
def evaluate(core: TemporalCore, inputs: torch.Tensor, intervals: torch.Tensor,
             targets: torch.Tensor, reset: bool = False, remove_time: bool = False) -> float:
    hidden = torch.zeros(len(inputs), STATE_SIZE)
    for index in range(inputs.shape[1]):
        previous = torch.zeros_like(hidden) if reset else hidden
        # Replace variable duration with an in-distribution constant; preserve order.
        elapsed = torch.full((len(inputs), 1), .5) if remove_time else intervals[:, index, None]
        hidden = core(inputs[:, index], previous, elapsed)
    return (core.forecast(hidden).argmax(-1) == targets[:, -1]).double().mean().item()


def probe(core: TemporalCore, anchors: torch.Tensor, history: list[int], gap: float) -> TemporalSession:
    session = TemporalSession(core)
    for index, identity in enumerate(history):
        session.advance(anchors[identity:identity + 1], gap if index == len(history) - 1 else .5)
    return session


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
    train_images, _, _ = bank(seed + 6100, 12)
    test_images, test_audio, _ = bank(seed + 6200, 12)
    with torch.no_grad():
        train_features = perception.encode(train_images, "image")
        features = {"image": perception.encode(test_images, "image"),
                    "audio": perception.encode(test_audio, "audio")}
    core = TemporalCore()
    train(core, train_features, seed + 6300)
    generator = torch.Generator().manual_seed(seed + 6400)
    identities, intervals, targets = sequences(generator, 512)
    inputs = {name: observations(values, identities, generator) for name, values in features.items()}
    alternating = torch.arange(6)[None, :, None] % 2 == 0
    inputs["mixed"] = torch.where(alternating, inputs["image"], inputs["audio"])
    scores = {name: evaluate(core, values, intervals, targets) for name, values in inputs.items()}
    reset = {name: evaluate(core, values, intervals, targets, reset=True) for name, values in inputs.items()}
    no_time = {name: evaluate(core, values, intervals, targets, remove_time=True) for name, values in inputs.items()}
    shuffled = inputs["mixed"].clone()
    shuffled[:, :-1] = shuffled[:, torch.tensor([3, 0, 4, 1, 2])]
    order_control = evaluate(core, shuffled, intervals, targets)
    probes = {}
    for name, history, gap in (("forward_short", [5, 6, 7, 0], .5),
                               ("backward_short", [3, 2, 1, 0], .5),
                               ("forward_long", [5, 6, 7, 0], 4),
                               ("backward_long", [3, 2, 1, 0], 4)):
        probes[name] = probe(core, perception.anchors, history, gap).prediction()
    prefix = probe(core, perception.anchors, [5, 6, 7], .5)
    before_missing = prefix.hidden.clone()
    prefix.advance(None, 3)
    missing_changes_state = not torch.equal(before_missing, prefix.hidden)
    save_checkpoint(output / "weights.pt", perception, prefix)
    _, restored = load_checkpoint(output / "weights.pt")
    prefix.advance(perception.anchors[0:1], 1)
    restored.advance(perception.anchors[0:1], 1)
    persistence = torch.equal(prefix.hidden, restored.hidden)
    uninterrupted = probe(core, perception.anchors, [5, 6, 7, 0], 4)
    missing_equivalent = torch.allclose(prefix.hidden, uninterrupted.hidden, atol=1e-6, rtol=1e-6)
    report = {"seed": seed, "next_signal_accuracy": scores,
              "reset_state_control": reset, "removed_interval_control": no_time,
              "shuffled_history_control": order_control, "same_current_signal_probes": probes,
              "missing_measurement_equivalent_to_elapsed_gap": missing_equivalent,
              "persistence_exact": persistence, "restored_continuation_prediction": restored.prediction(),
              "no_observation_changes_state": missing_changes_state,
              "perception_unchanged": all(torch.equal(frozen[name], value)
                                          for name, value in perception.state_dict().items()),
              "hidden_state_bytes": STATE_SIZE * 4,
              "core_parameters": sum(p.numel() for p in core.parameters()),
              "elapsed_seconds": round(time.perf_counter() - started, 3),
              "scope": "synthetic next-signal prediction; learned recurrent state, supplied elapsed time; offline training"}
    report["accepted"] = (min(scores.values()) >= .9 and
                           min(scores[name] - reset[name] for name in scores) >= .2 and
                           min(scores[name] - no_time[name] for name in scores) >= .2 and
                           scores["mixed"] - order_control >= .2 and
                           probes == {"forward_short": 1, "backward_short": 7,
                                      "forward_long": 2, "backward_long": 6} and
                           missing_equivalent and persistence and report["perception_unchanged"])
    examples = output / "examples"
    examples.mkdir()
    synthetic_image(0, random.Random(seed + 6500)).save(examples / "current.png")
    save_audio(examples / "current.wav", synthetic_audio(0, random.Random(seed + 6600)))
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
