"""Finite real/virtual scheduler for a checkpointed mind, with no live sensors.

Internal evocations can run without resending perception/history. Action objects
are recorded, never dispatched to an OS audio device or an external application.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import torch

from .continuous_mind import restore, save
from .process_metrics import Budget, memory_usage, quantiles


def load_scheduler(checkpoint: Path, worker_folder=None, worker_factory=None):
    from .checkpoint_io import read_checkpoint
    payload = read_checkpoint(checkpoint, 12_000_000)
    return restore_scheduler(payload, worker_folder, worker_factory)


def restore_scheduler(payload, worker_folder=None, worker_factory=None):
    if isinstance(payload, dict) and payload.get("format") in (40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58):
        from .conceptual_mind import restore as restore_conceptual, save as save_conceptual
        agent = restore_conceptual(payload, worker_folder, worker_factory)
        return agent, agent.mind, save_conceptual
    if isinstance(payload, dict) and payload.get("format") == 31:
        from .neural_language import restore as restore_neural, save as save_neural
        agent = restore_neural(payload, worker_folder or Path("bin/AliceMemory/LanguageWorkers"), worker_factory)
        return agent, agent.mind, save_neural
    if isinstance(payload, dict) and payload.get("format") in (30, 39):
        from .language_coordinator import restore as restore_language, save as save_language
        agent = restore_language(payload, worker_folder or Path("bin/AliceMemory/LanguageWorkers"), worker_factory)
        return agent, agent.mind, save_language
    if isinstance(payload, dict) and payload.get("format") in (29, 35):
        from .grounded_mind import restore as restore_grounded, save as save_grounded
        agent = restore_grounded(payload)
        return agent, agent.mind, save_grounded
    if isinstance(payload, dict) and payload.get("format") in (23, 28):
        from .consolidating_mind import restore as restore_consolidating, save as save_consolidating
        agent = restore_consolidating(payload)
        return agent, agent.mind, save_consolidating
    if isinstance(payload, dict) and payload.get("format") in (21, 27):
        from .temporal_mind import restore as restore_temporal, save as save_temporal
        agent = restore_temporal(payload)
        return agent, agent.mind, save_temporal
    mind = restore(payload)
    return mind, mind, save


def run(checkpoint: Path, output: Path, steps: int = 300, period: float = .1,
        realtime: bool = False, seconds: float = 60) -> dict:
    if isinstance(period, bool) or not isinstance(period, (int, float)) or not .001 <= period <= 1 or type(realtime) is not bool:
        raise ValueError("Scheduler period must be between 1 ms and 1 s.")
    budget = Budget(steps, seconds)
    agent, mind, save_agent = load_scheduler(checkpoint)
    try:
        return _run_loaded(checkpoint, output, steps, period, realtime, budget, agent, mind, save_agent)
    finally:
        if hasattr(agent, "close"):
            agent.close()
        if hasattr(mind.actor.session.memory, "close"):
            mind.actor.session.memory.close()


def _run_loaded(checkpoint, output, steps, period, realtime, budget, agent, mind, save_agent):
    temporal = getattr(agent, "temporal", None)
    initial_observations = None if temporal is None else temporal.observations
    semantic = getattr(agent, "semantic", None)
    initial_semantic_writes = None if semantic is None else int(semantic.bank.writes)
    output.mkdir(parents=True, exist_ok=False)
    initial_episodes = len(mind.actor.session.memory.blocks)
    initial_writes = mind.importance.values.writes.item()
    initial_clock = mind.clock
    started, previous, cpu_started = time.perf_counter(), time.perf_counter(), time.process_time()
    latency, lag = [], []
    evocations, actions, completed = 0, 0, 0
    interrupted = None
    try:
        for step in range(steps):
            deadline = started + (step + 1) * period
            if realtime:
                time.sleep(max(0., deadline - time.perf_counter()))
            now = time.perf_counter()
            elapsed = now - previous if realtime else period
            previous = now
            if elapsed > 60:
                agent.unobserved_gap(elapsed)
                result = agent.tick(0.)
            else:
                result = agent.tick(elapsed)
            completed += 1
            evocations += int(result["evoked"] is not None)
            actions += int(result["action"] is not None)
            latency.append((time.perf_counter() - now) * 1000)
            lag.append(max(0., now - deadline) * 1000 if realtime else 0.)
            budget.check(completed)
    except TimeoutError as error:
        interrupted = str(error)
    wall, cpu = time.perf_counter() - started, time.process_time() - cpu_started
    save_agent(output / "mind.pt", agent)
    temporal_stable = (temporal is None or (temporal.observations == initial_observations
                       and abs(temporal.clock - mind.clock) <= 1e-8))
    stability = (interrupted is None and completed == steps and initial_episodes == len(mind.actor.session.memory.blocks)
                 and initial_writes == mind.importance.values.writes.item()
                 and len(mind.credits) <= 32 and len(mind.actor.pending) <= 32 and temporal_stable
                 and (semantic is None or int(semantic.bank.writes) == initial_semantic_writes))
    tick_quantiles = quantiles(latency)
    usage = memory_usage()
    resource = (cpu / wall <= .05 and tick_quantiles["p95"] <= 10
                and isinstance(usage["peak_rss_bytes"], int) and usage["peak_rss_bytes"] <= 512 * 1024 * 1024) if realtime else None
    report = {"steps": completed, "requested_steps": steps, "period_seconds": period, "realtime": realtime,
              "runtime_wall_seconds": wall, "runtime_cpu_seconds": cpu,
              "single_core_cpu_fraction": cpu / wall if wall else 0., "clock_advanced_seconds": mind.clock - initial_clock,
              "tick_latency_ms": tick_quantiles, "scheduler_lag_ms": quantiles(lag),
              "memory": usage, "evocations": evocations, "action_objects": actions,
              "motor_pending": len(mind.actor.pending), "consequence_credits": len(mind.credits),
              "episodes_before": initial_episodes, "episodes_after": len(mind.actor.session.memory.blocks),
              "new_learned_value_writes": mind.importance.values.writes.item() - initial_writes,
              "interrupted": interrupted, "source_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
              "live_sensors_active": False, "history_resent": False,
              "temporal_core_active": temporal is not None,
              "temporal_observations_before": initial_observations,
              "temporal_observations_after": None if temporal is None else temporal.observations,
              "temporal_clocks_synced": temporal_stable,
              "semantic_writes_before": initial_semantic_writes,
              "semantic_writes_after": None if semantic is None else int(semantic.bank.writes),
              "scope": "finite scheduler and internal evocation; no permanent daemon, biological time or new experiences",
              "stability_accepted": stability, "resources_accepted": resource,
              "resource_targets": {"single_core_cpu_fraction_max": .05, "tick_p95_ms_max": 10, "rss_bytes_max": 512 * 1024 * 1024},
              "accepted": stability and (resource if realtime else True)}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--steps", type=int, default=300)
    parser.add_argument("--period-ms", type=float, default=100)
    parser.add_argument("--realtime", action="store_true")
    parser.add_argument("--max-seconds", type=float, default=60)
    args = parser.parse_args()
    import torch
    # Tiny intermittent inference needs no intra-op worker waiting between ticks.
    # Two threads showed ~100% of one core in the first real idle trial.
    torch.set_num_threads(1)
    report = run(args.checkpoint, args.output, args.steps, args.period_ms / 1000, args.realtime, args.max_seconds)
    print(json.dumps({"output": str(args.output.resolve()), **report}))
    raise SystemExit(0 if report["accepted"] else 2)


if __name__ == "__main__":
    main()
