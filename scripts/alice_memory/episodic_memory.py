"""Agent-generated episodes, partial-cue associations and directed belief revisions.

Semantic cues are learned sensory outputs. Index addresses/times/provenance are
explicit. Recalled attribute distributions live in per-episode RLS fast weights.
The finite capacity rejects overflow rather than silently overwriting episodes.
"""
from __future__ import annotations

import hashlib
import math
from contextlib import contextmanager
from dataclasses import asdict, dataclass

import torch
from torch import nn

from .experience_signals import FIELDS, WORDS
from .online_memory import OnlineMemory


def cue_valid(cue: torch.Tensor) -> torch.Tensor:
    if cue.shape != (16,) or cue.dtype != torch.float64 or not torch.isfinite(cue).all() or (cue < 0).any():
        raise ValueError("Expected a finite nonnegative double semantic cue of size 16.")
    totals = cue.reshape(4, 4).sum(-1)
    if (totals > 1.00001).any():
        raise ValueError("Cue distributions must not exceed unit mass.")
    return totals > .5


def partial_keys(cue: torch.Tensor) -> list[torch.Tensor]:
    known = cue_valid(cue)
    keys = []
    if not known.any():
        return keys
    for subset in range(16):
        mask = torch.tensor([bool(subset & (1 << field)) for field in range(4)])
        mask &= known
        value = torch.cat(((cue.reshape(4, 4) * mask.unsqueeze(-1)).flatten(), torch.ones(1, dtype=torch.float64)))
        if not any(torch.equal(value, key) for key in keys):
            keys.append(value)
    return keys


@dataclass
class EpisodeTrace:
    identifier: int
    started: float
    ended: float
    observations: int = 0


@dataclass(frozen=True)
class BeliefRevision:
    episode: int
    field: int
    learned_at: float
    source: str
    evidence_sha256: str
    previous_weights_sha256: str
    new_weights_sha256: str
    confidence: float


