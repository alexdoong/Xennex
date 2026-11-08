"""Train/evaluate grounded task decoding and temporal-context attention in CPU."""
from __future__ import annotations

import argparse
import itertools
import json
import random
import time
from pathlib import Path

import torch
from torch.nn import functional as F

from .experience_signals import samples
from .grounded_mind import load as load_mind
from .loop_checkpoint import atomic_write
from .neural_tasks import TaskModel, source, validate_weights
from .process_metrics import Budget, memory_usage
from .signals import audio_features


@torch.no_grad()
def worlds(agent, seed, count, reserved):
    rng = random.Random(seed)
    combinations = [values for values in itertools.product(range(4), repeat=4)
                    if (sum((index + 1) * value for index, value in enumerate(values)) % 5 == 0) == reserved]
    images, sounds, previous_images, previous_sounds, labels = [], [], [], [], []
    for _ in range(count):
        values = rng.choice(combinations)
        image, sound = samples(values, rng)
        previous = tuple(rng.randrange(4) for _ in range(4))
        previous_image, previous_sound = samples(previous, rng)
        images.append(image)
        sounds.append(sound)
        previous_images.append(previous_image)
        previous_sounds.append(previous_sound)
        labels.append(values)
    perception, core = agent.mind.actor.session.perception, agent.temporal.core
    def encode(images, sounds):
        visual = perception.encode(torch.stack(images), "image")
        acoustic = perception.encode(audio_features(torch.stack(sounds)), "audio")
        return torch.where((torch.arange(count) % 2 == 0).unsqueeze(1), visual, acoustic)
    old, current = encode(previous_images, previous_sounds), encode(images, sounds)
    hidden = core.initial(count)
    generator = torch.Generator().manual_seed(seed + 1)
    for _ in range(3):
        hidden = core.advance(old, hidden, torch.rand(count, 1, generator=generator) + .1, torch.ones(count, 1))
    for _ in range(3):
        hidden = core.advance(current, hidden, torch.rand(count, 1, generator=generator) + .1, torch.ones(count, 1))
    return hidden, torch.tensor(labels)


def queries(labels, seed):
    generator = torch.Generator().manual_seed(seed)
    count = len(labels)
    visible = torch.rand(count, 4, generator=generator) > .4
    visible[:, 0] = True
    targets = torch.where(visible, labels, 4)
    confidence = .85 + .15 * torch.rand(count, 4, 1, generator=generator)
    cues = F.one_hot(labels, 4).float() * visible.unsqueeze(-1) * confidence
    fields = torch.randint(5, (count,), generator=generator)
    return cues.flatten(1), fields, torch.cat((targets, fields.unsqueeze(-1)), -1)


def decoder_data(seed, count, reserved):
    rng = random.Random(seed)
    combinations = [values for values in itertools.product(range(4), repeat=4)
                    if (sum((index + 1) * value for index, value in enumerate(values)) % 5 == 0) == reserved]
    labels = torch.tensor([rng.choice(combinations) for _ in range(count)])
    cues, fields, targets = queries(labels, seed + 1)
    # Unknown/all-absent cues are explicitly represented, not fabricated concepts.
    cues[::13] = 0
    targets[::13, :4] = 4
    return cues, fields, targets


def pairs(context, labels, seed):
    # Pair each scene with a compatible cue and one explicitly incompatible cue.
    cue, fields, targets = queries(labels, seed)
    bad = labels.clone()
    generator = torch.Generator().manual_seed(seed + 19)
    visible = cue.reshape(-1, 4, 4).sum(-1) > .5
    chosen = (torch.rand(len(labels), 4, generator=generator) * visible).argmax(-1)
    rows = torch.arange(len(labels))
    bad[rows, chosen] = (bad[rows, chosen] + torch.randint(1, 4, (len(labels),), generator=generator)) % 4
    bad_cue, _, _ = queries(bad, seed)
    return (torch.cat((cue, bad_cue)), torch.cat((fields, fields)), torch.cat((targets, targets)),
            context.repeat(2, 1), torch.cat((torch.ones(len(labels)), torch.zeros(len(labels)))))


def train(model, decoder, attention, seed, steps, budget):
    generator = torch.Generator().manual_seed(seed)
    optimizer = torch.optim.Adam(model.parameters(), lr=.003)
    cues, fields, targets = decoder
    task_cues, task_fields, _, context, compatible = attention
    for step in range(steps):
        budget.check(step)
        index = torch.randint(len(cues), (128,), generator=generator)
        latent = model.encode(cues[index], fields[index])
        logits = model.decode(latent)
        decoding = F.cross_entropy(logits.flatten(0, 1), targets[index].flatten())
        pair = torch.randint(len(task_cues), (128,), generator=generator)
        query = model.encode(task_cues[pair], task_fields[pair])
        # Attention gradients do not redefine the representation's learned meaning.
        ranking = F.binary_cross_entropy_with_logits(model.score(query.detach(), context[pair]), compatible[pair])
        optimizer.zero_grad(set_to_none=True)
        (decoding + ranking).backward()
        optimizer.step()
    model.eval().requires_grad_(False)


