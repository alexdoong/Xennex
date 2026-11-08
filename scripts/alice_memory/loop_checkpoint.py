"""Atomic, versioned restoration of the causal agent and its simulation."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from uuid import uuid4

import torch

from .agent_loop import AgentLoop
from .temporal_core import restore_checkpoint
from .world import SyntheticWorld


def save(path: Path, agent: AgentLoop, world: SyntheticWorld) -> None:
    if abs(agent.clock - world.clock) > 1e-8:
        raise ValueError("Cannot checkpoint unsynchronized agent and world.")
    session = agent.temporal
    temporal = {"format": 3, "perception": agent.perception.state_dict(),
                "core": session.core.state_dict(), "hidden": session.hidden,
                "since_observation": session.since_observation, "observations": session.observations}
    payload = {"format": 6, "temporal": temporal, "agent": agent.snapshot(),
               "world": world.snapshot(), "torch_rng": torch.get_rng_state()}
    atomic_write(path, payload)


def atomic_write(path: Path, payload: dict) -> None:
    """Shared transaction for versioned, local Torch checkpoints."""
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        with temporary.open("wb") as stream:
            torch.save(payload, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError:
        logging.exception("Failed to save Alice loop checkpoint: %s", path)
        raise
    finally:
        if temporary.exists():
            temporary.unlink()


def load(path: Path) -> tuple[AgentLoop, SyntheticWorld]:
    try:
        if path.stat().st_size > 2_000_000:
            raise ValueError("Loop checkpoint exceeds the size limit.")
        payload = torch.load(path, map_location="cpu", weights_only=True)
    except OSError:
        logging.exception("Failed to load Alice loop checkpoint: %s", path)
        raise
    if not isinstance(payload, dict) or set(payload) != {"format", "temporal", "agent", "world", "torch_rng"} or payload["format"] != 6:
        raise ValueError("Invalid loop checkpoint format.")
    rng = payload["torch_rng"]
    if not isinstance(rng, torch.Tensor) or rng.dtype != torch.uint8 or rng.shape != torch.get_rng_state().shape:
        raise ValueError("Invalid Torch RNG snapshot.")
    with torch.random.fork_rng(devices=[]):
        perception, temporal = restore_checkpoint(payload["temporal"])
        agent = AgentLoop(perception, temporal)
        agent.restore_state(payload["agent"])
        world = SyntheticWorld.restore(payload["world"])
        if abs(agent.clock - world.clock) > 1e-8 or agent.steps != world.steps:
            raise ValueError("Checkpoint world and agent are out of sync.")
    # Commit RNG only after every component is validated.
    torch.set_rng_state(rng)
    return agent, world
