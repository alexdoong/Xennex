"""Learned short/long anticipation for the current 32-dimensional perception.

Forecasts are hypotheses. They never overwrite autobiographical facts.
"""
from __future__ import annotations

import math

import torch
from torch import nn
from torch.nn import functional as F

from .contracts import interval


def action_features(code: int | None = None, field: int = 0) -> torch.Tensor:
    if type(field) is not int or not 0 <= field < 4 or (code is not None and (type(code) is not int or not 0 <= code < 4)):
        raise ValueError("Invalid temporal motor command.")
    values = torch.zeros(9)
    if code is not None:
        values[code] = 1
        values[4 + field] = 1
        values[8] = 1
    return values


class Temporal32(nn.Module):
    def __init__(self, kind: str = "multi") -> None:
        super().__init__()
        if kind not in ("multi", "gru", "multi-gru-v1", "gru-v1"):
            raise ValueError("Unknown 32-dimensional temporal architecture.")
        self.kind = kind
        if kind in ("multi", "multi-gru-v1"):
            self.fast = nn.GRUCell(34, 32)
            self.slow = nn.Linear(32, 32, bias=False) if kind == "multi" else nn.GRUCell(34, 32)
            if kind == "multi":
                nn.init.eye_(self.slow.weight)
            self.gate = nn.Linear(98, 32)
            nn.init.constant_(self.gate.bias, -1)
            self.log_tau = nn.Parameter(torch.cat((torch.full((32,), math.log(2.)), torch.full((32,), math.log(120.)))))
            self.head = nn.Linear(73, 64)
        else:
            size = 48 if kind == "gru" else 60
            self.fast = nn.GRUCell(34, size)
            self.log_tau = nn.Parameter(torch.linspace(math.log(2.), math.log(120.), size))
            self.head = nn.Linear(size + 9, 64)

    def initial(self, batch: int) -> torch.Tensor:
        return torch.zeros(batch, len(self.log_tau))

    def advance(self, latent: torch.Tensor, hidden: torch.Tensor, elapsed: torch.Tensor,
                present: torch.Tensor) -> torch.Tensor:
        tau = self.log_tau.exp().clamp(.1, 10000)
        decayed = hidden * torch.exp(-elapsed / tau)
        values = torch.cat((latent * present, torch.log1p(elapsed), present), -1)
        if self.kind in ("gru", "gru-v1"):
            changed = self.fast(values, decayed)
            return present * changed + (1 - present) * decayed
        fast, slow = decayed[:, :32], decayed[:, 32:]
        changed_fast = self.fast(values, fast)
        gate = torch.sigmoid(self.gate(torch.cat((values, changed_fast, slow), -1)))
        candidate = self.slow(latent) if self.kind == "multi" else self.slow(values, slow)
        changed_slow = slow + gate * (candidate - slow)
        changed = torch.cat((changed_fast, changed_slow), -1)
        return present * changed + (1 - present) * decayed

    def forecast(self, hidden: torch.Tensor, action: torch.Tensor) -> torch.Tensor:
        return F.normalize(self.head(torch.cat((hidden, action), -1)).reshape(-1, 2, 32), dim=-1)

    def sequence(self, signals: torch.Tensor, commands: torch.Tensor, gaps: torch.Tensor,
                 presence: torch.Tensor, reset: bool = False) -> torch.Tensor:
        hidden, results = self.initial(len(signals)), []
        for step in range(signals.shape[1]):
            if reset:
                hidden = torch.zeros_like(hidden)
            hidden = self.advance(signals[:, step], hidden, gaps[:, step], presence[:, step])
            results.append(self.forecast(hidden, commands[:, step]))
        return torch.stack(results, 1)


class Temporal32Session:
    def __init__(self, core: Temporal32, clock: float = 0.) -> None:
        self.core = core.eval().requires_grad_(False)
        self.hidden = core.initial(1)
        self.clock = clock
        self.observations = 0
        self.last_prediction = torch.zeros(1, 2, 32)
        self.last_error = 0.
        self.command = torch.zeros(1, 9)
        with torch.no_grad():
            self.last_prediction = self.core.forecast(self.hidden, self.command)

    @torch.no_grad()
    def advance(self, latent: torch.Tensor | None, elapsed: float) -> None:
        interval(elapsed)
        if latent is not None and (not isinstance(latent, torch.Tensor) or latent.shape != (32,)
                or latent.dtype != torch.float32 or latent.device.type != "cpu" or not torch.isfinite(latent).all()):
            raise ValueError("Temporal perception requires a finite CPU float latent of size 32.")
        if latent is not None and not .99 <= latent.norm().item() <= 1.01:
            raise ValueError("Temporal perception requires a normalized latent.")
        if latent is not None and self.observations:
            self.last_error = (self.last_prediction[0, 0] - latent).square().mean().item()
        signal = torch.zeros(1, 32) if latent is None else latent.unsqueeze(0)
        self.hidden = self.core.advance(signal, self.hidden, torch.tensor([[elapsed]]), torch.tensor([[float(latent is not None)]]))
        self.clock += elapsed
        self.observations += int(latent is not None)
        if latent is not None:
            self.command.zero_()
        self.last_prediction = self.core.forecast(self.hidden, self.command)

    @torch.no_grad()
    def predict(self, code: int | None = None, field: int = 0) -> torch.Tensor:
        self.command = action_features(code, field).unsqueeze(0)
        self.last_prediction = self.core.forecast(self.hidden, self.command)
        return self.last_prediction.clone()

    def snapshot(self) -> dict:
        return {"hidden": self.hidden.clone(), "clock": self.clock, "observations": self.observations,
                "last_prediction": self.last_prediction.clone(), "last_error": self.last_error,
                "command": self.command.clone()}
