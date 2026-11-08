"""Shared conditional expectations consolidated from recalled episodic weights.

Addresses route a recall; they are never used as its target. No raw examples are
stored. Expectations remain hypotheses, including after a regularity changes.
"""
from __future__ import annotations

import math

import torch
from torch import nn

from .episodic_memory import EpisodicMemory, cue_valid
from .experience_signals import FIELDS, WORDS
from .online_memory import OnlineMemory


class SemanticMemory(nn.Module):
    max_writes_per_source = 3

    @property
    def update_budget(self):
        return 4096 if self.capacity <= 128 else 110592

    def transaction_state(self):
        return {name: value.clone() for name, value in self.state_dict().items()}

    def rollback(self, state):
        self.load_state_dict(state, strict=True)

    def __init__(self, capacity: int = 64, target: int = 2, forgetting: float = .9) -> None:
        super().__init__()
        if type(capacity) is not int or not 1 <= capacity <= 4096 or type(target) is not int or not 0 <= target < 4:
            raise ValueError("Invalid semantic memory capacity/target.")
        if isinstance(forgetting, bool) or not isinstance(forgetting, (int, float)) or not math.isfinite(forgetting) or not .9 <= forgetting <= 1:
            raise ValueError("Semantic forgetting must be between .9 and 1.")
        self.capacity, self.target, self.forgetting = capacity, target, float(forgetting)
        if capacity > 128 and forgetting != 1:
            raise ValueError("Large archives currently require cumulative semantic weights; adaptive long-run precision is unvalidated.")
        # Three independent conditional models, each with four categories+bias.
        self.bank = OnlineMemory(key_size=15, value_size=4)
        self.register_buffer("versions", torch.full((capacity,), -1, dtype=torch.int64))
        self.register_buffer("clock", torch.tensor(0., dtype=torch.float64))

    def keys(self, cue: torch.Tensor) -> list[tuple[int, torch.Tensor]]:
        known = cue_valid(cue)
        fields = [field for field in range(4) if field != self.target]
        result = []
        for group, field in enumerate(fields):
            if not known[field]:
                continue
            key = torch.zeros(15, dtype=torch.float64)
            values = cue.reshape(4, 4)[field]
            key[group * 5:group * 5 + 4] = values / values.sum()
            key[group * 5 + 4] = 1
            result.append((field, key))
        return result

    @torch.no_grad()
    def consolidate(self, memory: EpisodicMemory, episode: int, now: float) -> dict:
        if memory.capacity != self.capacity or type(episode) is not int or not 0 <= episode < len(memory.blocks):
            raise ValueError("Invalid semantic consolidation source.")
        if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now) or not self.clock.item() <= now <= memory.clock:
            raise ValueError("Semantic consolidation requires a current source time.")
        block, trace = memory.blocks[episode], memory.traces[episode]
        version = int(block.revisions.sum())
        if version <= int(self.versions[episode]):
            return {"learned": False, "reason": "already consolidated"}
        cue = block.addresses[1].flatten().clone()
        cue.reshape(4, 4)[self.target] = 0
        keys = self.keys(cue)
        if not keys:
            return {"learned": False, "reason": "incomplete source cue"}
        recalled = memory.read(cue, now, window=(trace.started, trace.ended))
        if recalled["episode"] != episode or not recalled["known"][self.target]:
            return {"learned": False, "reason": "unsupported source recall"}
        if self.bank.writes.item() + len(keys) > (4096 if self.capacity <= 128 else 110592):
            raise ValueError("Semantic update budget reached; weights preserved.")
        value = torch.tensor(recalled["distributions"][self.target], dtype=torch.float64)
        self.bank.precision.div_(self.forgetting)
        for _, key in keys:
            self.bank.write(key, value)
        self.versions[episode] = version
        self.clock.fill_(now)
        return {"learned": True, "source_episode": episode, "source_revision": version,
                "target": FIELDS[self.target], "hypothesis": True}

    @torch.no_grad()
    def predict(self, cue: torch.Tensor) -> dict:
        keys = self.keys(cue)
        result = {"hypothesis": True, "target": FIELDS[self.target], "value": None,
                  "supported": False, "distribution": [0.] * 4, "confidence": 0.,
                  "variance": None, "confidence_is_calibrated": False}
        if not keys:
            return result
        fields = [field for field in range(4) if field != self.target]
        candidates = []
        for field, key in keys:
            group = fields.index(field)
            distributions = []
            for category in range(4):
                probe = torch.zeros(15, dtype=torch.float64)
                probe[group * 5 + category] = probe[group * 5 + 4] = 1
                if self.bank.variance(probe).item() <= 25:
                    probability = (self.bank.weights @ probe).clamp_min(0)
                    distributions.append(probability / probability.sum().clamp_min(1e-10))
            relevance = max((.5 * (left - right).abs().sum().item()
                             for left in distributions for right in distributions), default=0.)
            probabilities = (self.bank.weights @ key).clamp_min(0)
            probabilities /= probabilities.sum().clamp_min(1e-10)
            variance, confidence = self.bank.variance(key).item(), probabilities.max().item()
            candidates.append((relevance * confidence, field, probabilities, variance, confidence, relevance))
        candidates.sort(key=lambda item: item[0], reverse=True)
        score, field, probabilities, variance, confidence, relevance = candidates[0]
        conflict = any(score - other[0] < .05 and other[2].argmax() != probabilities.argmax()
                       for other in candidates[1:])
        supported = bool(self.bank.writes.item() and variance <= 25 and confidence >= .8 and relevance >= .35 and not conflict)
        return {**result, "supported": supported, "distribution": probabilities.tolist(),
                "confidence": confidence, "variance": variance,
                "selected_source_field": FIELDS[field], "learned_relevance": relevance,
                "value": WORDS[self.target][int(probabilities.argmax())] if supported else None}

    def snapshot(self) -> dict:
        return {"architecture": "conditional-v2", "capacity": self.capacity, "target": self.target, "forgetting": self.forgetting,
                "state": {name: value.clone() for name, value in self.state_dict().items()}}


