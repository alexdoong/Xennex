"""Continuous temporal mind with shared, explicitly hypothetical regularities."""
from __future__ import annotations

from pathlib import Path
from contextlib import ExitStack

import torch

from .experience_perception import semantic
from .loop_checkpoint import atomic_write
from .semantic_memory import SemanticMemory, restore as restore_semantic
from .temporal_mind import TemporalMind, checkpoint_payload as temporal_payload, restore as restore_temporal


class ConsolidatingMind:
    def __init__(self, agent: TemporalMind, target: int = 2, forgetting: float = .9,
                 *, semantic_backend="conditional", seed=17) -> None:
        self.agent = agent
        memory = agent.mind.actor.session.memory
        if semantic_backend not in ("conditional", "neural", "neural-projected"):
            raise ValueError("Unknown semantic memory backend.")
        if semantic_backend == "neural-projected":
            from .projected_semantic_memory import ProjectedSemanticMemory
            self.semantic = ProjectedSemanticMemory(memory, target, seed=seed)
        elif semantic_backend == "neural":
            from .neural_semantic_memory import NeuralSemanticMemory
            self.semantic = NeuralSemanticMemory(memory, target, seed=seed)
        else:
            self.semantic = SemanticMemory(memory.capacity, target, forgetting)

    @property
    def mind(self):
        return self.agent.mind

    @property
    def temporal(self):
        return self.agent.temporal

    @property
    def clock(self):
        return self.agent.clock

    def consolidate_current(self) -> dict:
        memory = self.mind.actor.session.memory
        if not memory.blocks:
            return {"learned": False, "reason": "no episodes"}
        return self.semantic.consolidate(memory, len(memory.blocks) - 1, self.clock)

    def expand_capacity(self, capacity: int) -> dict:
        from .memory_capacity import expand_capacity
        return expand_capacity(self.mind.actor.session.memory, self.semantic, capacity, self.mind.importance)

    def perceive(self, observations, elapsed: float) -> dict:
        result = self.agent.perceive(observations, elapsed)
        learned = None
        if result["new_episode"] and result["episode"] > 0:
            learned = self.semantic.consolidate(self.mind.actor.session.memory, result["episode"] - 1, self.clock)
        return {**result, "consolidation": learned}

    def expect(self, cues) -> dict:
        session = self.mind.actor.session
        session.validate_cues(cues, self.clock)
        cue, _ = semantic(session.interpret(cues)[0])
        return self.semantic.predict(cue)

    def request(self, *args, **kwargs):
        return self.agent.request(*args, **kwargs)

    def revise(self, cues, evidence, field: int, elapsed: float, window=None) -> dict:
        result = self.agent.revise(cues, evidence, field, elapsed, window)
        consolidated = None
        if result["revised"]:
            consolidated = self.semantic.consolidate(self.mind.actor.session.memory, result["episode"], self.clock)
        return {**result, "consolidation": consolidated}

    def tick(self, *args, **kwargs):
        return self.agent.tick(*args, **kwargs)

    def hear(self, *args, **kwargs):
        return self.agent.hear(*args, **kwargs)

    def consequences(self, *args, **kwargs):
        return self.agent.consequences(*args, **kwargs)

    def issue_scripted(self, *args, **kwargs):
        return self.agent.issue_scripted(*args, **kwargs)

    def unobserved_gap(self, elapsed: float):
        return self.agent.unobserved_gap(elapsed)


def save(path: Path, agent: ConsolidatingMind) -> None:
    atomic_write(path, checkpoint_payload(agent))


def checkpoint_payload(agent: ConsolidatingMind) -> dict:
    temporal = temporal_payload(agent.agent)
    return {"format": 28 if temporal["format"] == 27 else 23, "agent": temporal,
            "semantic": agent.semantic.snapshot(), "torch_rng": torch.get_rng_state()}


def load(path: Path) -> ConsolidatingMind:
    from .checkpoint_io import read_checkpoint
    return restore(read_checkpoint(path, 12_000_000))


def restore(payload: dict) -> ConsolidatingMind:
    if not isinstance(payload, dict) or set(payload) != {"format", "agent", "semantic", "torch_rng"} or payload["format"] not in (23, 28):
        raise ValueError("Invalid consolidating checkpoint fields.")
    rng = payload["torch_rng"]
    if not isinstance(rng, torch.Tensor) or rng.dtype != torch.uint8 or rng.shape != torch.get_rng_state().shape:
        raise ValueError("Invalid consolidating checkpoint RNG.")
    with torch.random.fork_rng(devices=[]), ExitStack() as cleanup:
        agent = restore_temporal(payload["agent"])
        from .paged_memory import PagedMemory
        memory = agent.mind.actor.session.memory
        if isinstance(memory, PagedMemory):
            cleanup.callback(memory.close)
        if (payload["format"] == 28) != isinstance(memory, PagedMemory):
            raise ValueError("Consolidating memory architecture mismatch.")
        semantic_payload = payload["semantic"]
        restore_backend = restore_semantic
        if isinstance(semantic_payload, dict) and semantic_payload.get("architecture") == "neural-v1":
            from .neural_semantic_memory import restore as restore_backend
        if isinstance(semantic_payload, dict) and semantic_payload.get("architecture") == "neural-v2":
            from .projected_semantic_memory import restore as restore_backend
        semantic_model = restore_backend(semantic_payload, memory)
        result = ConsolidatingMind(agent, semantic_model.target, semantic_model.forgetting)
        result.semantic = semantic_model
        cleanup.pop_all()
    torch.set_rng_state(rng)
    return result
