"""Optional deep hypotheses with source provenance and conservative abstention.

The support gate currently requires an observed complete cue. It does not yet
admit the held-out cue combinations of the retention experiment. Predictions
come from network weights, never from an episode's target or a cached answer.
"""
from __future__ import annotations

import sqlite3
import weakref

import torch
from torch import nn

from .adaptive_memory import AdaptiveMemory, number, recalled_pair, restore as restore_kernel
from .episodic_memory import cue_valid
from .experience_signals import FIELDS, WORDS
from .neural_consolidation import consolidation_cycle
from .reactivation_index import ReactivationIndex, initial_digest, source_digest, signature, restore as restore_index


class NeuralSemanticMemory(nn.Module):
    update_budget = 100000
    forgetting = 1.  # Compatibility attribute; this kernel uses its own SGD rule.

    def __init__(self, memory, target=2, replay_limit=3, seed=17):
        super().__init__()
        if type(replay_limit) is not int or not 0 <= replay_limit <= 3:
            raise ValueError("Mind consolidation permits at most three reactivations.")
        self.capacity, self.target, self.replay_limit = memory.capacity, target, replay_limit
        self.index = ReactivationIndex(self.capacity, target=target, seed=seed)
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(seed)
            self.bank = AdaptiveMemory(window=16)
        # Keep a single source owner; nn.Module must not register the source as
        # another child and duplicate its weights in the semantic checkpoint.
        self._source = weakref.ref(memory)
        self.register_buffer("versions", torch.full((self.capacity,), -1, dtype=torch.int64))
        self.register_buffer("stamps", torch.zeros(self.capacity, dtype=torch.float64))
        self.register_buffer("observations", torch.zeros(self.capacity, dtype=torch.int64))
        self.register_buffer("origins", torch.zeros(self.capacity, 32, dtype=torch.uint8))
        self.register_buffer("digests", torch.zeros(self.capacity, 32, dtype=torch.uint8))
        self.register_buffer("clock", torch.tensor(0., dtype=torch.float64))

    @property
    def max_writes_per_source(self):
        return 1 + self.replay_limit

    def _owner(self, memory):
        if self._source() is not memory or memory.capacity != self.capacity:
            raise ValueError("Neural hypotheses require their original episodic owner.")

    def transaction_state(self):
        return ({name: value.clone() for name, value in self.state_dict().items()},
                self.index.generator.get_state().clone())

    def rollback(self, state):
        self.load_state_dict(state[0], strict=True)
        self.index.generator.set_state(state[1])

    @torch.no_grad()
    def consolidate(self, memory, episode, now):
        self._owner(memory)
        number(now, self.clock.item(), memory.clock, "semantic time")
        if now != memory.clock or type(episode) is not int or not 0 <= episode < len(memory.blocks):
            raise ValueError("Neural consolidation requires a current source episode/time.")
        block = memory.blocks[episode]
        if not bool(block.known[0].all()):
            return {"learned": False, "deferred": True, "reason": "incomplete first interpretation"}
        digest, origin = source_digest(block), initial_digest(block)
        if int(self.versions[episode]) >= 0 and not torch.equal(origin, self.origins[episode]):
            raise ValueError("The first interpretation of a consolidated source changed.")
        if int(self.versions[episode]) >= 0 and torch.equal(digest, self.digests[episode]):
            self.observations[episode] = memory.traces[episode].observations
            return {"learned": False, "reason": "already consolidated"}
        if recalled_pair(memory, episode, now, self.target) is None:
            return {"learned": False, "deferred": True, "reason": "unsupported source weights"}
        before = self.transaction_state()
        try:
            result = consolidation_cycle(self.bank, self.index, memory, episode, self.replay_limit)
            self.versions[episode] = result["source_revision"]
            self.stamps[episode] = block.learned_at[1].max()
            self.observations[episode] = memory.traces[episode].observations
            self.origins[episode].copy_(origin)
            self.digests[episode].copy_(digest)
            self.clock.fill_(now)
            return {**result, "source_reads": result["source_reads"] + 1, "learned": True,
                    "hypothesis": True, "target": FIELDS[self.target]}
        except BaseException:
            self.rollback(before)
            raise

    def pending_sources(self):
        memory = self._source()
        if memory is None:
            return None
        # Metadata only: no unbounded paging or recall during a prediction.
        return [episode for episode, block in enumerate(memory.blocks)
                if (int(self.versions[episode]) < 0 and bool(block.known[1].all())) or
                (int(self.versions[episode]) >= 0 and
                 (int(block.revisions.sum()) != int(self.versions[episode]) or
                 memory.traces[episode].observations != int(self.observations[episode]) or
                  block.learned_at[1].max().item() != self.stamps[episode].item()))]

    @torch.no_grad()
    def predict(self, cue):
        known = cue_valid(cue)
        result = {"hypothesis": True, "target": FIELDS[self.target], "value": None,
                  "supported": False, "distribution": [0.] * 4, "confidence": 0.,
                  "variance": None, "confidence_is_calibrated": False,
                  "support_policy": "observed_complete_cue", "reason": "incomplete cue"}
        fields = [field for field in range(4) if field != self.target]
        if not all(known[fields]):
            return result
        key = cue.reshape(4, 4)[fields].clone()
        key = (key / key.sum(-1, keepdim=True)).flatten().double()
        if (key.reshape(3, 4).max(-1).values < .8).any():
            return {**result, "reason": "ambiguous cue"}
        pending = self.pending_sources()
        if pending is None:
            return {**result, "reason": "source owner unavailable"}
        if pending:
            return {**result, "reason": "source updates pending", "pending_sources": pending}
        identities = self.index.keys[:int(self.index.count)].reshape(-1, 3, 4).argmax(-1)
        matched = (identities == torch.tensor(signature(key))).all(-1).nonzero().flatten().tolist()
        if not matched:
            return {**result, "reason": "unobserved cue combination"}
        position = matched[0]
        episode = int(self.index.episodes[position])
        memory = self._source()
        try:
            valid = torch.equal(source_digest(memory.blocks[episode]), self.index.digests[position])
        except (OSError, sqlite3.Error):
            return {**result, "reason": "source storage unavailable"}
        if not valid:
            return {**result, "reason": "source weights changed"}
        probabilities = self.bank.read(key).clamp_min(0)
        probabilities /= probabilities.sum().clamp_min(1e-10)
        top = probabilities.topk(2).values
        confidence = top[0].item()
        supported = bool(int(self.bank.writes) and confidence >= .8 and (top[0] - top[1]).item() >= .35)
        return {**result, "supported": supported, "distribution": probabilities.tolist(),
                "confidence": confidence, "value": WORDS[self.target][int(probabilities.argmax())] if supported else None,
                "reason": "supported hypothesis" if supported else "low neural confidence",
                "source_episode": episode, "source_revision": int(self.index.revisions[position])}

    def snapshot(self):
        ledger = {name: getattr(self, name).clone() for name in ("versions", "stamps", "observations", "origins", "digests", "clock")}
        return {"architecture": "neural-v1", "capacity": self.capacity, "target": self.target,
                "replay_limit": self.replay_limit, "kernel": self.bank.snapshot(),
                "index": self.index.snapshot(), "ledger": ledger}


