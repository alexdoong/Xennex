"""A supervised sensory curriculum, not photographs, speech or human affect.

Four independent visual regions / frequency bands encode a synthetic activity,
appraisal, participant and setting. The field meanings are taught conventions.
Ground-truth categories returned by datasets are never supplied to inference.
"""
from __future__ import annotations

import itertools
import random

import torch
from PIL import Image, ImageDraw

from .signals import AUDIO_SAMPLES, COLORS, SAMPLE_RATE, image_tensor

from .experience_vocabulary import FIELDS, WORDS


def samples(values: tuple[int, ...], rng: random.Random,
            present: tuple[bool, ...] = (True, True, True, True)) -> tuple[torch.Tensor, torch.Tensor]:
    if len(values) != 4 or any(type(value) is not int or not 0 <= value < 4 for value in values):
        raise ValueError("Expected four synthetic categories.")
    if len(present) != 4 or any(type(value) is not bool for value in present):
        raise ValueError("Expected four sensor-region masks.")
    image = Image.new("RGB", (32, 32), (12, 12, 12))
    draw = ImageDraw.Draw(image)
    times = torch.arange(AUDIO_SAMPLES, dtype=torch.float32) / SAMPLE_RATE
    sound = torch.tensor([rng.uniform(-.008, .008) for _ in range(AUDIO_SAMPLES)])
    for field, value in enumerate(values):
        if not present[field]:
            continue
        x, y = (field % 2) * 16, (field // 2) * 16
        margin = rng.randint(2, 4)
        color = tuple(max(0, min(255, channel + rng.randint(-6, 6))) for channel in COLORS[value])
        draw.rectangle((x + margin, y + margin, x + 15 - margin, y + 15 - margin), fill=color)
        frequency = (300, 1000, 1800, 2600)[field] + value * 140 + rng.uniform(-2, 2)
        sound += rng.uniform(.12, .2) * torch.sin(2 * torch.pi * frequency * times + rng.uniform(0, 6.28))
    return image_tensor(image), sound


def dataset(seed: int, count: int = 1600, evaluation: bool = False) -> tuple:
    rng = random.Random(seed)
    # Withhold entire combinations; every component remains represented in train.
    combinations = [values for values in itertools.product(range(4), repeat=4)
                    if (sum((i + 1) * value for i, value in enumerate(values)) % 5 == 0) == evaluation]
    images, audio, labels = [], [], []
    for index in range(count):
        values = rng.choice(combinations)
        visible = tuple(rng.random() > .25 for _ in range(4)) if index % 3 else (True,) * 4
        image, sound = samples(values, rng, visible)
        images.append(image)
        audio.append(sound)
        labels.append([value if mask else 4 for value, mask in zip(values, visible)])
    return torch.stack(images), torch.stack(audio), torch.tensor(labels)


def stories(seed: int, episodes: int = 24, gap_probability: float = .25) -> list[dict]:
    """Annotations are evaluation/training targets, never a session input."""
    rng = random.Random(seed)
    records = []
    previous = None
    clock = 0.
    for episode in range(episodes):
        values = tuple(rng.randrange(4) for _ in range(4))
        while values == previous:
            values = tuple(rng.randrange(4) for _ in range(4))
        # Some new encounters have identical contents but an observable long gap.
        if previous is not None and rng.random() < gap_probability:
            values = previous
            gap = rng.uniform(2, 5)
        else:
            gap = rng.uniform(.1, .25)
        for frame in range(rng.randint(6, 12)):
            elapsed = gap if frame == 0 else rng.uniform(.1, .25)
            clock += elapsed
            visible = (True,) * 4 if frame == 0 or rng.random() > .35 else tuple(rng.random() > .3 for _ in range(4))
            image, sound = samples(values, rng, visible)
            records.append({"image": image, "audio": sound, "elapsed": elapsed,
                            "clock": clock, "boundary": frame == 0,
                            "episode": episode, "truth": values})
        previous = values
    return records
