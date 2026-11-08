"""Versioned native percepts, independent of the older synthetic categories."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

import torch

REVISION = '914f7f89142e33e77833254d9c9b90c3cef7303b'
REPRESENTATION = 'embeddinggemma2-' + REVISION + '-bf16-cpu-mrl128-vision70-v1'
DIMENSION = 128
MODALITIES = ('image', 'audio', 'text')


@dataclass(frozen=True)
class NativeObservation:
    modality: str
    latent: torch.Tensor
    acquired_at: float
    sequence: int
    sample_sha256: str
    representation: str = REPRESENTATION
    origin: str = 'environment'

    def validate(self):
        if self.representation != REPRESENTATION or self.modality not in MODALITIES or self.origin not in ('environment', 'person', 'self'):
            raise ValueError("Unknown native representation/modality/origin.")
        value = self.latent
        if not isinstance(value, torch.Tensor) or value.device.type != 'cpu' or value.dtype != torch.float32 or value.shape != (DIMENSION,) or not torch.isfinite(value).all():
            raise ValueError("Native percept requires a finite float32 CPU embedding.")
        if not torch.isclose(value.norm(), torch.tensor(1.), atol=1e-5, rtol=0):
            raise ValueError("Native percept must be normalized after truncation.")
        if isinstance(self.acquired_at, bool) or not isinstance(self.acquired_at, (int, float)) or not math.isfinite(self.acquired_at) or not 0 <= self.acquired_at <= 1e12:
            raise ValueError("Invalid native acquisition time.")
        if type(self.sequence) is not int or not 0 <= self.sequence <= 1000000:
            raise ValueError("Invalid native sequence.")
        if not isinstance(self.sample_sha256, str) or re.fullmatch(r'[0-9a-f]{64}', self.sample_sha256) is None:
            raise ValueError("Invalid native source digest.")
