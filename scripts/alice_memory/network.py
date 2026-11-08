"""Shared perceptual space and a separate trainable parametric memory."""
from __future__ import annotations

from pathlib import Path

import torch
from torch import nn
from torch.nn import functional as F

LATENT_SIZE = 16
VOCABULARY = (
    ("Lina", "Ravi", "Nara", "Theo"),
    ("oficina", "jardim", "cozinha", "biblioteca"),
    ("dax", "nelo", "vima", "suri", "paku", "zefi", "lumo", "bira"),
)
FIELDS = ("dono", "lugar", "apelido")


class Perception(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.vision = nn.Sequential(
            nn.Conv2d(3, 8, 3, stride=2, padding=1), nn.GELU(),
            nn.Conv2d(8, 16, 3, stride=2, padding=1), nn.GELU(),
            nn.AdaptiveAvgPool2d(2), nn.Flatten(), nn.Linear(64, LATENT_SIZE))
        self.audio = nn.Sequential(nn.Linear(257, 64), nn.GELU(), nn.Linear(64, LATENT_SIZE))
        self.register_buffer("anchors", torch.eye(8, LATENT_SIZE))

    def encode(self, values: torch.Tensor, modality: str) -> torch.Tensor:
        if modality not in ("image", "audio"):
            raise ValueError("Modality must be image or audio.")
        encoder = self.vision if modality == "image" else self.audio
        return F.normalize(encoder(values), dim=-1)

    def freeze(self) -> None:
        self.eval()
        self.requires_grad_(False)


class NeuralMemory(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.layers = nn.Sequential(nn.Linear(LATENT_SIZE, 64), nn.GELU(), nn.Linear(64, 16))

    def forward(self, representation: torch.Tensor) -> tuple[torch.Tensor, ...]:
        return self.layers(representation).split((4, 4, 8), dim=-1)

    def recall(self, representation: torch.Tensor) -> torch.Tensor:
        return torch.stack([logits.argmax(dim=-1) for logits in self(representation)], dim=-1)


def save_checkpoint(path: Path, perception: Perception, memory: NeuralMemory) -> None:
    torch.save({"format": 1, "perception": perception.state_dict(),
                "memory": memory.state_dict()}, path)


def load_checkpoint(path: Path) -> tuple[Perception, NeuralMemory]:
    if path.stat().st_size > 2_000_000:
        raise ValueError("Checkpoint exceeds the size limit of this experiment.")
    payload = torch.load(path, map_location="cpu", weights_only=True)
    if not isinstance(payload, dict) or set(payload) != {"format", "perception", "memory"}:
        raise ValueError("Invalid neural-memory checkpoint.")
    if payload["format"] != 1:
        raise ValueError("Unsupported neural-memory checkpoint format.")
    perception, memory = Perception(), NeuralMemory()
    perception.load_state_dict(payload["perception"], strict=True)
    memory.load_state_dict(payload["memory"], strict=True)
    if any(not torch.isfinite(value).all() for model in (perception, memory)
           for value in model.state_dict().values()):
        raise ValueError("Checkpoint contains non-finite weights.")
    perception.freeze()
    memory.eval()
    return perception, memory


def describe(prediction: list[int]) -> dict[str, str]:
    return {field: choices[index] for field, choices, index in zip(FIELDS, VOCABULARY, prediction)}
