"""Learned interpretations of synthetic scenes and sounds with unknown regions."""
from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F

from .process_metrics import Budget
from .signals import audio_features


class ExperiencePerception(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.vision = nn.Sequential(nn.Conv2d(3, 12, 3, stride=2, padding=1), nn.GELU(),
                                    nn.Conv2d(12, 20, 3, stride=2, padding=1), nn.GELU(),
                                    nn.AdaptiveAvgPool2d(2), nn.Flatten(), nn.Linear(80, 32))
        self.audio = nn.Sequential(nn.Linear(257, 96), nn.GELU(), nn.Linear(96, 32))
        self.head = nn.Linear(32, 20)

    def encode(self, values: torch.Tensor, modality: str) -> torch.Tensor:
        if modality not in ("image", "audio"):
            raise ValueError("Unknown experience modality.")
        return F.normalize((self.vision if modality == "image" else self.audio)(values), dim=-1)

    def probabilities(self, latent: torch.Tensor) -> torch.Tensor:
        return self.head(latent).reshape(*latent.shape[:-1], 4, 5).softmax(-1)


def train(model: ExperiencePerception, data: tuple, seed: int, budget: Budget,
          steps: int = 1200) -> None:
    images, sound, labels = data
    audio = audio_features(sound)
    generator = torch.Generator().manual_seed(seed)
    optimizer = torch.optim.Adam(model.parameters(), lr=.004)
    for step in range(steps):
        budget.check(step)
        indices = torch.randint(len(images), (64,), generator=generator)
        visual, acoustic = model.encode(images[indices], "image"), model.encode(audio[indices], "audio")
        target = labels[indices].flatten()
        visual_loss = F.cross_entropy(model.head(visual).reshape(-1, 5), target)
        acoustic_loss = F.cross_entropy(model.head(acoustic).reshape(-1, 5), target)
        # Supervised concepts prevent collapse; pair correspondence is supplied.
        loss = visual_loss + acoustic_loss + .2 * (visual - acoustic).square().mean()
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
    model.eval().requires_grad_(False)


def semantic(probabilities: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    if probabilities.shape != (4, 5) or not torch.isfinite(probabilities).all():
        raise ValueError("Expected four finite perceptual distributions.")
    confidence, category = probabilities.max(-1)
    known = (confidence >= .8) & (category < 4)
    cue = probabilities[:, :4] * known.unsqueeze(-1)
    return cue.flatten().double(), known


@torch.no_grad()
def evaluate(model: ExperiencePerception, data: tuple) -> dict:
    images, sound, labels = data
    result = {}
    for name, values in (("image", images), ("audio", audio_features(sound))):
        probabilities = model.probabilities(model.encode(values, name))
        confidence, prediction = probabilities.max(-1)
        known = (prediction < 4) & (confidence >= .8)
        present = labels < 4
        correct = (prediction == labels) & known & present
        result[name] = {"known_field_recall": correct.sum().item() / max(present.sum().item(), 1),
                        "false_known_on_missing": (known & ~present).sum().item() / max((~present).sum().item(), 1),
                        "category_accuracy": (prediction == labels).float().mean().item(),
                        "latent_variance": model.encode(values, name).var(0).mean().item()}
    return result
