"""Finite causal-world evaluation; does not claim learned action policy or episodes."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from pathlib import Path

import torch

from .agent_loop import AgentLoop
from .experiment import learn_perception
from .loop_checkpoint import load, save
from .network import Perception
from .process_metrics import Budget, memory_usage, quantiles
from .signals import bank
from .temporal_core import TemporalCore, TemporalSession
from .world import SyntheticWorld


def create(seed: int) -> tuple[AgentLoop, SyntheticWorld]:
    torch.manual_seed(seed)
    perception = Perception()
    images, audio, labels = bank(seed + 100, 24)
    learn_perception(perception, images, audio, labels)
    # This foundation persists a recurrent state; its random core is explicitly untrained.
    core = TemporalCore().eval()
    return AgentLoop(perception, TemporalSession(core)), SyntheticWorld(seed)


def drive(agent: AgentLoop, world: SyntheticWorld, steps: int, budget: Budget,
          realtime: bool = False) -> dict:
    if type(steps) is not int or not 1 <= steps <= budget.steps:
        raise ValueError("Loop length must fit its explicit step budget.")
    latency = []
    counts = {kind: 0 for kind in ("focus", "inspect", "emit", "wait")}
    peak_pending = 0
    started = time.perf_counter()
    cpu = time.process_time()
    last = started
    for completed in range(steps):
        budget.check(completed)
        if realtime:
            delay = max(0, .05 - (time.perf_counter() - last))
            time.sleep(delay)
        now = time.perf_counter()
        elapsed = min(60, now - last) if realtime else .1
        last = now
        packets = world.advance(elapsed, agent.last_action)
        result = agent.step(packets, elapsed)
        latency.append(time.perf_counter() - now)
        counts[result.action.kind] += 1
        peak_pending = max(peak_pending, len(world.pending), len(agent.emissions))
    budget.check(steps)
    return {"steps": steps, "loop_wall_seconds": time.perf_counter() - started,
            "loop_cpu_seconds": time.process_time() - cpu,
            "step_latency_seconds": quantiles(latency), "actions": counts,
            "peak_pending": peak_pending, "last_step": asdict(result)}


def run(output: Path, seed: int = 17, steps: int = 10_000,
        max_seconds: float = 300, checkpoint: Path | None = None,
        realtime: bool = False) -> dict:
    if type(seed) is not int or not 0 <= seed <= 1_000_000:
        raise ValueError("Seed must be between 0 and 1000000.")
    budget = Budget(steps, max_seconds)
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    try:
        output.mkdir(parents=True, exist_ok=False)
        preparation = time.perf_counter()
        agent, world = load(checkpoint) if checkpoint else create(seed)
        prepare_seconds = time.perf_counter() - preparation
        start_memory = memory_usage()
        report = drive(agent, world, steps, budget, realtime)
        export = time.perf_counter()
        save(output / "loop.pt", agent, world)
        export_seconds = time.perf_counter() - export
        world.render().save(output / "scene.png")
        tensor_bytes = sum(value.numel() * value.element_size() for model in (agent.perception, agent.temporal.core)
                           for value in model.state_dict().values()) + agent.temporal.hidden.numel() * 4
        report.update(format=6, seed=world.seed, device="cpu", torch=str(torch.__version__),
                      scope="M1 causal loop; supervised synthetic perception; scripted policy; untrained recurrent core",
                      memory_at_loop_start=start_memory, memory_at_loop_end=memory_usage(),
                      preparation_seconds=prepare_seconds, checkpoint_seconds=export_seconds,
                      tensor_state_bytes=tensor_bytes, virtual_seconds=world.clock,
                      self_feedback=agent.self_feedback, external_feedback=agent.external_feedback,
                      stored_observation_history=False, resumed=checkpoint is not None,
                      accepted=report["peak_pending"] <= 32 and torch.isfinite(agent.temporal.hidden).all().item())
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report
    except (OSError, TimeoutError):
        logging.exception("Alice loop experiment failed in %s", output)
        raise
