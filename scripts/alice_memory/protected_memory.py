"""Periodic parameter anchoring with a learned squared-gradient sensitivity.

This is a fixed-hyperparameter research regularizer, not an implementation of
EWC's probabilistic Fisher estimate or learned retention gates.
"""
from __future__ import annotations

from pathlib import Path

import torch

from .adaptive_memory import AdaptiveMemory, number, restore as restore_adaptive
from .loop_checkpoint import atomic_write


class ProtectedMemory(AdaptiveMemory):
    def __init__(self, stability=8., period=64, sensitivity_decay=.99, **kwargs):
        super().__init__(**kwargs)
        if type(period) is not int or not 1 <= period <= 4096:
            raise ValueError("Invalid parameter consolidation period.")
        self.protection = dict(stability=number(stability, 0., 1024., "stability"), period=period,
                               sensitivity_decay=number(sensitivity_decay, 0., .9999, "sensitivity decay"))
        self.register_buffer("consolidations", torch.tensor(0, dtype=torch.int64))
        for index, parameter in enumerate(self.network.parameters()):
            self.register_buffer(f"anchor_{index}", parameter.detach().clone())
            self.register_buffer(f"sensitivity_{index}", torch.zeros_like(parameter))

    def _loss(self):
        objective = super()._loss()
        if not int(self.consolidations) or self.protection["stability"] == 0:
            return objective
        parameters = tuple(self.network.parameters())
        count = sum(parameter.numel() for parameter in parameters)
        mean = sum(getattr(self, f"sensitivity_{index}").sum() for index in range(len(parameters))) / count
        penalty = objective * 0.
        for index, parameter in enumerate(parameters):
            importance = getattr(self, f"sensitivity_{index}") / mean.clamp_min(1e-16)
            penalty = penalty + (importance * (parameter - getattr(self, f"anchor_{index}")).square()).sum() / count
        return objective + self.protection["stability"] * penalty

    def _update(self):
        parameters = tuple(self.network.parameters())
        with torch.enable_grad():
            gradients = torch.autograd.grad(super()._loss(), parameters)
        super()._update()
        with torch.no_grad():
            decay = self.protection["sensitivity_decay"]
            for index, gradient in enumerate(gradients):
                sensitivity = getattr(self, f"sensitivity_{index}")
                sensitivity.mul_(decay).add_(gradient.square(), alpha=1. - decay)
                if not torch.isfinite(sensitivity).all() or sensitivity.max().item() > 1e16:
                    raise ValueError("Invalid parameter sensitivity; prior state preserved.")
            if (int(self.writes) + 1) % self.protection["period"] == 0:
                for index, parameter in enumerate(parameters):
                    getattr(self, f"anchor_{index}").copy_(parameter)
                self.consolidations.add_(1)

    def snapshot(self):
        state = self.state_dict()
        extra = {name: value.clone() for name, value in state.items()
                 if name == "consolidations" or name.startswith(("anchor_", "sensitivity_"))}
        return {"format": 37, "adaptive": {"format": 36, "config": dict(self.config),
                                           "state": {name: value.clone() for name, value in state.items() if name not in extra}},
                "protection": dict(self.protection), "state": extra}

    def metrics(self):
        return {**super().metrics(), "protection": dict(self.protection), "consolidations": int(self.consolidations),
                "sensitivity_is_fisher": False}


def restore(payload):
    fields = {"format", "adaptive", "protection", "state"}
    if not isinstance(payload, dict) or set(payload) != fields or type(payload["format"]) is not int or payload["format"] != 37:
        raise ValueError("Invalid protected-memory checkpoint fields.")
    base = restore_adaptive(payload["adaptive"])
    protection = payload["protection"]
    if not isinstance(protection, dict) or set(protection) != {"stability", "period", "sensitivity_decay"}:
        raise ValueError("Invalid protected-memory checkpoint configuration.")
    with torch.random.fork_rng(devices=[]):
        result = ProtectedMemory(**protection, **base.config)
    extra, expected = payload["state"], result.snapshot()["state"]
    if not isinstance(extra, dict) or set(extra) != set(expected):
        raise ValueError("Invalid protected-memory checkpoint tensors.")
    for name, value in extra.items():
        if not isinstance(value, torch.Tensor) or value.device.type != "cpu" or value.dtype != expected[name].dtype or value.shape != expected[name].shape or not torch.isfinite(value).all():
            raise ValueError("Invalid protected-memory checkpoint tensor type/shape/value.")
    result.load_state_dict({**base.state_dict(), **extra}, strict=True)
    if int(result.consolidations) != int(result.writes) // result.protection["period"]:
        raise ValueError("Protected-memory consolidation counter disagrees with writes.")
    for index, _ in enumerate(result.network.parameters()):
        sensitivity = getattr(result, f"sensitivity_{index}")
        if sensitivity.min().item() < 0 or sensitivity.max().item() > 1e16 or getattr(result, f"anchor_{index}").abs().max().item() > 10000.:
            raise ValueError("Invalid protected-memory sensitivity/anchor range.")
    return result


def save(path: Path, model: ProtectedMemory):
    atomic_write(path, model.snapshot())


def load(path: Path):
    if path.stat().st_size > 4_000_000:
        raise ValueError("Protected-memory checkpoint exceeds its size limit.")
    return restore(torch.load(path, map_location="cpu", weights_only=True))