def restore(payload: dict, memory: EpisodicMemory) -> SemanticMemory:
    if not isinstance(payload, dict) or set(payload) != {"architecture", "capacity", "target", "forgetting", "state"} or payload["architecture"] != "conditional-v2":
        raise ValueError("Invalid semantic checkpoint fields.")
    model = SemanticMemory(payload["capacity"], payload["target"], payload["forgetting"])
    if model.capacity != memory.capacity:
        raise ValueError("Semantic checkpoint capacity mismatch.")
    state, expected = payload["state"], model.state_dict()
    if not isinstance(state, dict) or set(state) != set(expected):
        raise ValueError("Invalid semantic checkpoint tensors.")
    for name, value in state.items():
        if not isinstance(value, torch.Tensor) or value.dtype != expected[name].dtype or value.shape != expected[name].shape or not torch.isfinite(value).all():
            raise ValueError("Invalid semantic checkpoint tensor type/shape/value.")
    model.load_state_dict(state, strict=True)
    if not 0 <= model.clock.item() <= memory.clock or not 0 <= model.bank.writes.item() <= (4096 if model.capacity <= 128 else 110592):
        raise ValueError("Invalid semantic clock/write counter.")
    if (model.versions < -1).any() or (model.versions > memory.revision_capacity).any() or (model.versions[len(memory.blocks):] != -1).any():
        raise ValueError("Invalid semantic source versions.")
    for index, block in enumerate(memory.blocks):
        if model.versions[index] > block.revisions.sum():
            raise ValueError("Semantic source revision comes from the future.")
    if model.bank.writes.item() < int((model.versions >= 0).sum()):
        raise ValueError("Semantic write counter disagrees with its sources.")
    covariance = model.bank.precision
    if not torch.allclose(covariance, covariance.T, atol=1e-8, rtol=1e-8) or torch.linalg.cholesky_ex(covariance).info.item() != 0:
        raise ValueError("Invalid semantic precision matrix.")
    return model
