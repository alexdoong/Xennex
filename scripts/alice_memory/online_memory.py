"""Finite associative memory updated from one observation at a time by RLS."""
from __future__ import annotations

import math
from pathlib import Path

import torch
from torch import nn
from torch.nn import functional as F

from .network import LATENT_SIZE, Perception

EPISODES = 4
VIEWS = ("initial", "current")
KEY_SIZE = LATENT_SIZE * EPISODES * len(VIEWS)
FIELDS = ("atividade", "impressao", "autor")
VOCABULARY = (("digitar", "comer", "assistir", "jogar"),
              ("agradavel", "neutra", "barulhenta", "interessante"),
              ("pai", "mae", "colega", "usuario"))


def make_key(representation: torch.Tensor, episode: int, view: str) -> torch.Tensor:
    if episode not in range(EPISODES) or view not in VIEWS:
        raise ValueError("Use an episode from 0 to 3 and initial or current view.")
    if representation.shape[-1] != LATENT_SIZE:
        raise ValueError("Invalid perceptual representation.")
    context = torch.zeros(EPISODES * len(VIEWS), dtype=torch.float64)
    context[episode * len(VIEWS) + VIEWS.index(view)] = 1
    return (representation.double().unsqueeze(-1) * context).flatten(-2)


def make_value(attributes: torch.Tensor) -> torch.Tensor:
    if attributes.shape != (3,) or attributes.dtype != torch.int64:
        raise ValueError("Supply three integer attribute indices.")
    if not ((attributes >= 0) & (attributes < 4)).all():
        raise ValueError("Attribute indices must be between 0 and 3.")
    return F.one_hot(attributes, num_classes=4).flatten().double()


class OnlineMemory(nn.Module):
    """Fast weights plus inverse covariance; no stored observations or labels.

    Contexts occupy separate subspaces by design. This reduces interference in
    this controlled experiment; it is not an open-ended episodic architecture.
    """
    def __init__(self, key_size: int = KEY_SIZE, value_size: int = 12) -> None:
        super().__init__()
        self.register_buffer("weights", torch.zeros(value_size, key_size, dtype=torch.float64))
        self.register_buffer("precision", torch.eye(key_size, dtype=torch.float64) * 1000)
        self.register_buffer("writes", torch.tensor(0, dtype=torch.int64))

    @torch.no_grad()
    def write(self, key: torch.Tensor, value: torch.Tensor, strength: float = 1) -> None:
        if key.shape != (self.weights.shape[1],) or value.shape != (self.weights.shape[0],):
            raise ValueError("Invalid memory key or value shape.")
        if not torch.isfinite(key).all() or not torch.isfinite(value).all():
            raise ValueError("Memory input must be finite.")
        if not math.isfinite(strength) or not 0 < strength <= 10000:
            raise ValueError("Write strength must be finite, positive and at most 10000.")
        key, value = key.double(), value.double()
        projected = self.precision @ key
        denominator = 1 / strength + key @ projected
        error = value - self.weights @ key
        self.weights.add_(torch.outer(error, projected / denominator))
        self.precision.sub_(torch.outer(projected, projected) / denominator)
        self.precision.copy_((self.precision + self.precision.T) * .5)
        self.writes.add_(1)

    def recall(self, keys: torch.Tensor) -> torch.Tensor:
        logits = keys.double() @ self.weights.T
        return logits.reshape(*logits.shape[:-1], 3, 4).argmax(dim=-1)

    def variance(self, keys: torch.Tensor) -> torch.Tensor:
        keys = keys.double()
        return ((keys @ self.precision) * keys).sum(dim=-1)


def describe(prediction: list[int]) -> dict[str, str]:
    return {field: words[index] for field, words, index in zip(FIELDS, VOCABULARY, prediction)}


def save_checkpoint(path: Path, perception: Perception, memory: OnlineMemory) -> None:
    torch.save({"format": 2, "perception": perception.state_dict(),
                "memory": memory.state_dict()}, path)


def load_checkpoint(path: Path) -> tuple[Perception, OnlineMemory]:
    if path.stat().st_size > 2_000_000:
        raise ValueError("Checkpoint exceeds the size limit of this experiment.")
    payload = torch.load(path, map_location="cpu", weights_only=True)
    if not isinstance(payload, dict) or set(payload) != {"format", "perception", "memory"}:
        raise ValueError("Invalid online-memory checkpoint.")
    if payload["format"] != 2:
        raise ValueError("Unsupported online-memory checkpoint format.")
    perception, memory = Perception(), OnlineMemory()
    perception.load_state_dict(payload["perception"], strict=True)
    memory.load_state_dict(payload["memory"], strict=True)
    if any(not torch.isfinite(value).all() for model in (perception, memory)
           for value in model.state_dict().values()):
        raise ValueError("Checkpoint contains non-finite weights.")
    if not torch.allclose(memory.precision, memory.precision.T, atol=1e-8, rtol=1e-8):
        raise ValueError("Invalid precision matrix symmetry.")
    if torch.linalg.cholesky_ex(memory.precision).info.item() != 0 or memory.writes.item() < 0:
        raise ValueError("Invalid precision matrix or write count.")
    perception.freeze()
    memory.eval()
    return perception, memory
