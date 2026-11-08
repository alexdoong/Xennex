"""Typed sensor/action contracts; simulator labels are deliberately absent."""
from __future__ import annotations

import math
from dataclasses import dataclass

import torch


def interval(value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 60:
        raise ValueError("Elapsed time must be finite and between 0 and 60 seconds.")


@dataclass(frozen=True)
class Observation:
    modality: str
    payload: torch.Tensor
    acquired_at: float
    sequence: int
    origin: str = "environment"
    present: bool = True
    quality: float = 1.0
    action_id: int | None = None
    view: str = "focused"

    def validate(self) -> None:
        shapes = {"image": (3, 32, 32), "audio": (1024,)}
        if self.modality not in shapes or self.payload.shape != shapes[self.modality]:
            raise ValueError("Invalid observation modality or payload shape.")
        if self.payload.device.type != "cpu" or not self.payload.is_floating_point() or not torch.isfinite(self.payload).all():
            raise ValueError("Sensor payload must contain finite floating-point CPU samples.")
        if not math.isfinite(self.acquired_at) or self.acquired_at < 0:
            raise ValueError("Invalid acquisition time.")
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("Invalid observation sequence.")
        if self.origin not in ("environment", "person", "self") or type(self.present) is not bool:
            raise ValueError("Invalid sensor origin or presence mask.")
        if not math.isfinite(self.quality) or not 0 <= self.quality <= 1:
            raise ValueError("Invalid observation quality.")
        if self.view not in ("focused", "overview"):
            raise ValueError("Unknown sensor view.")
        if self.action_id is not None and (type(self.action_id) is not int or self.action_id < 0):
            raise ValueError("Invalid feedback action reference.")
        if self.origin == "self" and self.action_id is None:
            raise ValueError("Self feedback must identify the emitted action.")


@dataclass(frozen=True)
class Action:
    kind: str
    sequence: int
    issued_at: float
    target: int | None = None
    signal: int | None = None

    def validate(self) -> None:
        if self.kind not in ("focus", "inspect", "emit", "wait"):
            raise ValueError("Unknown simulator action.")
        if type(self.sequence) is not int or self.sequence < 0 or not math.isfinite(self.issued_at) or self.issued_at < 0:
            raise ValueError("Invalid action sequence/time.")
        if self.kind == "focus":
            if type(self.target) is not int or not 0 <= self.target < 3 or self.signal is not None:
                raise ValueError("Focus target is a spatial slot, between 0 and 2.")
            return
        if self.kind == "emit":
            if type(self.signal) is not int or not 0 <= self.signal < 8 or self.target is not None:
                raise ValueError("Emission requires a synthetic tone code between 0 and 7.")
            return
        if self.target is not None or self.signal is not None:
            raise ValueError("This action has no target or signal.")


@dataclass(frozen=True)
class StepResult:
    action: Action
    encoded: int
    stale: int
    self_feedback: int
    external_feedback: int
    hidden_norm: float
    internal_tick: bool
