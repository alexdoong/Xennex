"""Synthetic pixels and PCM audio. Object IDs are fixture labels, never inputs."""
from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path

import torch
from PIL import Image, ImageDraw

OBJECTS = 8
IMAGE_SIZE = 32
SAMPLE_RATE = 8000
AUDIO_SAMPLES = 1024
COLORS = ((220, 45, 50), (45, 210, 55), (50, 55, 220), (210, 200, 40),
          (210, 45, 205), (40, 200, 210), (220, 120, 35), (130, 80, 210))


def image_tensor(image: Image.Image) -> torch.Tensor:
    pixels = image.convert("RGB").resize((IMAGE_SIZE, IMAGE_SIZE))
    return torch.tensor(list(pixels.tobytes()), dtype=torch.float32).reshape(
        IMAGE_SIZE, IMAGE_SIZE, 3).permute(2, 0, 1) / 255


def synthetic_image(object_id: int, rng: random.Random) -> Image.Image:
    image = Image.new("RGB", (IMAGE_SIZE, IMAGE_SIZE), (12, 12, 12))
    draw = ImageDraw.Draw(image)
    x, y, radius = rng.randint(12, 20), rng.randint(12, 20), rng.randint(7, 10)
    color = tuple(max(0, min(255, value + rng.randint(-10, 10)))
                  for value in COLORS[object_id])
    bounds = (x - radius, y - radius, x + radius, y + radius)
    if object_id % 2 == 0:
        draw.ellipse(bounds, fill=color)
        return image
    draw.rectangle(bounds, fill=color)
    return image


def synthetic_audio(object_id: int, rng: random.Random) -> torch.Tensor:
    frequency = 300 + object_id * 210 + rng.uniform(-6, 6)
    phase, amplitude = rng.uniform(0, 2 * math.pi), rng.uniform(.3, .7)
    times = torch.arange(AUDIO_SAMPLES, dtype=torch.float32) / SAMPLE_RATE
    noise = torch.tensor([rng.uniform(-.015, .015) for _ in range(AUDIO_SAMPLES)])
    return amplitude * torch.sin(2 * math.pi * frequency * times + phase) + noise


def audio_features(samples: torch.Tensor) -> torch.Tensor:
    """Standard spectral transform, followed by a learned audio encoder."""
    if samples.shape[-1] != AUDIO_SAMPLES or not torch.isfinite(samples).all():
        raise ValueError("Expected 1024 finite PCM samples at 8000 Hz.")
    spectrum = torch.stft(samples, n_fft=512, hop_length=256,
                          window=torch.hann_window(512), return_complex=True)
    features = torch.log1p(spectrum.abs()).mean(dim=-1)
    return features / features.norm(dim=-1, keepdim=True).clamp_min(1e-8)


def bank(seed: int, examples: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    rng = random.Random(seed)
    labels = torch.arange(OBJECTS).repeat_interleave(examples)
    images = torch.stack([image_tensor(synthetic_image(int(label), rng)) for label in labels])
    audio = torch.stack([synthetic_audio(int(label), rng) for label in labels])
    return images, audio_features(audio), labels


def save_audio(path: Path, samples: torch.Tensor) -> None:
    pcm = [round(float(value) * 32767) for value in samples.clamp(-1, 1)]
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(SAMPLE_RATE)
        stream.writeframes(struct.pack(f"<{len(pcm)}h", *pcm))


def load_image(path: Path) -> torch.Tensor:
    with Image.open(path) as image:
        if image.width * image.height > 4_000_000:
            raise ValueError("Experiment input is limited to 4 million pixels.")
        return image_tensor(image).unsqueeze(0)


def load_audio(path: Path) -> torch.Tensor:
    with wave.open(str(path), "rb") as stream:
        if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate(),
                stream.getnframes()) != (1, 2, SAMPLE_RATE, AUDIO_SAMPLES):
            raise ValueError("Use mono PCM16 WAV, 8000 Hz, exactly 1024 samples.")
        values = struct.unpack(f"<{AUDIO_SAMPLES}h", stream.readframes(AUDIO_SAMPLES))
    return audio_features(torch.tensor(values, dtype=torch.float32).unsqueeze(0) / 32767)
