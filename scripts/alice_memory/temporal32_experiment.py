"""Matched-budget temporal models trained on raw sensory delayed encounters."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from pathlib import Path

import torch
from torch.nn import functional as F

from .experience_signals import samples
from .memory_actor import load as load_actor
from .process_metrics import Budget, memory_usage
from .temporal32 import Temporal32, action_features
from .signals import audio_features


def trajectory(rng: random.Random, length: int = 96) -> dict:
    mood, author, context = (rng.randrange(4) for _ in range(3))
    activity = 0
    images, sounds, actions, elapsed, visible = [], [], [], [], []
    for step in range(length + 1):
        complete = step < 3 or step == length
        image, sound = samples((activity, mood, author, context), rng, (True, True, complete, complete))
        images.append(image)
        sounds.append(sound)
        visible.append(step < 3 or step == length or rng.random() >= .1)
        elapsed.append(rng.choice((.05, .1, .2, .5, 1.)))
        field = 0 if rng.random() < .6 else rng.choice((1, 2, 3))
        code = rng.randrange(4) if rng.random() < .85 else None
        actions.append(action_features(code, field))
        if code is not None and field == 0:
            activity = code
        if step == length - 1:
            activity = 0  # Encounter returns to its original activity.
    return {"images": torch.stack(images), "sounds": torch.stack(sounds), "commands": torch.stack(actions),
            "gaps": elapsed, "presence": visible, "truth": (0, mood, author, context)}


@torch.no_grad()
def curriculum(perception, seed: int, count: int = 64, length: int = 96) -> dict:
    rng = random.Random(seed)
    inputs, commands, gaps, presence, short, long, truths = [], [], [], [], [], [], []
    for _ in range(count):
        record = trajectory(rng, length)
        images, sounds = record["images"], record["sounds"]
        actions, elapsed, visible = record["commands"], record["gaps"], record["presence"]
        visual = perception.encode(images, "image")
        acoustic = perception.encode(audio_features(sounds), "audio")
        encoded = F.normalize(visual + acoustic, dim=-1)
        inputs.append(encoded[:-1] * torch.tensor(visible[:-1]).unsqueeze(-1))
        commands.append(actions[:-1])
        gaps.append(elapsed[:-1])
        presence.append(visible[:-1])
        short.append(encoded[1:])
        long.append(encoded[-1:].expand(length, 32))
        truths.append(record["truth"])
    return {"signals": torch.stack(inputs), "commands": torch.stack(commands),
            "gaps": torch.tensor(gaps).unsqueeze(-1), "presence": torch.tensor(presence).float().unsqueeze(-1),
            "short": torch.stack(short), "long": torch.stack(long),
            "short_mask": torch.stack([torch.tensor(row[1:], dtype=torch.float32) for row in
                                      [presence_row + [True] for presence_row in presence]]).unsqueeze(-1),
            "truth": torch.tensor(truths)}


def losses(prediction: torch.Tensor, data: dict) -> tuple[torch.Tensor, torch.Tensor]:
    # Ignore the last transition where a return occurs at an undisclosed time.
    short_error = (prediction[:, :-1, 0] - data["short"][:, :-1]).square().mean(-1, keepdim=True)
    mask = data["short_mask"][:, :-1]
    short = (short_error * mask).sum() / mask.sum().clamp_min(1)
    long = (prediction[:, 3:, 1] - data["long"][:, 3:]).square().mean()
    return short, long


def train(core: Temporal32, data: dict, seed: int, budget: Budget, steps: int = 800) -> None:
    generator = torch.Generator().manual_seed(seed)
    optimizer = torch.optim.Adam(core.parameters(), lr=.003)
    for step in range(steps):
        budget.check(step)
        indices = torch.randint(len(data["signals"]), (8,), generator=generator)
        batch = {name: values[indices] for name, values in data.items()}
        predicted = core.sequence(batch["signals"], batch["commands"], batch["gaps"], batch["presence"])
        short, long = losses(predicted, batch)
        optimizer.zero_grad(set_to_none=True)
        (short + long).backward()
        torch.nn.utils.clip_grad_norm_(core.parameters(), 1)
        optimizer.step()
    core.eval().requires_grad_(False)


@torch.no_grad()
def evaluate(core: Temporal32, data: dict, perception, reset: bool = False, shuffled: bool = False) -> dict:
    command = data["commands"].roll(7, 1) if shuffled else data["commands"]
    predicted = core.sequence(data["signals"], command, data["gaps"], data["presence"], reset)
    short, long = losses(predicted, data)
    recovered = perception.probabilities(predicted[:, -2, 1]).argmax(-1)
    return {"short_mse": short.item(), "long_mse": long.item(),
            "late_author_context_accuracy": (recovered[:, 2:] == data["truth"][:, 2:]).float().mean().item()}


def run(checkpoint: Path, output: Path, seed: int, seconds: float = 600) -> dict:
    budget = Budget(100000, seconds)
    torch.set_num_threads(2)
    template = load_actor(checkpoint)
    output.mkdir(parents=True, exist_ok=False)
    training = curriculum(template.session.perception, seed + 103000, 256)
    heldout = curriculum(template.session.perception, seed + 113000, 32)
    longer = curriculum(template.session.perception, seed + 123000, 32, 192)
    models, scores = {}, {}
    started = time.perf_counter()
    for kind in ("multi", "gru"):
        torch.manual_seed(seed)
        core = Temporal32(kind)
        train(core, training, seed + 104000, budget)
        models[kind] = core
        scores[kind] = {"parameters": sum(value.numel() for value in core.parameters()),
                       "heldout": evaluate(core, heldout, template.session.perception),
                       "longer": evaluate(core, longer, template.session.perception),
                       "reset": evaluate(core, heldout, template.session.perception, reset=True),
                       "shuffled_action": evaluate(core, heldout, template.session.perception, shuffled=True)}
    gain = 1 - scores["multi"]["heldout"]["long_mse"] / scores["gru"]["heldout"]["long_mse"]
    accepted = (gain >= .1 and scores["multi"]["heldout"]["short_mse"] <= 1.05 * scores["gru"]["heldout"]["short_mse"]
                and scores["multi"]["reset"]["long_mse"] > scores["multi"]["heldout"]["long_mse"]
                and scores["multi"]["shuffled_action"]["short_mse"] > scores["multi"]["heldout"]["short_mse"]
                and scores["multi"]["heldout"]["late_author_context_accuracy"] >= .9)
    report = {"seed": seed, "training_seed": seed + 103000, "evaluation_seed": seed + 113000,
              "longer_evaluation_seed": seed + 123000, "training_steps_each": 800, "scores": scores,
              "long_gain_over_matched_gru": gain, "accepted": accepted,
              "source_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
              "wall_seconds": time.perf_counter() - started, "memory": memory_usage(),
              "scope": "paired 32-d senses; gated slow projection initialized as identity; delayed encounter and field-specific commands; future supervision; no runtime connection yet"}
    torch.save({"format": 20, "perception": template.session.perception.state_dict(),
                "models": {kind: core.state_dict() for kind, core in models.items()}, "torch_rng": torch.get_rng_state()}, output / "models.pt")
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--max-seconds", type=float, default=600)
    args = parser.parse_args()
    report = run(args.checkpoint, args.output, args.seed, args.max_seconds)
    print(json.dumps({"output": str(args.output.resolve()), "accepted": report["accepted"],
                      "gain": report["long_gain_over_matched_gru"], "scores": report["scores"]}))
    raise SystemExit(0 if report["accepted"] else 2)


if __name__ == "__main__":
    main()
