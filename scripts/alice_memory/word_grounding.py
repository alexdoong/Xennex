"""Written symbols learn sensory meanings in weights, not in a definition map.

Symbol hashing supplies distinct keys, not linguistic semantics or LLM states.
The learned value is the existing 32-dimensional audiovisual representation.
"""
from __future__ import annotations

import hashlib
import io
import math

import torch
from torch import nn
from torch.nn import functional as F

from .experience_perception import semantic
from .online_memory import OnlineMemory
from .written_symbols import symbol

KEY_SIZE = 256
REPRESENTATION = "symbol-hash-to-sensory32-v1"


def key(value: str) -> torch.Tensor:
    value = symbol(value)
    raw = hashlib.shake_256((REPRESENTATION + ":" + value).encode("utf-8")).digest(KEY_SIZE)
    return torch.tensor([1. if byte & 1 else -1. for byte in raw], dtype=torch.float64) / math.sqrt(KEY_SIZE)


def sensory_digest(perception) -> str:
    stream = io.BytesIO()
    torch.save(perception.state_dict(), stream)
    return hashlib.sha256(stream.getvalue()).hexdigest()


class WordGrounding(nn.Module):
    def __init__(self, perception, capacity: int = 128):
        super().__init__()
        if type(capacity) is not int or not 1 <= capacity <= 128:
            raise ValueError("Invalid lexical capacity.")
        # The sensory model is owned by the mind, not duplicated in this module.
        object.__setattr__(self, "perception", perception)
        self.capacity = capacity
        self.source_digest = sensory_digest(perception)
        self.names: list[str] = []
        self.bank = OnlineMemory(KEY_SIZE, 32)
        self.register_buffer("updates", torch.zeros(capacity, dtype=torch.int64))
        self.register_buffer("learned_at", torch.full((capacity,), -1., dtype=torch.float64))
        self.register_buffer("clock", torch.tensor(0., dtype=torch.float64))

    @torch.no_grad()
    def teach(self, name: str, latent: torch.Tensor, now: float) -> dict:
        name = symbol(name)
        if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now) or now < self.clock.item():
            raise ValueError("Lexical learning requires monotonic finite time.")
        if not isinstance(latent, torch.Tensor) or latent.device.type != "cpu" or latent.dtype != torch.float32 or latent.shape != (32,) or not torch.isfinite(latent).all():
            raise ValueError("Invalid sensory meaning.")
        if not torch.isclose(latent.norm(), torch.tensor(1.), atol=1e-5):
            raise ValueError("Sensory meaning must be normalized.")
        probabilities = self.perception.probabilities(latent.unsqueeze(0))[0]
        _, known = semantic(probabilities)
        if int(known.sum()) != 1:
            raise ValueError("This lexical curriculum requires attention to one concept.")
        existing = name in self.names
        if not existing and len(self.names) >= self.capacity:
            raise ValueError("Lexical capacity reached; earlier meanings preserved.")
        if self.bank.writes.item() >= 100000:
            raise ValueError("Lexical update budget reached.")
        index = self.names.index(name) if existing else len(self.names)
        self.bank.write(key(name), latent)
        if not existing:
            self.names.append(name)
        self.updates[index] += 1
        self.learned_at[index] = now
        self.clock.fill_(now)
        return {"learned": True, "name": name, "index": index}

    @torch.no_grad()
    def lookup(self, name: str) -> dict:
        name = symbol(name)
        if name not in self.names:
            return {"supported": False, "reason": "unknown_symbol", "name": name}
        encoded = key(name)
        variance = self.bank.variance(encoded).item()
        value = self.bank.weights @ encoded
        if variance > 25 or value.norm().item() < 1e-8:
            return {"supported": False, "reason": "unlearned_weights", "name": name}
        latent = F.normalize(value.float(), dim=0)
        probabilities = self.perception.probabilities(latent.unsqueeze(0))[0]
        cue, known = semantic(probabilities)
        if int(known.sum()) != 1:
            return {"supported": False, "reason": "uncertain_meaning", "name": name}
        return {"supported": True, "name": name, "latent": latent, "cue": cue,
                "known": known, "variance": variance,
                "field": int(torch.where(known)[0][0]),
                "category": int(cue.reshape(4, 4)[known][0].argmax())}

    @torch.no_grad()
    def cue(self, names: list[str]) -> dict:
        if not isinstance(names, list) or not 1 <= len(names) <= 8:
            raise ValueError("A written cue requires one to eight symbols.")
        canonical = [symbol(name) for name in names]
        if len(set(canonical)) != len(canonical):
            raise ValueError("A written cue cannot repeat a symbol.")
        results = [self.lookup(name) for name in canonical]
        unsupported = [item["name"] for item in results if not item["supported"]]
        if unsupported:
            return {"supported": False, "reason": "unsupported_symbols", "symbols": unsupported}
        cue = torch.zeros(4, 4, dtype=torch.float64)
        for field in range(4):
            selected = [item for item in results if item["field"] == field]
            if not selected:
                continue
            if len({item["category"] for item in selected}) != 1:
                return {"supported": False, "reason": "conflicting_meanings", "field": field}
            cue[field] = torch.stack([item["cue"].reshape(4, 4)[field] for item in selected]).mean(0)
        return {"supported": True, "cue": cue.flatten(), "names": canonical,
                "joint": F.normalize(torch.stack([item["latent"] for item in results]).mean(0), dim=0)}

    def snapshot(self):
        return {"representation": REPRESENTATION, "capacity": self.capacity, "names": list(self.names),
                "source_digest": self.source_digest, "weights": self.state_dict()}


def restore(payload: dict, perception, clock: float) -> WordGrounding:
    if not isinstance(payload, dict) or set(payload) != {"representation", "capacity", "names", "source_digest", "weights"} or payload["representation"] != REPRESENTATION:
        raise ValueError("Invalid lexical checkpoint fields/representation.")
    result = WordGrounding(perception, payload["capacity"])
    if payload["source_digest"] != result.source_digest:
        raise ValueError("Lexical and sensory representations differ.")
    names = payload["names"]
    if not isinstance(names, list) or len(names) > result.capacity or any(symbol(name) != name for name in names) or len(set(names)) != len(names):
        raise ValueError("Invalid learned surface names.")
    expected = result.state_dict()
    state = payload["weights"]
    if not isinstance(state, dict) or set(state) != set(expected):
        raise ValueError("Invalid lexical tensor fields.")
    for name, value in state.items():
        if not isinstance(value, torch.Tensor) or value.dtype != expected[name].dtype or value.shape != expected[name].shape or not torch.isfinite(value).all():
            raise ValueError("Invalid lexical tensor shape/type/value.")
    result.load_state_dict(state, strict=True)
    result.names = list(names)
    size = len(names)
    if not 0 <= result.clock.item() <= clock or not 0 <= result.bank.writes.item() <= 100000 or result.updates.sum() != result.bank.writes:
        raise ValueError("Invalid lexical clocks/update counters.")
    if (result.updates[:size] < 1).any() or result.updates[size:].any() or (result.learned_at[:size] < 0).any() or (result.learned_at[:size] > result.clock).any() or (result.learned_at[size:] != -1).any():
        raise ValueError("Lexical metadata disagrees with learned names.")
    precision = result.bank.precision
    if not torch.allclose(precision, precision.T, atol=1e-8) or torch.linalg.cholesky_ex(precision).info.item() != 0:
        raise ValueError("Invalid lexical precision.")
    return result
