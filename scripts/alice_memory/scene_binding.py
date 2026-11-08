"""Learned participant correspondence between perceptual concept distributions.

Teacher identity equality exists only as a loss target. Runtime never receives
labels, simulator IDs, names, activity truth, or spatial track IDs.
"""
from __future__ import annotations

import random

import torch
from torch import nn
from torch.nn import functional as F

from .experience_perception import semantic
from .experience_signals import samples
from .process_metrics import Budget
from .signals import audio_features
from .word_grounding import sensory_digest


class ParticipantBinding(nn.Module):
    def __init__(self):
        super().__init__()
        self.layers = nn.Sequential(nn.Linear(32, 64), nn.GELU(), nn.Linear(64, 1))

    def forward(self, previous: torch.Tensor, current: torch.Tensor) -> torch.Tensor:
        return self.layers(torch.cat((previous, current), -1)).squeeze(-1)


class EventBinding(ParticipantBinding):
    """Same participant/activity/context; appraisal remains separately revisable."""
    def __init__(self):
        nn.Module.__init__(self)
        self.layers = nn.Sequential(nn.Linear(32, 96), nn.GELU(), nn.Linear(96, 64),
                                    nn.GELU(), nn.Linear(64, 1))


def event_source(perception):
    return {"perception_sha256": sensory_digest(perception), "representation": "localized-two-source-events-v2"}


@torch.no_grad()
def event_data(perception, seed: int, count=1536, evaluation=False):
    if type(count) is not int or not 16 <= count <= 4096:
        raise ValueError("Event binding curriculum needs 16–4096 pairs.")
    rng = random.Random(seed)
    before, after, targets = [], [], []
    for attempt in range(count * 30):
        if len(before) == count:
            return torch.stack(before), torch.stack(after), torch.tensor(targets)
        left = tuple(rng.randrange(4) for _ in range(4))
        right = list(left)
        right[1] = rng.randrange(4)
        same = len(before) % 4 < 2
        if not same:
            field = (0, 2, 3)[(len(before) // 4) % 3]
            right[field] = (right[field] + rng.randrange(1, 4)) % 4
        held_out = (left[0] + 2 * left[2] + 3 * left[3] + right[1]) % 5 == 0
        if held_out != evaluation:
            continue
        missing = rng.choice((0, 2, 3)) if rng.random() < .1 else None
        for side, value, output in ((0, left, before), (1, tuple(right), after)):
            present = tuple(field != missing or side == 0 for field in range(4))
            image, sound = samples(value, rng, present)
            modality = rng.choice(("image", "audio"))
            raw = image.unsqueeze(0) if modality == "image" else audio_features(sound.unsqueeze(0))
            cue = semantic(perception.probabilities(perception.encode(raw, modality))[0])[0]
            output.append(cue.float())
        targets.append(float(same and missing is None))
    raise TimeoutError("Event binding curriculum exhausted its sampling budget.")


@torch.no_grad()
def data(perception, seed: int, count=1024, evaluation=False):
    rng = random.Random(seed)
    before, after, targets = [], [], []
    while len(before) < count:
        left, right = tuple(rng.randrange(4) for _ in range(4)), tuple(rng.randrange(4) for _ in range(4))
        same = len(before) % 2 == 0
        right = (*right[:2], left[2] if same else (left[2] + rng.randrange(1, 4)) % 4, right[3])
        # Withhold combinations of activity/appraisal/context, not participant classes.
        held_out = (left[0] + 2 * left[1] + 3 * right[0] + right[3]) % 5 == 0
        if held_out != evaluation:
            continue
        for value, output in ((left, before), (right, after)):
            present = tuple(field == 2 or rng.random() > .25 for field in range(4))
            image, sound = samples(value, rng, present)
            modality = rng.choice(("image", "audio"))
            raw = image.unsqueeze(0) if modality == "image" else audio_features(sound.unsqueeze(0))
            cue = semantic(perception.probabilities(perception.encode(raw, modality))[0])[0]
            output.append(cue.float())
        targets.append(float(same))
    return torch.stack(before), torch.stack(after), torch.tensor(targets)


def train(model: ParticipantBinding, values: tuple, seed: int, steps=800):
    budget = Budget(steps, 60)
    generator = torch.Generator().manual_seed(seed)
    optimizer = torch.optim.Adam(model.parameters(), lr=.004)
    previous, current, target = values
    for step in range(steps):
        budget.check(step)
        indices = torch.randint(len(target), (128,), generator=generator)
        loss = F.binary_cross_entropy_with_logits(model(previous[indices], current[indices]), target[indices])
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
    model.eval().requires_grad_(False)


@torch.no_grad()
def evaluate(model, values):
    previous, current, target = values
    probability = model(previous, current).sigmoid()
    return {"match_recall": float(((probability >= .8) & target.bool()).sum()) / max(float(target.sum()), 1),
            "false_match_rate": float(((probability >= .8) & ~target.bool()).sum()) / max(float((1 - target).sum()), 1),
            "accuracy": float(((probability >= .5) == target.bool()).float().mean()),
            "cases": len(target)}


def source(perception):
    return {"perception_sha256": sensory_digest(perception), "representation": "localized-two-source-concepts-v1"}
