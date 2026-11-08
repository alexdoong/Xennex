"""A learned event-change detector: annotated boundaries are targets only."""
from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F

from .process_metrics import Budget


class EventBoundary(nn.Module):
    def __init__(self, mask_unobserved: bool = False) -> None:
        super().__init__()
        self.mask_unobserved = mask_unobserved
        self.layers = nn.Sequential(nn.Linear(34, 32), nn.GELU(), nn.Linear(32, 1))

    def forward(self, current: torch.Tensor, previous: torch.Tensor,
                elapsed: torch.Tensor, seen: torch.Tensor) -> torch.Tensor:
        difference = (current - previous).abs()
        if self.mask_unobserved:
            common = (current.reshape(-1, 4, 4).sum(-1) > .5) & (previous.reshape(-1, 4, 4).sum(-1) > .5)
            difference *= common.unsqueeze(-1).expand(-1, -1, 4).flatten(1)
        return self.layers(torch.cat((current, difference,
                                      torch.log1p(elapsed), seen), -1)).squeeze(-1)


def train(model: EventBoundary, data: tuple, seed: int, budget: Budget, steps: int = 600) -> None:
    current, previous, elapsed, seen, target = data
    optimizer = torch.optim.Adam(model.parameters(), lr=.004)
    generator = torch.Generator().manual_seed(seed)
    positive_weight = (1 - target.mean()) / target.mean().clamp_min(.001)
    for step in range(steps):
        budget.check(step)
        indices = torch.randint(len(target), (128,), generator=generator)
        logits = model(current[indices], previous[indices], elapsed[indices], seen[indices])
        loss = F.binary_cross_entropy_with_logits(logits, target[indices], pos_weight=positive_weight)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
    model.eval().requires_grad_(False)


def score(actual: list[int], expected: list[int], tolerance: int = 1) -> dict:
    unmatched = set(expected)
    true_positive = 0
    for position in actual:
        candidates = [target for target in unmatched if abs(target - position) <= tolerance]
        if candidates:
            unmatched.remove(min(candidates, key=lambda target: abs(target - position)))
            true_positive += 1
    precision = true_positive / max(len(actual), 1)
    recall = true_positive / max(len(expected), 1)
    return {"precision": precision, "recall": recall,
            "f1": 2 * precision * recall / max(precision + recall, 1e-12),
            "predicted": len(actual), "expected": len(expected), "tolerance_steps": tolerance}
