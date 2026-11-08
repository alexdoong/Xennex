"""Experimental linear/deep fast weights with an explicit bounded recent window.

Fixed hyperparameters, not a meta-trained Titans/ATLAS implementation. Reads use
only network weights; updates retain at most sixteen encoded key/value pairs.
"""
from __future__ import annotations

import math
from pathlib import Path

import torch
from torch import nn
from torch.nn import functional as F

from .loop_checkpoint import atomic_write


def number(value, low, high, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"Invalid adaptive-memory {name}.")
    return float(value)


class AdaptiveMemory(nn.Module):
    """Small CPU research kernel; transactional SGD, momentum and weight decay."""
    def __init__(self, key_size=12, value_size=4, architecture="mlp", hidden=32,
                 window=8, loss="mse", learning_rate=.12, momentum=.8,
                 retention=0., inner_steps=8, huber_delta=.25):
        super().__init__()
        for name, value, maximum in (("key_size", key_size, 128), ("value_size", value_size, 128),
                                     ("hidden", hidden, 128), ("window", window, 16),
                                     ("inner_steps", inner_steps, 64)):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f"Invalid adaptive-memory {name}.")
        if architecture not in ("linear", "mlp") or loss not in ("mse", "huber"):
            raise ValueError("Invalid adaptive-memory architecture/loss.")
        self.config = dict(key_size=key_size, value_size=value_size, architecture=architecture,
                           hidden=hidden, window=window, loss=loss, inner_steps=inner_steps,
                           learning_rate=number(learning_rate, 1e-6, 1., "learning rate"),
                           momentum=number(momentum, 0., .99, "momentum"),
                           retention=number(retention, 0., .01, "retention"),
                           huber_delta=number(huber_delta, 1e-6, 100., "Huber delta"))
        self.network = (nn.Linear(key_size, value_size) if architecture == "linear" else
                        nn.Sequential(nn.Linear(key_size, hidden), nn.GELU(), nn.Linear(hidden, value_size)))
        self.network.double()
        for index, parameter in enumerate(self.network.parameters()):
            self.register_buffer(f"velocity_{index}", torch.zeros_like(parameter))
        self.register_buffer("keys", torch.zeros(window, key_size, dtype=torch.float64))
        self.register_buffer("values", torch.zeros(window, value_size, dtype=torch.float64))
        self.register_buffer("strengths", torch.zeros(window, dtype=torch.float64))
        self.register_buffer("writes", torch.tensor(0, dtype=torch.int64))
        self.register_buffer("cursor", torch.tensor(0, dtype=torch.int64))
        self.register_buffer("count", torch.tensor(0, dtype=torch.int64))
        self.register_buffer("clock", torch.tensor(0., dtype=torch.float64))

    def _vector(self, value, size):
        if not isinstance(value, torch.Tensor) or value.device.type != "cpu" or value.dtype not in (torch.float32, torch.float64) or value.shape != (size,) or not torch.isfinite(value).all() or value.abs().max().item() > 100.:
            raise ValueError("Invalid adaptive-memory vector; use bounded finite CPU floats.")
        return value.detach().double().clone()

    def _loss(self):
        count = int(self.count)
        prediction = self.network(self.keys[:count])
        losses = ((prediction - self.values[:count]).square() if self.config["loss"] == "mse" else
                  F.huber_loss(prediction, self.values[:count], reduction="none", delta=self.config["huber_delta"]))
        weights = self.strengths[:count]
        return (losses.mean(-1) * weights).sum() / weights.sum()

    def _update(self):
        parameters = tuple(self.network.parameters())
        # Enable gradients even when a consolidating caller itself uses no_grad.
        with torch.enable_grad():
            for _ in range(self.config["inner_steps"]):
                objective = self._loss()
                gradients = torch.autograd.grad(objective, parameters)
                with torch.no_grad():
                    for index, (parameter, gradient) in enumerate(zip(parameters, gradients)):
                        velocity = getattr(self, f"velocity_{index}")
                        velocity.mul_(self.config["momentum"]).add_(gradient)
                        parameter.mul_(1. - self.config["retention"]).add_(velocity, alpha=-self.config["learning_rate"])
                        if not torch.isfinite(parameter).all() or parameter.abs().max().item() > 10000. or not torch.isfinite(velocity).all() or velocity.abs().max().item() > 1e8:
                            raise ValueError("Adaptive-memory update diverged; prior state preserved.")

    def write(self, key, value, now, strength=1.):
        key = self._vector(key, self.config["key_size"])
        value = self._vector(value, self.config["value_size"])
        now = number(now, self.clock.item(), 1e12, "time")
        strength = number(strength, 1e-6, 1., "strength")
        if int(self.writes) >= 100000:
            raise ValueError("Adaptive-memory write budget reached; weights preserved.")
        before = {name: tensor.clone() for name, tensor in self.state_dict().items()}
        try:
            with torch.no_grad():
                position = int(self.cursor)
                self.keys[position].copy_(key)
                self.values[position].copy_(value)
                self.strengths[position] = strength
                self.cursor.fill_((position + 1) % self.config["window"])
                self.count.fill_(min(int(self.count) + 1, self.config["window"]))
            self._update()
            self.writes.add_(1)
            self.clock.fill_(now)
        except BaseException:
            self.load_state_dict(before, strict=True)
            raise

    @torch.no_grad()
    def read(self, key):
        key = self._vector(key, self.config["key_size"])
        return self.network(key).detach().clone()

    @torch.no_grad()
    def clear_working_context(self, reset_momentum=True):
        if type(reset_momentum) is not bool:
            raise ValueError("Use an explicit boolean when clearing momentum.")
        self.keys.zero_()
        self.values.zero_()
        self.strengths.zero_()
        self.count.zero_()
        self.cursor.zero_()
        if reset_momentum:
            for index, _ in enumerate(self.network.parameters()):
                getattr(self, f"velocity_{index}").zero_()

    def snapshot(self):
        return {"format": 36, "config": dict(self.config),
                "state": {name: value.clone() for name, value in self.state_dict().items()}}

    def metrics(self):
        parameters = sum(value.numel() for value in self.network.parameters())
        tensors = sum(value.numel() * value.element_size() for value in self.state_dict().values())
        return {"parameters": parameters, "state_tensor_bytes": tensors,
                "working_context_bytes": sum(value.numel() * value.element_size() for value in (self.keys, self.values, self.strengths)),
                "working_context_count": int(self.count), "writes": int(self.writes),
                "read_uses_working_context": False}