def restore(payload, memory):
    fields = {"architecture", "capacity", "target", "replay_limit", "kernel", "index", "ledger"}
    if not isinstance(payload, dict) or set(payload) != fields or payload["architecture"] != "neural-v1" or type(payload["capacity"]) is not int or payload["capacity"] != memory.capacity:
        raise ValueError("Invalid neural semantic checkpoint fields/owner capacity.")
    with torch.random.fork_rng(devices=[]):
        result = NeuralSemanticMemory(memory, payload["target"], payload["replay_limit"])
        result.bank = restore_kernel(payload["kernel"])
    if result.bank.config["key_size"] != 12 or result.bank.config["value_size"] != 4:
        raise ValueError("Invalid neural semantic kernel dimensions.")
    ledger = payload["ledger"]
    names = ("versions", "stamps", "observations", "origins", "digests", "clock")
    if not isinstance(ledger, dict) or set(ledger) != set(names):
        raise ValueError("Invalid neural semantic ledger fields.")
    for name in names:
        value, expected = ledger[name], getattr(result, name)
        if not isinstance(value, torch.Tensor) or value.device.type != "cpu" or value.dtype != expected.dtype or value.shape != expected.shape or not torch.isfinite(value).all():
            raise ValueError("Invalid neural semantic ledger tensor.")
        expected.copy_(value)
    used = result.versions >= 0
    if (result.versions < -1).any() or (result.versions > memory.revision_capacity).any() or used[len(memory.blocks):].any() or (result.stamps < 0).any() or (result.stamps > result.clock).any():
        raise ValueError("Invalid neural semantic source versions/times.")
    if any(getattr(result, name)[~used].count_nonzero() for name in ("stamps", "observations", "origins", "digests")) or (result.observations[used] < 1).any():
        raise ValueError("Invalid unused neural semantic ledger rows.")
    if not 0 <= result.clock.item() <= memory.clock or result.clock.item() != result.bank.clock.item() or int(result.bank.writes) < int(used.sum()):
        raise ValueError("Neural semantic clock/writes disagree with the ledger.")
    if bool(used.any()) != bool(int(result.bank.writes)):
        raise ValueError("Neural semantic weights have no recorded learning sources.")
    for episode in used.nonzero().flatten().tolist():
        block = memory.blocks[episode]
        revision, stamp = int(block.revisions.sum()), block.learned_at[1].max().item()
        if not bool(block.known[0].all()) or not torch.equal(initial_digest(block), result.origins[episode]) or int(result.versions[episode]) > revision or result.stamps[episode].item() > stamp or int(result.observations[episode]) > memory.traces[episode].observations:
            raise ValueError("Neural semantic ledger does not belong to its source history.")
        fresh = int(result.versions[episode]) == revision and result.stamps[episode].item() == stamp and int(result.observations[episode]) == memory.traces[episode].observations
        if fresh and not torch.equal(source_digest(block), result.digests[episode]):
            raise ValueError("Neural semantic ledger source weights differ.")
    result.index = restore_index(payload["index"], memory, allow_stale=True, stale_episodes=result.pending_sources())
    if result.index.target != result.target or result.index.clock.item() > result.clock.item():
        raise ValueError("Neural semantic index target/clock mismatch.")
    if bool(int(result.index.count)) != bool(used.any()):
        raise ValueError("Neural semantic source ledger has no routing witnesses.")
    for position in range(int(result.index.count)):
        episode = int(result.index.episodes[position])
        if (int(result.index.revisions[position]) != int(result.versions[episode]) or
                result.index.learned_at[position].item() != result.stamps[episode].item() or
                not torch.equal(result.index.digests[position], result.digests[episode])):
            raise ValueError("Neural semantic routes disagree with the source ledger.")
    return result