@torch.no_grad()
def evaluate(model, decoder, attention):
    cues, fields, targets = decoder
    probabilities = model.decode(model.encode(cues, fields)).softmax(-1)
    confidence, predictions = probabilities.max(-1)
    exact = ((predictions == targets) & (confidence >= .8)).all(-1)
    task_cues, task_fields, _, context, compatible = attention
    scores = model.score(model.encode(task_cues, task_fields), context).sigmoid()
    count = len(scores) // 2
    ranking = float((scores[:count] > scores[count:]).float().mean())
    accuracy = float(((scores >= .5) == compatible.bool()).float().mean())
    swapped_context = context.roll(137, 0)
    shuffled = model.score(model.encode(task_cues, task_fields), swapped_context).sigmoid()
    shuffled_ranking = float((shuffled[:count] > shuffled[count:]).float().mean())
    wrong_confident = ((predictions != targets) & (confidence >= .8)).any(-1)
    return {"exactConfidentDecode": float(exact.float().mean()), "fieldAccuracy": float((predictions[:, 4] == targets[:, 4]).float().mean()),
            "rankingAccuracy": ranking, "classificationAccuracy": accuracy,
            "shuffledContextRanking": shuffled_ranking, "wrongConfidentCases": int(wrong_confident.sum()),
            "positiveScoreMean": float(scores[:count].mean()), "negativeScoreMean": float(scores[count:].mean()),
            "decoderCases": len(cues), "rankingPairs": count}


def load_model(path, agent):
    if path.stat().st_size > 2000000:
        raise ValueError("Task model exceeds experimental size budget.")
    report_path = path.parent / "report.json"
    if report_path.stat().st_size > 32768:
        raise ValueError("Task validation report exceeds its size budget.")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(report, dict) or report.get("accepted") is not True:
        raise ValueError("Task model did not pass its evaluation gate.")
    payload = torch.load(path, map_location="cpu", weights_only=True)
    if not isinstance(payload, dict) or set(payload) != {"format", "source", "model"} or payload["format"] != 32 or payload["source"] != source(agent):
        raise ValueError("Task model and mind representation differ.")
    with torch.random.fork_rng(devices=[]):
        model = TaskModel()
        validate_weights(payload["model"], model)
        model.load_state_dict(payload["model"], strict=True)
    return model.eval().requires_grad_(False)


def run(checkpoint, output, seed, steps):
    output.mkdir(parents=True, exist_ok=False)
    started, cpu = time.perf_counter(), time.process_time()
    budget = Budget(3000, 240)
    agent = load_mind(checkpoint)
    try:
        context, labels = worlds(agent, seed + 701, 512, False)
        reserved_context, reserved_labels = worlds(agent, seed + 702, 512, True)
        decoder = decoder_data(seed + 703, 4096, False)
        held_decoder = decoder_data(seed + 704, 4096, True)
        attention = pairs(context, labels, seed + 705)
        held_attention = pairs(reserved_context, reserved_labels, seed + 706)
        torch.manual_seed(seed)
        model = TaskModel()
        before = evaluate(model, held_decoder, held_attention)
        train(model, decoder, attention, seed + 707, steps, budget)
        trained = evaluate(model, held_decoder, held_attention)
        report = {"format": 1, "seed": seed, "steps": steps, "before": before, "after": trained,
                  "accepted": trained["exactConfidentDecode"] >= .95 and trained["rankingAccuracy"] >= .90,
                  "source": source(agent), "wallSeconds": time.perf_counter() - started,
                  "cpuSeconds": time.process_time() - cpu, "memory": memory_usage(),
                  "scope": "synthetic learned query latents/temporal priority; not internal LLM activations",
                  "retention": "explicit neural working-state latch; not learned long-horizon retention"}
        atomic_write(output / "model.pt", {"format": 32, "source": source(agent), "model": model.state_dict()})
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report
    finally:
        if hasattr(agent.mind.actor.session.memory, "close"):
            agent.mind.actor.session.memory.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--steps", type=int, default=2000)
    options = parser.parse_args()
    if not 1 <= options.steps <= 3000:
        parser.error("steps must be between 1 and 3000")
    torch.set_num_threads(1)
    result = run(options.checkpoint, options.output, options.seed, options.steps)
    print(json.dumps(result))
    raise SystemExit(0 if result["accepted"] else 1)
