"""Raw paired inputs through the mind: timing, memory, actuator and forecast."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

import torch
from torch.nn import functional as F

from .contracts import Observation
from .continuous_mind import ContinuousMind
from .episodic_memory import EpisodicMemory
from .episodic_session import EpisodicSession
from .experience_signals import samples
from .memory_actor import MemoryActor, load as load_actor
from .process_metrics import Budget, memory_usage
from .signals import audio_features
from .temporal32_experiment import trajectory
from .temporal_mind import TemporalMind, load, load_models, save


def make_agent(template: MemoryActor, core, source: dict) -> TemporalMind:
    session = EpisodicSession(template.session.perception, template.session.boundary, EpisodicMemory(128))
    return TemporalMind(ContinuousMind(MemoryActor(session, template.policy)), core, source)


@torch.no_grad()
def rollout(agent: TemporalMind, record: dict, seed: int, control: str = "memory") -> dict:
    rng = random.Random(seed)
    predictions = []
    commands = record["commands"][:-1]
    shuffled = commands.roll(7, 0)
    for step in range(len(commands)):
        now = agent.clock + record["gaps"][step]
        visible = record["presence"][step]
        packets = [Observation("image", record["images"][step], now, agent.mind.actor.session.steps * 2,
                               "environment", present=visible),
                   Observation("audio", record["sounds"][step], now, agent.mind.actor.session.steps * 2 + 1,
                               "person", present=visible)]
        if control == "reset":
            agent.temporal.hidden.zero_()
        agent.perceive(packets, record["gaps"][step])
        command = commands[step]
        code = int(command[:4].argmax()) if command[8] else None
        purpose = int(command[4:8].argmax()) if command[8] else 0
        action = agent.issue_scripted(code, purpose)
        if code is not None:
            values = [0] * 4
            values[purpose] = code
            _, returned = samples(tuple(values), rng, tuple(index == purpose for index in range(4)))
            agent.hear([Observation("audio", returned, agent.clock, action.sequence, "self", action_id=action.sequence)], 0.)
        if control == "shuffled":
            altered = shuffled[step]
            agent.temporal.predict(int(altered[:4].argmax()) if altered[8] else None,
                                   int(altered[4:8].argmax()) if altered[8] else 0)
        predictions.append(agent.temporal.last_prediction[0].clone())
    # Evaluator reads the actual future raw observations only AFTER the rollout.
    perception = agent.mind.actor.session.perception
    encoded = F.normalize(perception.encode(record["images"], "image") +
                          perception.encode(audio_features(record["sounds"]), "audio"), dim=-1)
    predictions = torch.stack(predictions)
    short_error = (predictions[:-1, 0] - encoded[1:-1]).square().mean(-1)
    mask = torch.tensor(record["presence"][1:-1]).float()
    short = (short_error * mask).sum() / mask.sum().clamp_min(1)
    long = (predictions[3:, 1] - encoded[-1]).square().mean()
    recovered = perception.probabilities(predictions[-2, 1]).argmax(-1)
    expected = torch.tensor(record["truth"])
    return {"short_mse": short.item(), "long_mse": long.item(),
            "late_author_context_accuracy": (recovered[2:] == expected[2:]).float().mean().item(),
            "episodes": len(agent.mind.actor.session.memory.blocks),
            "motor_pending": len(agent.mind.actor.pending), "clock_sync": abs(agent.clock - agent.temporal.clock) < 1e-8}


def run(checkpoint: Path, models: Path, output: Path, seed: int, seconds: float = 180) -> dict:
    budget = Budget(100000, seconds)
    torch.set_num_threads(1)
    template = load_actor(checkpoint)
    source, core = load_models(models)
    output.mkdir(parents=True, exist_ok=False)
    rng = random.Random(seed + 133000)
    records = [trajectory(rng) for _ in range(32)]
    scores = {}
    last_agent = None
    for mode in ("memory", "reset", "shuffled"):
        trials = []
        for index, record in enumerate(records):
            budget.check(index)
            agent = make_agent(template, core, source)
            trials.append(rollout(agent, record, seed + index + 143000, mode))
            if mode == "memory":
                last_agent = agent
        scores[mode] = {name: sum(result[name] for result in trials) / len(trials)
                        for name in ("short_mse", "long_mse", "late_author_context_accuracy")}
        scores[mode].update(max_episodes=max(result["episodes"] for result in trials),
                            max_motor_pending=max(result["motor_pending"] for result in trials),
                            clocks_synced=all(result["clock_sync"] for result in trials))
    save(output / "agent.pt", last_agent)
    restored = load(output / "agent.pt")
    next_equal = last_agent.tick(.1) == restored.tick(.1) and torch.equal(last_agent.temporal.hidden, restored.temporal.hidden)
    report = {"seed": seed, "world_seed": seed + 133000, "format": 21, "trajectories": 32,
              "source_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
              "model_sha256": hashlib.sha256(models.read_bytes()).hexdigest(),
              "scores": scores, "next_tick_equal": next_equal, "memory": memory_usage(),
              "scope": "96-step raw paired external inputs through mind; scripted actuators and immediate own returns; hypotheses do not rewrite memories",
              "accepted": scores["memory"]["late_author_context_accuracy"] >= .9
                          and scores["reset"]["long_mse"] > scores["memory"]["long_mse"]
                          and scores["shuffled"]["short_mse"] > scores["memory"]["short_mse"]
                          and all(result["clocks_synced"] for result in scores.values()) and next_equal}
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--models", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--max-seconds", type=float, default=180)
    args = parser.parse_args()
    report = run(args.checkpoint, args.models, args.output, args.seed, args.max_seconds)
    print(json.dumps({"output": str(args.output.resolve()), "accepted": report["accepted"], "scores": report["scores"]}))
    raise SystemExit(0 if report["accepted"] else 2)


if __name__ == "__main__":
    main()
