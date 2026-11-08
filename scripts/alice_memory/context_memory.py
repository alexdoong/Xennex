"""Budgeted associative blocks, indexed by temporal state with bounded access heat."""
from __future__ import annotations

import math
from pathlib import Path

import torch
from torch import nn
from torch.nn import functional as F

from .network import LATENT_SIZE, Perception
from .online_memory import OnlineMemory, describe
from .temporal_core import STATE_SIZE, TemporalSession, restore_checkpoint


class ContextMemory(nn.Module):
    """Latent addresses/metadata are explicit; experiential attributes live in RLS weights.

    Flat index costs O(blocks * STATE_SIZE); only selected blocks perform recalls.
    Heat is an access priority, unrelated to decoding temperature or true confidence.
    """
    def __init__(self, capacity: int = 16, half_life: float = 60,
                 importance_floor: float = .5) -> None:
        super().__init__()
        if type(capacity) is not int or not 1 <= capacity <= 128:
            raise ValueError("Capacity must be an integer between 1 and 128.")
        if not math.isfinite(half_life) or half_life <= 0:
            raise ValueError("Heat half-life must be positive and finite.")
        if not math.isfinite(importance_floor) or not 0 <= importance_floor <= 1:
            raise ValueError("Importance floor must be between 0 and 1.")
        self.capacity, self.half_life, self.importance_floor = capacity, half_life, importance_floor
        self.blocks = nn.ModuleList()
        self.register_buffer("addresses", torch.zeros(capacity, STATE_SIZE, dtype=torch.float64))
        for name in ("importance", "activation", "last_access", "last_observed", "observations"):
            self.register_buffer(name, torch.zeros(capacity, dtype=torch.float64))
        self.register_buffer("clock", torch.tensor(0., dtype=torch.float64))

    def context(self, value: torch.Tensor, now: float) -> torch.Tensor:
        if value.shape != (STATE_SIZE,) or not torch.isfinite(value).all() or value.norm() < 1e-10:
            raise ValueError("Expected a nonzero finite temporal context vector.")
        if not math.isfinite(now) or now < self.clock.item():
            raise ValueError("Memory time must be finite and must not precede its committed clock.")
        return F.normalize(value.double(), dim=0)

    def heat(self, now: float) -> torch.Tensor:
        count = len(self.blocks)
        age = (now - self.last_access[:count]).clamp_min(0)
        transient = self.activation[:count] * torch.exp(-math.log(2) * age / self.half_life)
        freshness = torch.exp(-math.log(2) * (now - self.last_observed[:count]).clamp_min(0) / self.half_life)
        return (self.importance_floor * self.importance[:count]
                + (1 - self.importance_floor) * (freshness + transient) * .5)

    @torch.no_grad()
    def write(self, context: torch.Tensor, signal: torch.Tensor, value: torch.Tensor,
              now: float, importance: float = .5, strength: float = 1) -> int:
        address = self.context(context, now)
        if signal.shape != (LATENT_SIZE,) or not torch.isfinite(signal).all() or signal.norm() < 1e-10:
            raise ValueError("Expected one nonzero finite perceptual signal.")
        if value.shape != (12,) or not torch.isfinite(value).all():
            raise ValueError("Expected a finite associative value of size 12.")
        if not math.isfinite(importance) or not 0 <= importance <= 1:
            raise ValueError("Importance must be between 0 and 1.")
        if not math.isfinite(strength) or not 0 < strength <= 10000:
            raise ValueError("Invalid associative write strength.")
        count = len(self.blocks)
        similarities = self.addresses[:count] @ address
        # Use the same relatedness floor for consolidation and retrieval.
        novel = count == 0 or similarities.max().item() < .85
        if novel and count == self.capacity:
            raise ValueError("Memory capacity reached; existing blocks were preserved.")
        if novel:
            self.blocks.append(OnlineMemory(key_size=LATENT_SIZE))
        index = count if novel else similarities.argmax().item()
        self.blocks[index].write(signal, value, strength)
        seen = self.observations[index].item()
        self.addresses[index].copy_(F.normalize(self.addresses[index] * seen + address, dim=0))
        self.observations[index] += 1
        self.importance[index] = max(self.importance[index].item(), importance)
        self.activation[index] = 1
        self.last_access[index] = now
        self.last_observed[index] = now
        self.clock.fill_(now)
        return index

    @torch.no_grad()
    def read(self, context: torch.Tensor, signal: torch.Tensor, now: float,
             activate: bool = False, budget: int = 2) -> dict:
        address = self.context(context, now)
        if signal.shape != (LATENT_SIZE,) or not torch.isfinite(signal).all():
            raise ValueError("Invalid perceptual query signal.")
        if type(budget) is not int or not 1 <= budget <= 2:
            raise ValueError("Read budget must be one or two associative blocks.")
        count = len(self.blocks)
        result = {"recall": None, "block": None, "blocks_read": 0, "addresses_compared": count}
        if count == 0:
            return result
        relevance = self.addresses[:count] @ address
        # Heat only breaks near matches; it cannot admit unrelated contexts.
        eligible = (relevance >= .85) & (relevance >= relevance.max() - .03)
        scores = relevance + .15 * self.heat(now)
        candidates = torch.where(eligible)[0]
        ranked = candidates[torch.argsort(scores[candidates], descending=True)][:budget]
        for index in ranked.tolist():
            result["blocks_read"] += 1
            variance = self.blocks[index].variance(signal).item()
            if variance > 25:
                continue
            prediction = self.blocks[index].recall(signal).tolist()
            result.update(recall=describe(prediction), block=index,
                          relevance=relevance[index].item(), heat=self.heat(now)[index].item(),
                          importance=self.importance[index].item(),
                          freshness=torch.exp(-math.log(2) * (now - self.last_observed[index]) / self.half_life).item(),
                          reactivation=(self.activation[index] * torch.exp(
                              -math.log(2) * (now - self.last_access[index]) / self.half_life)).item())
            if activate:
                age = now - self.last_access[index].item()
                cooled = self.activation[index].item() * math.exp(-math.log(2) * age / self.half_life)
                self.activation[index] = min(1, cooled + .25)
                self.last_access[index] = now
                self.clock.fill_(now)
            return result
        return result

    def state_bytes(self) -> int:
        return sum(value.numel() * value.element_size() for value in self.state_dict().values())


