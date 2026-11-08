"""Two simultaneous localized synthetic sources, no speaker IDs at inference.

Visual halves and stereo channels are supplied spatial localization. This is not
blind source separation, photographs, speech, or a model of real acoustic mixing.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

import torch

from .contracts import Observation
from .experience_signals import samples


@dataclass(frozen=True)
class SceneObservation:
    modality: str
    payload: torch.Tensor
    acquired_at: float
    sequence: int
    origin: str = "environment"
    present: bool = True
    quality: float = 1.
    action_id: int | None = None

    def regions(self) -> list[Observation]:
        shape = (3, 32, 64) if self.modality == "image" else (2, 1024)
        if self.modality not in ("image", "audio") or not isinstance(self.payload, torch.Tensor) or self.payload.shape != shape:
            raise ValueError("Expected a two-region visual scene or localized stereo sound.")
        parts = [self.payload[:, :, :32], self.payload[:, :, 32:]] if self.modality == "image" else list(self.payload.unbind(0))
        packets = [Observation(self.modality, part, self.acquired_at, self.sequence,
                               self.origin, self.present, self.quality, self.action_id) for part in parts]
        for packet in packets:
            packet.validate()
        return packets


def scene(values: tuple[tuple[int, ...], tuple[int, ...]], rng: random.Random,
          masks=((True,) * 4, (True,) * 4)) -> tuple[torch.Tensor, torch.Tensor]:
    if len(values) != 2 or len(masks) != 2:
        raise ValueError("The scene curriculum has exactly two spatial regions.")
    pairs = [samples(value, rng, mask) for value, mask in zip(values, masks)]
    return torch.cat([pair[0] for pair in pairs], -1), torch.stack([pair[1] for pair in pairs])


def packets(image: torch.Tensor, audio: torch.Tensor, clock: float, sequence: int, modality="both") -> list[SceneObservation]:
    if modality not in ("both", "image", "audio"):
        raise ValueError("Unknown scene modality selection.")
    result = []
    if modality in ("both", "image"):
        result.append(SceneObservation("image", image, clock, sequence))
    if modality in ("both", "audio"):
        result.append(SceneObservation("audio", audio, clock, sequence + 1, "person"))
    return result
