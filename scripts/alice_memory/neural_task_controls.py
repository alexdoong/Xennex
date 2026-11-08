"""Runtime-slot attention controls on held-out temporal states, no language calls."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import torch

from .grounded_mind import load
from .neural_task_experiment import load_model, pairs, worlds
from .neural_tasks import TaskSlots, source
from .process_metrics import memory_usage


def run(checkpoint: Path, model_path: Path, output: Path, seed: int):
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    agent = load(checkpoint)
    try:
        model = load_model(model_path, agent)
        context, labels = worlds(agent, seed + 702, 512, True)
        cues, fields, _, contexts, _ = pairs(context, labels, seed + 706)
        slots = TaskSlots(model, source(agent))
        learned, shuffled, permuted, zero = [], [], [], []
        saved_weights = {name: value.clone() for name, value in model.state_dict().items()}
        no_refresh = True
        score_rows = []
        for index in range(512):
            # Older incompatible question then newer compatible question: FIFO
            # deliberately services the older one; this tests contextual preference.
            slots.store(1, cues[512 + index].double(), int(fields[512 + index]))
            slots.store(2, cues[index].double(), int(fields[index]))
            retained = slots.slots.clone()
            current = contexts[index:index + 1]
            bad, good = slots.score(1, current), slots.score(2, current)
            learned.append(good > bad)
            other = contexts[(index + 137) % 512:(index + 137) % 512 + 1]
            shuffled.append(slots.score(2, other) > slots.score(1, other))
            no_refresh &= bool(torch.equal(retained, slots.slots))
            # Keep ownership/metadata unchanged while swapping semantic contents.
            slots.slots[0] = retained[1]
            slots.slots[1] = retained[0]
            permuted.append(slots.score(2, current) > slots.score(1, current))
            slots.slots.copy_(retained)
            if index < 8:
                score_rows.append({"case": index, "older_incompatible": bad, "newer_compatible": good})
        with torch.no_grad():
            for value in model.priority.parameters():
                value.zero_()
            for index in range(512):
                slots.store(1, cues[512 + index].double(), int(fields[512 + index]))
                slots.store(2, cues[index].double(), int(fields[index]))
                current = contexts[index:index + 1]
                zero.append(slots.score(2, current) > slots.score(1, current))
            model.load_state_dict(saved_weights, strict=True)
        fraction = lambda values: sum(values) / len(values)
        restored_weights = all(torch.equal(value, saved_weights[name]) for name, value in model.state_dict().items())
        report = {"format": 1, "seed": seed, "pairs": 512, "learnedContextPreference": fraction(learned),
                  "shuffledContextPreference": fraction(shuffled), "swappedSlotPreference": fraction(permuted),
                  "erasedAttentionPreference": fraction(zero), "fifoContextPreference": 0.,
                  "retainedSlotsWithoutReencoding": no_refresh, "weightsRestoredExactly": restored_weights,
                  "samples": score_rows, "wallSeconds": time.perf_counter() - started, "memory": memory_usage(),
                  "scope": "held-out synthetic states; contextual preference, not FIFO's overall utility or fairness",
                  "accepted": fraction(learned) >= .9 and fraction(shuffled) <= .65 and fraction(permuted) <= .15
                  and fraction(zero) <= .1 and no_refresh and restored_weights}
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report
    finally:
        agent.mind.actor.session.memory.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()
    torch.set_num_threads(1)
    result = run(args.checkpoint, args.model, args.output, args.seed)
    print(json.dumps(result))
    raise SystemExit(0 if result["accepted"] else 1)
