"""Neural hypotheses with a learned-function projection and bounded witnesses."""
from __future__ import annotations

import sqlite3

import torch

from .episodic_memory import cue_valid
from .experience_signals import WORDS
from .neural_semantic_memory import NeuralSemanticMemory, restore as restore_base
from .reactivation_index import source_digest
from .support_projection import SupportProjection, probabilities


class ProjectedSemanticMemory(NeuralSemanticMemory):
    def __init__(self, memory, target=2, replay_limit=3, seed=17):
        super().__init__(memory, target, replay_limit, seed)
        self.projection = SupportProjection()

    def consolidate(self, memory, episode, now):
        before = self.transaction_state()
        try:
            result = super().consolidate(memory, episode, now)
            if result["learned"]:
                self.projection.fit(self.bank, self.index)
            return result
        except BaseException:
            self.rollback(before)
            raise

    @torch.no_grad()
    def predict(self, cue):
        original = super().predict(cue)
        ignored = int(self.projection.ignored)
        if ignored < 0 or original["reason"] not in ("incomplete cue", "ambiguous cue", "unobserved cue combination"):
            return original
        if int(self.projection.fitted_writes) != int(self.bank.writes):
            return {**original, "reason": "projection requires refresh"}
        fields = [field for field in range(4) if field != self.target]
        retained = [axis for axis in range(3) if axis != ignored]
        known = cue_valid(cue)
        if not all(known[[fields[axis] for axis in retained]]):
            return original
        key = cue.reshape(4, 4)[fields].clone()
        key /= key.sum(-1, keepdim=True).clamp_min(1e-10)
        if (key[retained].max(-1).values < .8).any():
            return {**original, "reason": "ambiguous retained cue"}
        pending = self.pending_sources()
        if pending is None:
            return {**original, "reason": "source owner unavailable"}
        if pending:
            return {**original, "reason": "source updates pending", "pending_sources": pending}
        identities = self.index.keys[:int(self.index.count)].reshape(-1, 3, 4).argmax(-1)
        matches = (identities[:, retained] == key.argmax(-1)[retained]).all(-1).nonzero().flatten().tolist()
        by_category = {int(identities[position, ignored]): position for position in matches}
        if len(by_category) < 2:
            return {**original, "reason": "unobserved retained combination"}
        categories = sorted(by_category)
        positions = [by_category[categories[0]], by_category[categories[-1]]]
        memory = self._source()
        try:
            valid = all(torch.equal(source_digest(memory.blocks[int(self.index.episodes[position])]), self.index.digests[position])
                        for position in positions)
        except (OSError, sqlite3.Error):
            return {**original, "reason": "source storage unavailable"}
        if not valid:
            return {**original, "reason": "source weights changed"}
        probes = key.flatten().repeat(2, 1).reshape(2, 3, 4)
        for row, position in enumerate(positions):
            probes[row, ignored] = self.index.keys[position].reshape(3, 4)[ignored]
        outputs = probabilities(self.bank.network(probes.flatten(1)))
        agreement = (.5 * (outputs[0] - outputs[1]).abs().sum()).item()
        average = outputs.mean(0)
        top = average.topk(2).values
        supported = bool(int(self.bank.writes) and top[0] >= .8 and top[0] - top[1] >= .35 and agreement <= .15)
        return {**original, "supported": supported, "value": WORDS[self.target][int(average.argmax())] if supported else None,
                "distribution": average.tolist(), "confidence": top[0].item(), "confidence_is_calibrated": False,
                "reason": "supported projected hypothesis" if supported else "uncertain projected hypothesis",
                "support_policy": "learned_single_field_projection", "ignored_field": fields[ignored],
                "witnesses": [int(self.index.episodes[position]) for position in positions],
                "probe_disagreement": agreement}

    def snapshot(self):
        return {**super().snapshot(), "architecture": "neural-v2", "projection": self.projection.snapshot()}


def restore(payload, memory):
    if not isinstance(payload, dict) or payload.get("architecture") != "neural-v2" or "projection" not in payload:
        raise ValueError("Invalid projected semantic checkpoint.")
    base_payload = {name: value for name, value in payload.items() if name != "projection"}
    base_payload["architecture"] = "neural-v1"
    base = restore_base(base_payload, memory)
    result = ProjectedSemanticMemory(memory, base.target, base.replay_limit)
    result.bank, result.index = base.bank, base.index
    for name, value in base.named_buffers(recurse=False):
        getattr(result, name).copy_(value)
    result.projection.restore(payload["projection"], result.bank, result.index)
    return result
