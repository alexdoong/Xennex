"""Chronological synthetic episodes, incremental writes and a later correction."""
from __future__ import annotations

import json
import random
import time
from pathlib import Path

import torch

from .experiment import learn_perception
from .network import Perception
from .online_memory import (EPISODES, VIEWS, OnlineMemory, describe, load_checkpoint,
                            make_key, make_value, save_checkpoint)
from .signals import bank, synthetic_image, synthetic_audio, save_audio, image_tensor

NOVELTY_THRESHOLD = 25.0  # Specific to this synthetic representation and ridge prior.


def score(memory: OnlineMemory, representations: dict, labels: list,
          targets: torch.Tensor, episodes: int) -> dict:
    result = {}
    for modality in ("image", "audio"):
        predicted, expected = [], []
        for episode in range(episodes):
            for view_index, view in enumerate(VIEWS):
                keys = make_key(representations[episode][modality], episode, view)
                predicted.append(memory.recall(keys))
                expected.append(targets[episode, view_index, labels[episode]])
        matches = torch.cat(predicted) == torch.cat(expected)
        result[modality] = {"exact": matches.all(dim=-1).double().mean().item(),
                            "attributes": matches.double().mean().item()}
    return result


def run(output: Path, seed: int = 17) -> dict:
    if not 0 <= seed <= 1_000_000:
        raise ValueError("Seed must be between 0 and 1000000.")
    output.mkdir(parents=True, exist_ok=False)
    torch.manual_seed(seed)
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    started = time.perf_counter()
    perception = Perception()
    train_images, train_audio, train_labels = bank(seed + 100, 24)
    learn_perception(perception, train_images, train_audio, train_labels)
    frozen = {name: value.clone() for name, value in perception.state_dict().items()}
    memory = OnlineMemory()
    # Labels and evaluator banks belong to the simulator, never to the memory.
    generator = torch.Generator().manual_seed(seed + 300)
    initial = torch.randint(0, 4, (EPISODES, 8, 3), generator=generator)
    initial[1, 0] = torch.tensor([1, 0, 0])  # Ate pleasant meal; initially credited father.
    targets = initial.unsqueeze(1).repeat(1, len(VIEWS), 1, 1)
    evaluation, labels = {}, []
    with torch.inference_mode():
        for episode in range(EPISODES):
            images, audio, identity = bank(seed + 1000 + episode, 12)
            evaluation[episode] = {"image": perception.encode(images, "image"),
                                   "audio": perception.encode(audio, "audio")}
            labels.append(identity)
    state_bytes = sum(t.numel() * t.element_size() for t in memory.state_dict().values())
    stages, novelty = [], []
    for episode in range(EPISODES):
        keys = make_key(evaluation[episode]["image"], episode, "current")
        novelty.append(bool((memory.variance(keys) > NOVELTY_THRESHOLD).all()))
        images, _, identity = bank(seed + 2000 + episode, 16)
        with torch.no_grad():
            representations = perception.encode(images, "image")
        for index in torch.randperm(len(identity), generator=generator).tolist():
            for view in VIEWS:
                memory.write(make_key(representations[index], episode, view),
                             make_value(initial[episode, identity[index]]))
        stages.append(score(memory, evaluation, labels, targets, episode + 1))
    before_correction = score(memory, evaluation, labels, targets, EPISODES)
    corrected = initial[1, 0].clone()
    corrected[2] = 1  # Later evidence says mother cooked it.
    # One new observation with explicitly supplied trust; no replay of prior episodes.
    image = synthetic_image(0, random.Random(seed + 4000))
    with torch.no_grad():
        representation = perception.encode(image_tensor(image).unsqueeze(0), "image")[0]
    memory.write(make_key(representation, 1, "current"), make_value(corrected), strength=128)
    targets[1, 1, 0] = corrected
    after = score(memory, evaluation, labels, targets, EPISODES)
    zero_control = score(OnlineMemory(), evaluation, labels, targets, EPISODES)
    mismatched = {episode: {modality: values.roll(12, dims=0)
                           for modality, values in inputs.items()}
                  for episode, inputs in evaluation.items()}
    mismatch_control = score(memory, mismatched, labels, targets, EPISODES)
    save_checkpoint(output / "weights.pt", perception, memory)
    _, restored = load_checkpoint(output / "weights.pt")
    persisted = all(torch.equal(value, restored.state_dict()[name])
                    for name, value in memory.state_dict().items())
    focus = {}
    for view in VIEWS:
        keys = make_key(evaluation[1]["audio"][labels[1] == 0], 1, view)
        focus[view] = describe(memory.recall(keys)[0].tolist())
    report = {"seed": seed, "stages": stages, "before_correction": before_correction,
              "after_correction": after, "meal": focus,
              "zero_memory_control": zero_control, "mismatched_input_control": mismatch_control,
              "unknown_episode_abstention_before_write": novelty,
              "writes": memory.writes.item(), "replayed_observations": 0,
              "memory_state_bytes": state_bytes, "checkpoint_bytes": (output / "weights.pt").stat().st_size,
              "perception_unchanged": all(torch.equal(frozen[name], value)
                                          for name, value in perception.state_dict().items()),
              "persistence_exact": persisted,
              "elapsed_seconds": round(time.perf_counter() - started, 3),
              "scope": "8 synthetic identities, 4 supplied episode indices, 2 supplied views; finite RLS memory"}
    report["accepted"] = all(metrics[modality]["exact"] >= .9
                             for metrics in [*stages, after] for modality in ("image", "audio"))
    report["accepted"] &= (focus["initial"]["autor"] == "pai" and focus["current"]["autor"] == "mae"
                           and all(novelty) and persisted and report["perception_unchanged"]
                           and all(control[modality]["exact"] < .3
                                   for control in (zero_control, mismatch_control)
                                   for modality in ("image", "audio")))
    examples = output / "examples"
    examples.mkdir()
    image.save(examples / "meal.png")
    save_audio(examples / "meal.wav", synthetic_audio(0, random.Random(seed + 5000)))
    (output / "expected.json").write_text(json.dumps(focus, indent=2), encoding="utf-8")
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