def restore(payload):
    if not isinstance(payload, dict) or set(payload) != {"format", "config", "state"} or type(payload["format"]) is not int or payload["format"] != 36:
        raise ValueError("Invalid adaptive-memory checkpoint fields.")
    config = payload["config"]
    fields = {"key_size", "value_size", "architecture", "hidden", "window", "loss", "learning_rate", "momentum", "retention", "inner_steps", "huber_delta"}
    if not isinstance(config, dict) or set(config) != fields:
        raise ValueError("Invalid adaptive-memory checkpoint configuration.")
    with torch.random.fork_rng(devices=[]):
        model = AdaptiveMemory(**config)
    state, expected = payload["state"], model.state_dict()
    if not isinstance(state, dict) or set(state) != set(expected):
        raise ValueError("Invalid adaptive-memory checkpoint tensors.")
    for name, value in state.items():
        if not isinstance(value, torch.Tensor) or value.device.type != "cpu" or value.dtype != expected[name].dtype or value.shape != expected[name].shape or not torch.isfinite(value).all():
            raise ValueError("Invalid adaptive-memory checkpoint tensor type/shape/value.")
    model.load_state_dict(state, strict=True)
    writes, count, cursor = int(model.writes), int(model.count), int(model.cursor)
    window = model.config["window"]
    if not 0 <= writes <= 100000 or not 0 <= count <= min(writes, window) or not 0 <= cursor < window or (count < window and cursor != count) or not 0 <= model.clock.item() <= 1e12 or (writes == 0 and model.clock.item() != 0):
        raise ValueError("Invalid adaptive-memory checkpoint counters.")
    if model.keys.abs().max() > 100 or model.values.abs().max() > 100 or (model.strengths[:count] < 1e-6).any() or (model.strengths[:count] > 1).any():
        raise ValueError("Invalid adaptive-memory checkpoint working context.")
    if any(value[count:].count_nonzero().item() for value in (model.keys, model.values, model.strengths)):
        raise ValueError("Invalid adaptive-memory unused working context.")
    if any(value.abs().max().item() > 10000. for value in model.network.parameters()):
        raise ValueError("Invalid adaptive-memory checkpoint parameter range.")
    if any(getattr(model, f"velocity_{index}").abs().max().item() > 1e8 for index, _ in enumerate(model.network.parameters())):
        raise ValueError("Invalid adaptive-memory checkpoint momentum range.")
    return model


def save(path: Path, model: AdaptiveMemory):
    atomic_write(path, model.snapshot())


def load(path: Path):
    if path.stat().st_size > 2_000_000:
        raise ValueError("Adaptive-memory checkpoint exceeds its size limit.")
    return restore(torch.load(path, map_location="cpu", weights_only=True))


@torch.no_grad()
def recalled_pair(memory, episode, now, target=2):
    """Derive supervision from recalled weights, never the target route address."""
    if type(episode) is not int or not 0 <= episode < len(memory.blocks) or type(target) is not int or not 0 <= target < 4:
        raise ValueError("Invalid adaptive-memory source episode/target.")
    number(now, memory.clock, memory.clock, "source time")
    block, trace = memory.blocks[episode], memory.traces[episode]
    cue = block.addresses[1].flatten().clone()
    cue.reshape(4, 4)[target] = 0
    recalled = memory.read(cue, now, window=(trace.started, trace.ended))
    if recalled["episode"] != episode or not all(recalled["known"]):
        return None
    distributions = torch.tensor(recalled["distributions"], dtype=torch.float64)
    fields = [field for field in range(4) if field != target]
    return {"key": distributions[fields].flatten(), "value": distributions[target].clone(),
            "source_episode": episode, "source_revision": int(block.revisions.sum())}