def save_checkpoint(path: Path, perception: Perception, session: TemporalSession,
                    memory: ContextMemory) -> None:
    temporal = {"format": 3, "perception": perception.state_dict(), "core": session.core.state_dict(),
                "hidden": session.hidden, "since_observation": session.since_observation,
                "observations": session.observations}
    torch.save({"format": 5, "temporal": temporal, "count": len(memory.blocks),
                "capacity": memory.capacity, "half_life": memory.half_life,
                "importance_floor": memory.importance_floor, "memory": memory.state_dict()}, path)


def load_checkpoint(path: Path) -> tuple[Perception, TemporalSession, ContextMemory]:
    if path.stat().st_size > 2_000_000:
        raise ValueError("Context-memory checkpoint exceeds the size limit.")
    payload = torch.load(path, map_location="cpu", weights_only=True)
    fields = {"format", "temporal", "count", "capacity", "half_life", "importance_floor", "memory"}
    if not isinstance(payload, dict) or set(payload) != fields or payload["format"] != 5:
        raise ValueError("Invalid context-memory checkpoint format.")
    memory = ContextMemory(payload["capacity"], payload["half_life"], payload["importance_floor"])
    count = payload["count"]
    if type(count) is not int or not 0 <= count <= memory.capacity:
        raise ValueError("Invalid associative block count.")
    memory.blocks.extend(OnlineMemory(key_size=LATENT_SIZE) for _ in range(count))
    memory.load_state_dict(payload["memory"], strict=True)
    if any(not torch.isfinite(value).all() for value in memory.state_dict().values()):
        raise ValueError("Context memory contains non-finite values.")
    if (memory.clock.item() < 0 or (memory.importance < 0).any() or (memory.importance > 1).any()
            or (memory.activation < 0).any() or (memory.activation > 1).any()
            or (memory.last_access < 0).any() or (memory.last_access > memory.clock).any()
            or (memory.last_observed < 0).any() or (memory.last_observed > memory.clock).any()
            or (memory.observations[:count] < 1).any()):
        raise ValueError("Invalid context-memory metadata.")
    if count and not torch.allclose(memory.addresses[:count].norm(dim=1), torch.ones(count).double(), atol=1e-6):
        raise ValueError("Invalid context-memory address norms.")
    for block in memory.blocks:
        if (not torch.allclose(block.precision, block.precision.T, atol=1e-8, rtol=1e-8)
                or torch.linalg.cholesky_ex(block.precision).info.item() != 0 or block.writes.item() < 1):
            raise ValueError("Invalid associative state.")
    perception, session = restore_checkpoint(payload["temporal"])
    return perception, session, memory