class EpisodeBlock(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.banks = nn.ModuleList([OnlineMemory(key_size=17, value_size=4) for _ in range(8)])
        self.register_buffer("addresses", torch.zeros(2, 4, 4, dtype=torch.float64))
        self.register_buffer("known", torch.zeros(2, 4, dtype=torch.bool))
        self.register_buffer("learned_at", torch.zeros(2, 4, dtype=torch.float64))
        self.register_buffer("revisions", torch.zeros(4, dtype=torch.int64))

    @torch.no_grad()
    def observe(self, cue: torch.Tensor, now: float) -> None:
        known = cue_valid(cue)
        keys = partial_keys(cue)
        for field in torch.where(known)[0].tolist():
            value = cue.reshape(4, 4)[field]
            value = value / value.sum()
            for view in (0, 1):
                bank = self.banks[view * 4 + field]
                if view == 0 and self.known[view, field]:
                    continue  # Initial interpretation remains the first learned one.
                if view == 1 and self.revisions[field] > 0:
                    continue  # Explicit corrections require new revision evidence.
                for key in keys:
                    bank.write(key, value)
                self.addresses[view, field] = value
                self.known[view, field] = True
                self.learned_at[view, field] = now


class EpisodicMemory(nn.Module):
    def __init__(self, capacity: int = 64) -> None:
        super().__init__()
        if type(capacity) is not int or not 1 <= capacity <= 128:
            raise ValueError("Episode capacity must be between 1 and 128.")
        self.capacity = capacity
        self.revision_capacity = 128
        self.blocks = nn.ModuleList()
        self.traces: list[EpisodeTrace] = []
        self.revision_log: list[BeliefRevision] = []
        self.clock = 0.

    def time_valid(self, now: float) -> None:
        if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now) or now < self.clock:
            raise ValueError("Episode memory time must be finite and monotonic.")

    @contextmanager
    def atomic_observations(self, episodes):
        """Commit a bounded frame together, preserving earlier learned episodes."""
        episodes = tuple(episodes)
        if hasattr(self, "_observation_targets") or any(type(index) is not int or not 0 <= index < len(self.blocks) for index in episodes):
            raise ValueError("Invalid ongoing episode address.")
        selected = set(episodes)
        count, clock = len(self.blocks), self.clock
        before = {index: ({name: value.clone() for name, value in self.blocks[index].state_dict().items()},
                          asdict(self.traces[index])) for index in selected}
        self._observation_targets = selected
        try:
            yield
        except Exception:
            self.clock = clock
            del self.blocks[count:]
            del self.traces[count:]
            for index, (state, trace) in before.items():
                self.blocks[index].load_state_dict(state)
                self.traces[index] = EpisodeTrace(**trace)
            raise
        finally:
            del self._observation_targets

    @torch.no_grad()
    def observe(self, cue: torch.Tensor, now: float, boundary: bool) -> int | None:
        if type(boundary) is not bool:
            raise ValueError("Boundary decision must be boolean.")
        return self.observe_at(cue, now, None if boundary or not self.blocks else len(self.blocks) - 1)

    @torch.no_grad()
    def observe_at(self, cue: torch.Tensor, now: float, episode: int | None = None) -> int | None:
        """Agent-selected ongoing episode; None creates an episode for a new event."""
        known = cue_valid(cue)
        self.time_valid(now)
        if episode is not None and (type(episode) is not int or not 0 <= episode < len(self.blocks)):
            raise ValueError("Invalid ongoing episode address.")
        if episode is not None and hasattr(self, "_observation_targets") and episode not in self._observation_targets:
            raise ValueError("Episode was not reserved for this observation transaction.")
        if not known.any():
            self.clock = now
            return None
        new = episode is None
        if new and len(self.blocks) == self.capacity:
            raise ValueError("Episode capacity reached; existing experiences preserved.")
        if new:
            identifier = len(self.blocks)
            self.blocks.append(EpisodeBlock())
            self.traces.append(EpisodeTrace(identifier, now, now))
        index = len(self.blocks) - 1 if new else episode
        self.blocks[index].observe(cue, now)
        self.traces[index].ended = now
        self.traces[index].observations += 1
        self.clock = now
        return index

    @torch.no_grad()
    def read(self, cue: torch.Tensor, now: float, view: str = "current",
             window: tuple[float, float] | None = None, budget: int = 2) -> dict:
        known = cue_valid(cue)
        self.time_valid(now)
        if view not in ("initial", "current") or type(budget) is not int or not 1 <= budget <= 2:
            raise ValueError("Invalid interpretation or read budget.")
        if window is not None and (not isinstance(window, tuple) or len(window) != 2 or
                                   any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in window)
                                   or not 0 <= window[0] <= window[1] <= now):
            raise ValueError("Invalid occurrence-time window.")
        result = {"episode": None, "recall": None, "known": [False] * 4,
                  "distributions": [[0.] * 4 for _ in range(4)], "blocks_read": 0,
                  "addresses_compared": len(self.blocks), "ambiguous": False, "view": view}
        if not known.any():
            return result
        side = ("initial", "current").index(view)
        candidates = self.candidates(cue, side, window)
        if not candidates:
            return result
        if len(candidates) > 1 and candidates[0][0] - candidates[1][0] < .03:
            result["ambiguous"] = True
            return result
        for relevance, index in candidates[:budget]:
            block = self.blocks[index]
            result["blocks_read"] += 1
            effective = cue.reshape(4, 4).clone()
            # Other banks have never learned keys from a corrected field value;
            # use the remaining clues / local prior after explicit index routing.
            effective[block.revisions > 0] = 0
            key = torch.cat((effective.flatten(), torch.ones(1, dtype=torch.float64)))
            distributions = []
            valid = []
            for field in range(4):
                bank = block.banks[side * 4 + field]
                probability = (bank.weights @ key).clamp_min(0)
                probability /= probability.sum().clamp_min(1e-10)
                valid.append(bool(block.known[side, field]) and bank.variance(key).item() <= 25
                             and probability.max().item() >= .8)
                distributions.append(probability.tolist())
            if not any(valid):
                continue
            result.update(episode=index, known=valid, distributions=distributions,
                          recall={FIELDS[field]: WORDS[field][int(torch.tensor(distributions[field]).argmax())]
                                  for field in range(4) if valid[field]},
                          occurred_at=[self.traces[index].started, self.traces[index].ended],
                          learned_at=block.learned_at[side].tolist(), relevance=relevance)
            return result
        return result

    def candidates(self, cue: torch.Tensor, side: int, window=None) -> list[tuple[float, int]]:
        known = cue_valid(cue)
        query = cue.reshape(4, 4)
        query = query / query.sum(-1, keepdim=True).clamp_min(1e-10)
        candidates = []
        for index, (block, trace) in enumerate(zip(self.blocks, self.traces)):
            if window is not None and (trace.ended < window[0] or trace.started > window[1]):
                continue
            if not block.known[side, known].all():
                continue
            similarity = (query[known] * block.addresses[side, known]).sum(-1).mean().item()
            if similarity >= .85:
                candidates.append((similarity, index))
        return sorted(candidates, reverse=True)

    @torch.no_grad()
    def revise(self, cue: torch.Tensor, field: int, probabilities: torch.Tensor,
               learned_at: float, window: tuple[float, float] | None = None,
               source: str = "person") -> dict:
        cue_valid(cue)
        self.time_valid(learned_at)
        if type(field) is not int or not 0 <= field < 4 or source not in ("person", "environment"):
            raise ValueError("Invalid revision field/source.")
        if probabilities.shape != (5,) or not torch.isfinite(probabilities).all() or (probabilities < 0).any() or not torch.isclose(probabilities.sum(), torch.tensor(1., dtype=probabilities.dtype), atol=1e-5):
            raise ValueError("Invalid revision distribution.")
        confidence, category = probabilities.max(-1)
        if confidence < .8 or category >= 4:
            return {"revised": False, "reason": "uncertain evidence"}
        if len(self.revision_log) >= self.revision_capacity:
            raise ValueError("Revision capacity reached; previous records preserved.")
        recall = self.read(cue, learned_at, window=window)
        index = recall["episode"]
        if index is None:
            return {"revised": False, "reason": "ambiguous or unsupported target"}
        block = self.blocks[index]
        old = block.banks[4 + field]
        if recall["known"][field] and int(torch.tensor(recall["distributions"][field]).argmax()) == category.item():
            return {"revised": False, "reason": "unchanged belief", "episode": index}
        replacement = OnlineMemory(key_size=17, value_size=4)
        address = block.addresses[1].flatten().clone()
        value = probabilities[:4].double()
        value /= value.sum()
        address.reshape(4, 4)[field] = value
        # A new current bank prevents averaging a contradiction into the old claim.
        # Initial bank stays intact; other attributes and episodes are untouched.
        for key in partial_keys(address):
            replacement.write(key, value)
        record = BeliefRevision(index, field, learned_at, source,
                                hashlib.sha256(str(probabilities.tolist()).encode()).hexdigest(),
                                hashlib.sha256(str(old.weights.tolist()).encode()).hexdigest(),
                                hashlib.sha256(str(replacement.weights.tolist()).encode()).hexdigest(), confidence.item())
        block.banks[4 + field] = replacement
        block.addresses[1, field] = value
        block.known[1, field] = True
        block.learned_at[1, field] = learned_at
        block.revisions[field] += 1
        self.revision_log.append(record)
        self.clock = learned_at
        return {"revised": True, "episode": index, "field": FIELDS[field], "record": asdict(record)}

    def metadata(self) -> dict:
        return {"capacity": self.capacity, "clock": self.clock,
                "traces": [asdict(trace) for trace in self.traces],
                "revisions": [asdict(record) for record in self.revision_log]}
