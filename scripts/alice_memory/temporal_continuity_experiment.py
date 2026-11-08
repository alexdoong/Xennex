"""Two held-out encounters share one mind; past facts and current forecasts differ."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

import torch

from .episodic_experiment import packets
from .experience_signals import samples
from .memory_actor import load as load_actor
from .process_metrics import Budget, memory_usage
from .temporal32_experiment import trajectory
from .temporal_mind import load_models, save
from .temporal_runtime_experiment import make_agent, rollout


def recall_score(agent, cues, window, truth) -> float:
    recalled = agent.mind.actor.session.query(cues, window=window)
    return sum(bool(recalled["known"][field]) and
               int(torch.tensor(recalled["distributions"][field]).argmax()) == truth[field]
               for field in (2, 3)) / 2


def run(checkpoint: Path, models: Path, output: Path, seed: int, seconds: float = 120) -> dict:
    budget = Budget(10000, seconds)
    torch.set_num_threads(1)
    template = load_actor(checkpoint)
    source, core = load_models(models)
    rng = random.Random(seed + 153000)
    output.mkdir(parents=True, exist_ok=False)
    trials = []
    for index in range(8):
        budget.check(index)
        first, second = trajectory(rng), trajectory(rng)
        while any(first["truth"][field] == second["truth"][field] for field in (2, 3)):
            second = trajectory(rng)
        agent = make_agent(template, core, source)
        window = (first["gaps"][0], first["gaps"][0])
        rollout(agent, first, seed + index + 163000)
        image, sound = samples(first["truth"], rng, (True, True, False, False))
        before = recall_score(agent, packets(image, sound, agent.clock, 0), window, first["truth"])
        trace = agent.mind.actor.session.memory.traces[0]
        initial_dates = (trace.started, trace.ended)
        first_count = len(agent.mind.actor.session.memory.blocks)
        agent.unobserved_gap(30.)
        current = rollout(agent, second, seed + index + 173000)
        after = recall_score(agent, packets(image, sound, agent.clock, 0), window, first["truth"])
        trace = agent.mind.actor.session.memory.traces[0]
        trials.append({"past_before": before, "past_after": after,
                       "current_forecast": current["late_author_context_accuracy"],
                       "past_dates_preserved": initial_dates == (trace.started, trace.ended),
                       "episodes_before": first_count, "episodes_after": current["episodes"],
                       "clocks_synced": current["clock_sync"]})
    scores = {name: sum(trial[name] for trial in trials) / len(trials)
              for name in ("past_before", "past_after", "current_forecast")}
    accepted = (all(value >= .9 for value in scores.values())
                and all(trial["past_dates_preserved"] and trial["clocks_synced"]
                        and trial["episodes_after"] > trial["episodes_before"] for trial in trials))
    save(output / "agent.pt", agent)
    report = {"seed": seed, "world_seed": seed + 153000, "pairs": 8, "pause_seconds": 30,
              "scores": scores, "trials": trials, "accepted": accepted, "memory": memory_usage(),
              "source_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
              "model_sha256": hashlib.sha256(models.read_bytes()).hexdigest(),
              "scope": "two raw synthetic encounters, same state without reset; partial past cue plus occurrence window; scripted actions"}
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--models", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--max-seconds", type=float, default=120)
    args = parser.parse_args()
    report = run(args.checkpoint, args.models, args.output, args.seed, args.max_seconds)
    print(json.dumps({"output": str(args.output.resolve()), "accepted": report["accepted"], "scores": report["scores"]}))
    raise SystemExit(0 if report["accepted"] else 2)


if __name__ == "__main__":
    main()
