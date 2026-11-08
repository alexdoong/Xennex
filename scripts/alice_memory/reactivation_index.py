"""Bounded representative routes into episodic weights, without cached targets."""
from __future__ import annotations

import hashlib
import struct

import torch
from torch import nn

from .adaptive_memory import number, recalled_pair


def signature(key):
    if not isinstance(key, torch.Tensor) or key.device.type != "cpu" or key.dtype != torch.float64 or key.shape != (12,) or not torch.isfinite(key).all() or (key < 0).any():
        raise ValueError("Invalid representative route key.")
    fields = key.reshape(3, 4)
    if not torch.allclose(fields.sum(-1), torch.ones(3, dtype=torch.float64), atol=1e-5) or (fields.max(-1).values < .8).any():
        raise ValueError("Representative routes require three confident learned fields.")
    return tuple(fields.argmax(-1).tolist())


def _banks_digest(banks):
    # Hash source weights, not their decoded categorical targets. The digest is
    # only an integrity/provenance check; it never supplies a learning value.
    digest = hashlib.sha256()
    for bank in banks:
        for tensor in (bank.weights, bank.precision, bank.writes):
            values = tensor.detach().flatten().tolist()
            code = "q" if tensor.dtype == torch.int64 else "d"
            digest.update(struct.pack("<" + code * len(values), *values))
    return torch.tensor(list(digest.digest()), dtype=torch.uint8)


def source_digest(block):
    return _banks_digest(block.banks)


def initial_digest(block):
    """Bind a complete source to its immutable first interpretation."""
    return _banks_digest(block.banks[:4])


class ReactivationIndex(nn.Module):
    """One latest learned source per structured cue; uniform bounded reactivation.

    These routes rely on the existing learned four-category perceptual fields,
    not general open-world latent clustering. No target values are kept here.
    """
    def __init__(self, source_capacity, capacity=128, target=2, seed=17):
        super().__init__()
        if type(source_capacity) is not int or not 1 <= source_capacity <= 4096 or type(capacity) is not int or not 1 <= capacity <= 256 or type(target) is not int or not 0 <= target < 4 or type(seed) is not int or not 0 <= seed <= 2**63 - 1:
            raise ValueError("Invalid reactivation-index configuration.")
        self.source_capacity, self.capacity, self.target = source_capacity, capacity, target
        self.generator = torch.Generator().manual_seed(seed)
        self.register_buffer("keys", torch.zeros(capacity, 12, dtype=torch.float64))
        self.register_buffer("episodes", torch.full((capacity,), -1, dtype=torch.int64))
        self.register_buffer("revisions", torch.full((capacity,), -1, dtype=torch.int64))
        self.register_buffer("learned_at", torch.zeros(capacity, dtype=torch.float64))
        self.register_buffer("digests", torch.zeros(capacity, 32, dtype=torch.uint8))
        self.register_buffer("count", torch.tensor(0, dtype=torch.int64))
        self.register_buffer("updates", torch.tensor(0, dtype=torch.int64))
        self.register_buffer("clock", torch.tensor(0., dtype=torch.float64))

    def _owner(self, memory):
        if memory.capacity != self.source_capacity:
            raise ValueError("Reactivation-index source capacity mismatch.")

    @torch.no_grad()
    def observe(self, memory, episode, now):
        self._owner(memory)
        number(now, self.clock.item(), memory.clock, "reactivation time")
        pair = recalled_pair(memory, episode, now, self.target)
        if pair is None:
            return {"indexed": False, "reason": "unsupported source weights"}
        key = pair["key"]
        identity = signature(key)
        identities = self.keys[:int(self.count)].reshape(-1, 3, 4).argmax(-1)
        matches = (identities == torch.tensor(identity)).all(-1).nonzero().flatten().tolist()
        obsolete = ((self.episodes[:int(self.count)] == episode) &
                    (identities != torch.tensor(identity)).any(-1)).nonzero().flatten().tolist()
        kept = [position for position in range(int(self.count)) if position not in obsolete]
        position = kept.index(matches[0]) if matches else len(kept)
        block = memory.blocks[episode]
        learned_at = block.learned_at[1].max().item()
        digest = source_digest(block)
        previous = matches[0] if matches else None
        if matches and (learned_at < self.learned_at[previous].item() or
                        (episode == int(self.episodes[previous]) and torch.equal(digest, self.digests[previous]))):
            return {"indexed": False, "reason": "older or already indexed source"}
        if position >= self.capacity or int(self.updates) >= 100000:
            raise ValueError("Reactivation route budget reached; prior routes preserved.")
        if obsolete:
            self._compact(kept)
        self.keys[position].copy_(key)
        self.episodes[position] = episode
        self.revisions[position] = pair["source_revision"]
        self.learned_at[position] = learned_at
        self.digests[position].copy_(digest)
        self.count.fill_(max(int(self.count), position + 1))
        self.updates.add_(1)
        self.clock.fill_(now)
        return {"indexed": True, "route": position, "source_episode": episode}

    def _compact(self, kept):
        for name in ("keys", "episodes", "revisions", "learned_at", "digests"):
            buffer = getattr(self, name)
            retained = buffer[kept].clone()
            buffer.fill_(-1 if name in ("episodes", "revisions") else 0)
            buffer[:len(kept)].copy_(retained)
        self.count.fill_(len(kept))

    @torch.no_grad()
    def select(self, memory, limit=3, exclude=None, policy="representatives"):
        self._owner(memory)
        if type(limit) is not int or not 0 <= limit <= 16 or policy not in ("representatives", "history") or (exclude is not None and (type(exclude) is not int or not 0 <= exclude < len(memory.blocks))):
            raise ValueError("Invalid bounded reactivation request.")
        population = ([index for index in range(int(self.count)) if int(self.episodes[index]) != exclude]
                      if policy == "representatives" else [index for index in range(len(memory.blocks)) if index != exclude])
        before = self.generator.get_state().clone()
        try:
            order = torch.randperm(len(population), generator=self.generator).tolist()[:limit] if population and limit else []
            result, skipped = [], []
            for chosen in order:
                route = population[chosen]
                episode = int(self.episodes[route]) if policy == "representatives" else route
                block = memory.blocks[episode]
                if policy == "representatives" and not torch.equal(source_digest(block), self.digests[route]):
                    skipped.append({"episode": episode, "reason": "source weights changed"})
                    continue
                pair = recalled_pair(memory, episode, memory.clock, self.target)
                if pair is None:
                    skipped.append({"episode": episode, "reason": "unsupported source weights"})
                    continue
                if policy == "representatives" and signature(pair["key"]) != signature(self.keys[route]):
                    skipped.append({"episode": episode, "reason": "source cue changed"})
                    continue
                result.append(pair)
            return {"pairs": result, "attempted": len(order), "skipped": skipped}
        except BaseException:
            self.generator.set_state(before)
            raise

    def snapshot(self):
        return {"format": 38, "capacity": self.capacity, "source_capacity": self.source_capacity,
                "target": self.target, "generator": self.generator.get_state().clone(),
                "state": {name: value.clone() for name, value in self.state_dict().items()}}

    def metrics(self):
        return {"representatives": int(self.count), "route_updates": int(self.updates),
                "route_tensor_bytes": sum(value.numel() * value.element_size() for value in self.state_dict().values()),
                "generator_bytes": self.generator.get_state().numel(), "cached_target_values": 0}


