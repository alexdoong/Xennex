"""Train/evaluate the isolated experiment. Reports never participate in recall."""
from __future__ import annotations

import copy
import json
import random
import time
from pathlib import Path

import torch
from torch.nn import functional as F

from .network import NeuralMemory, Perception, describe, load_checkpoint, save_checkpoint
from .signals import OBJECTS, bank, save_audio, synthetic_audio, synthetic_image


def learn_perception(model: Perception, images: torch.Tensor, audio: torch.Tensor,
                     labels: torch.Tensor, steps: int = 400) -> None:
    optimizer = torch.optim.Adam(model.parameters(), lr=.006)
    for _ in range(steps):
        indices = torch.randint(len(labels), (64,))
        visual = model.encode(images[indices], "image")
        acoustic = model.encode(audio[indices], "audio")
        target = model.anchors[labels[indices]]
        loss = F.mse_loss(visual, target) + F.mse_loss(acoustic, target)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
    model.freeze()


def associations(seed: int) -> torch.Tensor:
    """New experiences are assigned AFTER perceptual training, independently."""
    rng = random.Random(seed)
    names = list(range(OBJECTS))
    rng.shuffle(names)
    return torch.tensor([[rng.randrange(4), rng.randrange(4), name] for name in names])


def learn_memory(model: NeuralMemory, features: torch.Tensor, labels: torch.Tensor,
                 targets: torch.Tensor, steps: int = 250) -> None:
    optimizer = torch.optim.Adam(model.parameters(), lr=.02)
    model.train()
    for _ in range(steps):
        logits = model(features)
        loss = sum(F.cross_entropy(part, targets[labels, column])
                   for column, part in enumerate(logits))
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
    model.eval()


@torch.inference_mode()
def accuracy(model: NeuralMemory, features: torch.Tensor, labels: torch.Tensor,
             targets: torch.Tensor) -> dict[str, float]:
    correct = model.recall(features).eq(targets[labels])
    return {"exact": float(correct.all(dim=1).float().mean()),
            "attributes": float(correct.float().mean())}


def score_modalities(memory: NeuralMemory, features: dict[str, torch.Tensor],
                     labels: torch.Tensor, targets: torch.Tensor) -> dict:
    return {modality: accuracy(memory, values, labels, targets)
            for modality, values in features.items()}


def run(output: Path, seed: int = 17) -> dict:
    if not 0 <= seed <= 1_000_000:
        raise ValueError("Seed must be between 0 and 1000000.")
    output.mkdir(parents=True, exist_ok=False)
    torch.manual_seed(seed)
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    started = time.perf_counter()
    images, audio, labels = bank(seed + 100, 24)
    test_images, test_audio, test_labels = bank(seed + 200, 12)
    perception = Perception()
    learn_perception(perception, images, audio, labels)
    frozen = {key: value.clone() for key, value in perception.state_dict().items()}
    with torch.no_grad():
        train_features = perception.encode(images, "image").detach()
        test_features = {"image": perception.encode(test_images, "image"),
                         "audio": perception.encode(test_audio, "audio")}
    targets = associations(seed + 300)
    memory = NeuralMemory()
    report = {"format": 1, "seed": seed, "device": "cpu", "torch": torch.__version__,
              "scope": "synthetic closed-set experiment; not LLM integration",
              "training": "visual inputs only; replay of old latent examples",
              "objects": OBJECTS, "test_samples_per_modality": len(test_labels),
              "before": score_modalities(memory, test_features, test_labels, targets)}
    old_train, old_test = labels < 4, test_labels < 4
    learn_memory(memory, train_features[old_train], labels[old_train], targets)
    report["first_stage_old"] = score_modalities(
        memory, {key: value[old_test] for key, value in test_features.items()},
        test_labels[old_test], targets)
    no_replay = copy.deepcopy(memory)
    learn_memory(no_replay, train_features[~old_train], labels[~old_train], targets)
    report["second_stage_without_replay_old"] = score_modalities(
        no_replay, {key: value[old_test] for key, value in test_features.items()},
        test_labels[old_test], targets)
    learn_memory(memory, train_features, labels, targets)
    report["second_stage_with_replay"] = score_modalities(memory, test_features, test_labels, targets)
    corrected = targets.clone()
    corrected[0, 2] = (corrected[0, 2] + 3) % 8
    learn_memory(memory, train_features, labels, corrected)
    report["after_correction"] = score_modalities(memory, test_features, test_labels, corrected)
    report["perception_unchanged"] = all(torch.equal(frozen[key], value)
                                         for key, value in perception.state_dict().items())
    empty = copy.deepcopy(memory)
    with torch.no_grad():
        for parameter in empty.parameters():
            parameter.zero_()
    report["zero_memory_control"] = score_modalities(empty, test_features, test_labels, corrected)
    # Rotate object groups, avoiding accidental fixed points in the shuffled control.
    shifted = {key: value.roll(12, dims=0) for key, value in test_features.items()}
    report["mismatched_input_control"] = score_modalities(memory, shifted, test_labels, corrected)
    save_checkpoint(output / "weights.pt", perception, memory)
    restored_perception, restored_memory = load_checkpoint(output / "weights.pt")
    with torch.no_grad():
        restored_features = {"image": restored_perception.encode(test_images, "image"),
                             "audio": restored_perception.encode(test_audio, "audio")}
        report["checkpoint_predictions_identical"] = all(torch.equal(
            memory.recall(test_features[key]), restored_memory.recall(value))
            for key, value in restored_features.items())
    report["parameters"] = {"perception": sum(p.numel() for p in perception.parameters()),
                            "memory": sum(p.numel() for p in memory.parameters())}
    report["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    report["accepted"] = accepted(report)
    write_samples(output, seed + 400, corrected)
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def accepted(report: dict) -> bool:
    stages = ("first_stage_old", "second_stage_with_replay", "after_correction")
    successful = all(report[stage][modality]["exact"] >= .9
                     for stage in stages for modality in ("image", "audio"))
    controls = all(report["after_correction"][modality]["exact"] >
                   max(report[control][modality]["exact"] for control in
                       ("before", "zero_memory_control", "mismatched_input_control"))
                   for modality in ("image", "audio"))
    return successful and controls and report["perception_unchanged"] and report[
        "checkpoint_predictions_identical"]


def write_samples(output: Path, seed: int, targets: torch.Tensor) -> None:
    rng = random.Random(seed)
    examples = output / "examples"
    examples.mkdir()
    expected = {}
    for object_id in range(OBJECTS):
        name = f"object-{object_id}"
        synthetic_image(object_id, rng).save(examples / f"{name}.png")
        save_audio(examples / f"{name}.wav", synthetic_audio(object_id, rng))
        expected[name] = describe(targets[object_id].tolist())
    # Evaluation-only file; query never opens it.
    (output / "expected.json").write_text(json.dumps(expected, indent=2), encoding="utf-8")
