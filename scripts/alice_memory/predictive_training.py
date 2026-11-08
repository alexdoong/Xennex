"""Longer causal curriculum for the predictor's runtime distribution."""
from __future__ import annotations

import hashlib
import json
import random
import time
from pathlib import Path

import torch

from .contracts import Action
from .crossmodal import load, prediction_scores, train_predictor
from .process_metrics import Budget, memory_usage
from .world import SyntheticWorld


@torch.no_grad()
def curriculum(perception, seed: int, count: int = 64, length: int = 128) -> tuple:
    rng = random.Random(seed)
    observations, actions, gaps, presence = [], [], [], []
    for episode in range(count):
        world = SyntheticWorld(seed + episode)
        first = world.advance(.1)[0]
        pixels, visible = [first.payload], [first.present]
        targets, intervals = [], []
        focus = 0
        # Same temporal scale as runtime, varied between trajectories, not oracle.
        gap = rng.choice((.1, .15, .2))
        for step in range(length):
            # Independent schedules prevent a recurrent clock from replacing
            # the action input, and make shuffled-action controls nondegenerate.
            phase = step % 8 if episode % 2 == 0 else rng.randrange(8)
            if phase in (0, 3, 6):
                focus = (focus + (1 if episode % 2 == 0 else rng.choice((1, 2)))) % 3
                action = Action("focus", step, world.clock, target=focus)
            elif phase in (1, 4):
                action = Action("inspect", step, world.clock)
            elif phase == 7:
                action = Action("emit", step, world.clock, signal=rng.randrange(8))
            else:
                action = Action("wait", step, world.clock)
            packets = world.advance(gap, action)
            image = packets[0]
            pixels.append(image.payload)
            visible.append(image.present)
            targets.append(focus)
            intervals.append(gap)
        encoded = perception.encode(torch.stack(pixels), "image")
        observations.append(encoded * torch.tensor(visible).float().unsqueeze(-1))
        actions.append(targets)
        gaps.append(intervals)
        presence.append(visible)
    return (torch.stack(observations), torch.tensor(actions), torch.tensor(gaps).unsqueeze(-1),
            torch.tensor(presence).float().unsqueeze(-1))


def run(output: Path, models: Path, seed: int = 17, max_seconds: float = 300) -> dict:
    if type(seed) is not int or not 0 <= seed <= 100000:
        raise ValueError("Invalid predictive training seed.")
    budget = Budget(100000, max_seconds)
    torch.manual_seed(seed)
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    output.mkdir(parents=True, exist_ok=False)
    perception, predictor = load(models)
    started = time.perf_counter()
    training = curriculum(perception, seed + 10000)
    # Different worlds from short-curriculum and failing runtime diagnostics.
    heldout = curriculum(perception, seed + 70000, 32, 256)
    before = prediction_scores(predictor, heldout)
    train_predictor(predictor, training, seed + 30000, budget, steps=1200)
    after = prediction_scores(predictor, heldout)
    shuffled = prediction_scores(predictor, heldout, shuffle_actions=True)
    reset = prediction_scores(predictor, heldout, reset=True)
    report = {"format": 8, "seed": seed, "curriculum": "128 steps; mixed scripted/random focus, dwell, inspection, replacement and dropout",
              "source_sha256": hashlib.sha256(models.read_bytes()).hexdigest(),
              "torch": str(torch.__version__), "threads": torch.get_num_threads(),
              "training_steps": 1200, "training_length": 128, "training_world_seed": seed + 10000,
              "predictor_parameters": sum(value.numel() for value in predictor.parameters()),
              "evaluation_world_seed": seed + 70000, "evaluation_length": 256,
              "before": before, "prediction": after,
              "reset_state": reset, "shuffled_actions": shuffled,
              "wall_seconds": time.perf_counter() - started, "memory": memory_usage(),
              "accepted": after["relative_improvement"] >= .2 and reset["mse"] > after["mse"] and shuffled["mse"] > after["mse"],
              "scope": "runtime distribution adaptation; supervised future pixels; frozen paired encoders; no runtime weight changes"}
    torch.save({"format": 8, "perception": perception.state_dict(), "predictor": predictor.state_dict()}, output / "models.pt")
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