def restore(payload, memory, *, allow_stale=False, stale_episodes=()):
    fields = {"format", "capacity", "source_capacity", "target", "generator", "state"}
    if not isinstance(payload, dict) or set(payload) != fields or type(payload["format"]) is not int or payload["format"] != 38:
        raise ValueError("Invalid reactivation-index checkpoint fields.")
    result = ReactivationIndex(payload["source_capacity"], payload["capacity"], payload["target"])
    result._owner(memory)
    state, expected = payload["state"], result.state_dict()
    if not isinstance(state, dict) or set(state) != set(expected):
        raise ValueError("Invalid reactivation-index checkpoint tensors.")
    for name, value in state.items():
        if not isinstance(value, torch.Tensor) or value.device.type != "cpu" or value.dtype != expected[name].dtype or value.shape != expected[name].shape or not torch.isfinite(value).all():
            raise ValueError("Invalid reactivation-index checkpoint tensor type/shape/value.")
    result.load_state_dict(state, strict=True)
    count = int(result.count)
    if not 0 <= count <= result.capacity or not count <= int(result.updates) <= 100000 or not 0 <= result.clock.item() <= memory.clock:
        raise ValueError("Invalid reactivation-index checkpoint counters.")
    if any(value[count:].count_nonzero().item() for value in (result.keys, result.learned_at, result.digests)) or (result.episodes[count:] != -1).any() or (result.revisions[count:] != -1).any():
        raise ValueError("Invalid reactivation-index unused routes.")
    if type(allow_stale) is not bool:
        raise ValueError("Invalid stale-source restore option.")
    if (not isinstance(stale_episodes, (tuple, list)) or
            any(type(episode) is not int or not 0 <= episode < len(memory.blocks) for episode in stale_episodes) or
            (stale_episodes and not allow_stale)):
        raise ValueError("Invalid deferred-source restore references.")
    identities = set()
    for position in range(count):
        episode, revision = int(result.episodes[position]), int(result.revisions[position])
        if not 0 <= episode < len(memory.blocks) or revision < 0 or not 0 <= result.learned_at[position].item() <= result.clock.item():
            raise ValueError("Invalid representative source reference/time.")
        block = memory.blocks[episode]
        stamp = result.learned_at[position].item()
        current_revision, current_stamp = int(block.revisions.sum()), block.learned_at[1].max().item()
        stale = revision < current_revision or stamp < current_stamp or episode in stale_episodes
        if revision > current_revision or stamp > current_stamp or (stale and not allow_stale):
            raise ValueError("Representative checkpoint does not match its source weights.")
        identity = signature(result.keys[position])
        if identity in identities:
            raise ValueError("Invalid or duplicate learned representative cue.")
        if not stale:
            if not torch.equal(source_digest(block), result.digests[position]):
                raise ValueError("Representative checkpoint does not match its source weights.")
            pair = recalled_pair(memory, episode, memory.clock, result.target)
            if pair is None or signature(pair["key"]) != identity:
                raise ValueError("Invalid learned representative cue.")
        identities.add(identity)
    generator = payload["generator"]
    if not isinstance(generator, torch.Tensor) or generator.device.type != "cpu" or generator.dtype != torch.uint8 or generator.shape != result.generator.get_state().shape:
        raise ValueError("Invalid reactivation sampler state.")
    try:
        result.generator.set_state(generator.clone())
    except RuntimeError as error:
        raise ValueError("Invalid reactivation sampler state.") from error
    return result
