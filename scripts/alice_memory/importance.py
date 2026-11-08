"""Learned consequence values, distinct from memory age, access and truth.

Utility is learned online in goal-specific RLS weights. Clocks and access counts
are explicit metadata. These functional variables do not establish feelings.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import torch
from torch import nn

from .episodic_memory import EpisodicMemory, cue_valid
from .online_memory import OnlineMemory


def bounded(value: float, low: float, high: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError("Invalid bounded functional signal.")


@dataclass(frozen=True)
class Consequence:
    action_id: int
    acquired_at: float
    benefit: float
    social: float
    effort: float
    origin: str = "environment"

    def validate(self) -> None:
        if type(self.action_id) is not int or self.action_id < 1 or self.origin not in ("environment", "person"):
            raise ValueError("Consequences require an external origin and action reference.")
        bounded(self.acquired_at, 0, float("inf"))
        bounded(self.benefit, -1, 1)
        bounded(self.social, -1, 1)
        bounded(self.effort, 0, 1)


@dataclass
class FunctionalState:
    energy: float = 1.
    load: float = 0.
    novelty: float = 0.
    progress: float = 0.
    social: float = 0.
    valence: float = 0.
    activation: float = 0.
    work_units: int = 0

    def validate(self) -> None:
        for name in ("energy", "load", "novelty", "activation"):
            bounded(getattr(self, name), 0, 1)
        for name in ("progress", "social", "valence"):
            bounded(getattr(self, name), -1, 1)
        if type(self.work_units) is not int or self.work_units < 0:
            raise ValueError("Invalid internal work counter.")

    def advance(self, elapsed: float, work: int, pending: bool) -> None:
        bounded(elapsed, 0, 60)
        if type(work) is not int or not 0 <= work <= 64 or type(pending) is not bool:
            raise ValueError("Invalid internal workload.")
        # Modelled energy/work, not electricity or the OS CPU utilization.
        # Token budget: 25 modelled work units/s, with capacity for 500 units.
        # A normal 10 Hz two-sense stream is sustainable; a burst still costs.
        self.energy = min(1., max(0., self.energy + .05 * elapsed - .002 * work))
        self.load = .8 * self.load + .2 * min(1., work / 8)
        self.novelty *= math.exp(-elapsed / 5)
        self.activation = min(1., .4 * self.novelty + .4 * float(pending) + .2 * self.load)
        self.work_units += work

    def observe(self, outcome: Consequence) -> None:
        self.progress = .8 * self.progress + .2 * outcome.benefit
        self.social = .8 * self.social + .2 * outcome.social
        self.valence = math.tanh(self.progress + .5 * self.social - .25 * outcome.effort)


class Importance(nn.Module):
    def __init__(self, capacity: int) -> None:
        super().__init__()
        if type(capacity) is not int or not 1 <= capacity <= 128:
            raise ValueError("Invalid importance capacity.")
        self.capacity = capacity
        # One subspace per episode AND pending field; no global bias leaks one
        # episode's consequences into another episode or an untrained purpose.
        self.values = OnlineMemory(key_size=capacity * 4, value_size=3)
        self.register_buffer("updates", torch.zeros(capacity, 4, dtype=torch.int64))
        self.register_buffer("last_access", torch.full((capacity,), -1., dtype=torch.float64))
        self.register_buffer("accesses", torch.zeros(capacity, dtype=torch.int64))
        self.register_buffer("surprise", torch.zeros(capacity, dtype=torch.float64))

    def key(self, episode: int, field: int) -> torch.Tensor:
        if type(episode) is not int or not 0 <= episode < self.capacity or type(field) is not int or not 0 <= field < 4:
            raise ValueError("Invalid importance address.")
        key = torch.zeros(self.capacity * 4, dtype=torch.float64)
        key[episode * 4 + field] = 1
        return key

    @torch.no_grad()
    def learn(self, episode: int, field: int, outcome: Consequence) -> None:
        outcome.validate()
        key = self.key(episode, field)
        self.values.write(key, torch.tensor([outcome.benefit, outcome.social, outcome.effort], dtype=torch.float64))
        self.updates[episode, field] += 1

    @torch.no_grad()
    def access(self, episode: int, now: float) -> None:
        self.key(episode, 0)
        bounded(now, 0, float("inf"))
        if now < self.last_access[episode].item():
            raise ValueError("Memory reactivation time must be monotonic.")
        self.last_access[episode] = now
        self.accesses[episode] += 1

    @torch.no_grad()
    def observe_surprise(self, episode: int, error: float) -> None:
        self.key(episode, 0)
        bounded(error, 0, 1)
        self.surprise[episode] = .8 * self.surprise[episode] + .2 * error

    @torch.no_grad()
    def durable(self, episode: int, field: int) -> float:
        key = self.key(episode, field)
        if self.updates[episode, field] == 0:
            return 0.
        benefit, social, effort = (self.values.weights @ key).clamp(-1, 1).tolist()
        # Useful/risky consequences and sustained social feedback both matter.
        # Unpredictability alone is not a durable value or evidence of truth.
        return min(1., max(0., abs(benefit) + .5 * abs(social) - .25 * max(0., effort)))

    @torch.no_grad()
    def rank(self, memory: EpisodicMemory, cue: torch.Tensor, field: int, now: float,
             mode: str = "learned", limit: int = 2) -> list[dict]:
        known = cue_valid(cue)
        self.key(0, field)
        memory.time_valid(now)
        if memory.capacity != self.capacity or mode not in ("learned", "fixed", "surprise") or type(limit) is not int or not 1 <= limit <= 2:
            raise ValueError("Invalid salience mode or budget.")
        if not known.any():
            return []
        query = cue.reshape(4, 4).clone()
        query /= query.sum(-1, keepdim=True).clamp_min(1e-10)
        candidates = []
        for index, (block, trace) in enumerate(zip(memory.blocks, memory.traces)):
            if not block.known[1, known].all():
                continue
            relevance = (block.addresses[1, known] * query[known]).sum(-1).mean().item()
            if relevance < .85:
                continue  # Heat never licenses an irrelevant association.
            durable = self.durable(index, field)
            fresh = math.exp(-(now - trace.ended) / 10)
            accessed = self.last_access[index].item()
            reactivation = 0. if accessed < 0 else math.exp(-(now - accessed) / 5)
            score = .7 * durable + .2 * fresh + .1 * reactivation
            if mode == "fixed":
                score = .7 + .2 * fresh + .1 * reactivation
            if mode == "surprise":
                score = self.surprise[index].item()
            candidates.append({"episode": index, "score": score, "durable": durable,
                               "fresh": fresh, "reactivation": reactivation, "relevance": relevance,
                               "occurred_at": [trace.started, trace.ended], "hypothesis": True})
        # This selects an attention hypothesis. Factual retrieval keeps its own
        # ambiguity check: value must not decide who actually cooked a meal.
        return sorted(candidates, key=lambda item: (item["score"], item["episode"]), reverse=True)[:limit]
