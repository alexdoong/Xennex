"""Exact one-hot RLS with a diagonal covariance rather than a dense square."""
from __future__ import annotations

import math

import torch
from torch import nn

from .importance import Importance


class DiagonalBank(nn.Module):
    def __init__(self, size):
        super().__init__()
        self.register_buffer("weights", torch.zeros(3, size, dtype=torch.float64))
        self.register_buffer("precision", torch.full((size,), 1000., dtype=torch.float64))
        self.register_buffer("writes", torch.tensor(0, dtype=torch.int64))

    @torch.no_grad()
    def write_index(self, index, value):
        projected = self.precision[index].clone()
        gain = projected / (1 + projected)
        self.weights[:, index].add_((value - self.weights[:, index]) * gain)
        self.precision[index].sub_(projected * gain)
        self.writes.add_(1)


class DiagonalImportance(Importance):
    def __init__(self, capacity):
        if type(capacity) is not int or not 1 <= capacity <= 4096:
            raise ValueError("Invalid diagonal importance capacity.")
        super().__init__(min(capacity, 128))
        self.capacity = capacity
        self.values = DiagonalBank(capacity * 4)
        self.updates = torch.zeros(capacity, 4, dtype=torch.int64)
        self.last_access = torch.full((capacity,), -1., dtype=torch.float64)
        self.accesses = torch.zeros(capacity, dtype=torch.int64)
        self.surprise = torch.zeros(capacity, dtype=torch.float64)

    def index(self, episode, field):
        if type(episode) is not int or not 0 <= episode < self.capacity or type(field) is not int or not 0 <= field < 4:
            raise ValueError("Invalid diagonal importance address.")
        return episode * 4 + field

    def key(self, episode, field):
        index = self.index(episode, field)
        key = torch.zeros(self.capacity * 4, dtype=torch.float64)
        key[index] = 1
        return key

    @torch.no_grad()
    def learn(self, episode, field, outcome):
        outcome.validate()
        index = self.index(episode, field)
        value = torch.tensor([outcome.benefit, outcome.social, outcome.effort], dtype=torch.float64)
        self.values.write_index(index, value)
        self.updates[episode, field] += 1

    def durable(self, episode, field):
        index = self.index(episode, field)
        if self.updates[episode, field] == 0:
            return 0.
        benefit, social, effort = self.values.weights[:, index].clamp(-1, 1).tolist()
        return min(1., max(0., abs(benefit) + .5 * abs(social) - .25 * max(0., effort)))

    @torch.no_grad()
    def rank(self, memory, cue, field, now, mode="learned", limit=2):
        self.index(0, field)
        memory.time_valid(now)
        if memory.capacity != self.capacity or mode not in ("learned", "fixed", "surprise") or type(limit) is not int or not 1 <= limit <= 2:
            raise ValueError("Invalid diagonal salience mode/budget.")
        results = []
        for relevance, index in memory.candidates(cue, 1):
            trace = memory.traces[index]
            durable = self.durable(index, field)
            fresh = math.exp(-(now - trace.ended) / 10)
            accessed = self.last_access[index].item()
            reactivation = 0. if accessed < 0 else math.exp(-(now - accessed) / 5)
            score = .7 * durable + .2 * fresh + .1 * reactivation
            if mode == "fixed":
                score = .7 + .2 * fresh + .1 * reactivation
            if mode == "surprise":
                score = self.surprise[index].item()
            results.append({"episode": index, "score": score, "durable": durable, "fresh": fresh,
                            "reactivation": reactivation, "relevance": relevance,
                            "occurred_at": [trace.started, trace.ended], "hypothesis": True})
        return sorted(results, key=lambda row: (row["score"], row["episode"]), reverse=True)[:limit]
