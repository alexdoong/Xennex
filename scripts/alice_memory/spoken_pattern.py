"""Compact acoustic examples of explicitly taught isolated words."""
import math
from functools import lru_cache

import numpy as np
import torch

WIDTH = 24
MIN_FRAMES = 8
MAX_FRAMES = 240
WINDOW, HOP, FFT = 400, 160, 512
MAX_DISTANCE = .30
MIN_MARGIN = .08


@lru_cache(maxsize=1)
def spectrum_basis():
    def mel(hertz):
        return 2595 * np.log10(1 + hertz / 700)
    hertz = np.fft.rfftfreq(FFT, 1 / 16000)
    centers = 700 * (10 ** (np.linspace(mel(100), mel(7400), 34) / 2595) - 1)
    lower, center, upper = centers[:-2, None], centers[1:-1, None], centers[2:, None]
    filters = np.maximum(0, np.minimum((hertz - lower) / (center - lower), (upper - hertz) / (upper - center)))
    order = np.arange(1, 13)
    dct = np.cos(np.pi / 32 * order[:, None] * (np.arange(32) + .5)) * math.sqrt(2 / 32)
    return np.hanning(WINDOW), filters, dct * (np.sqrt(order) / 6.)[:, None]


def describe(samples):
    """Convert mono 16 kHz PCM to one bounded cepstral sequence."""
    if not isinstance(samples, np.ndarray) or samples.ndim != 1 or not 1 <= len(samples) <= 160000:
        raise ValueError('An acoustic word requires bounded mono 16 kHz samples.')
    if not np.isfinite(samples).all():
        raise ValueError('An acoustic word requires finite samples.')
    audio = np.pad(samples, (0, max(0, WINDOW - len(samples))))
    windows = np.lib.stride_tricks.sliding_window_view(audio, WINDOW)[::HOP]
    energy = np.sqrt((windows * windows).mean(axis=1))
    active = np.flatnonzero(energy > max(1e-4, energy.max() * .03))
    if len(active) < 1:
        return None
    start, end = int(active[0]), int(active[-1]) + 1
    if not MIN_FRAMES <= end - start <= MAX_FRAMES:
        return None
    window, filters, dct = spectrum_basis()
    filtered = np.concatenate((audio[:1], audio[1:] - .97 * audio[:-1]))
    frames = np.lib.stride_tricks.sliding_window_view(filtered, WINDOW)[::HOP][start:end]
    power = np.abs(np.fft.rfft(frames * window, n=FFT)) ** 2
    static = np.log(np.maximum(power @ filters.T, 1e-6)) @ dct.T
    padded = np.pad(static, ((2, 2), (0, 0)), mode='edge')
    derivative = (padded[4:] - padded[:-4]) * .5
    return torch.from_numpy(np.concatenate((static, derivative), axis=1).astype(np.float32))


def validate(pattern):
    if (not isinstance(pattern, torch.Tensor) or pattern.device.type != 'cpu' or pattern.dtype != torch.float32
            or pattern.layout != torch.strided or pattern.requires_grad
            or pattern.ndim != 2 or not MIN_FRAMES <= pattern.shape[0] <= MAX_FRAMES
            or pattern.shape[1] != WIDTH or not torch.isfinite(pattern).all() or pattern.abs().max() > 100):
        raise ValueError('Invalid acoustic word descriptor.')


def distance(reference, cue):
    """Align whole isolated clips with bounded local speed changes."""
    length, width = len(reference), len(cue)
    if width * 2 < length or length * 2 < width:
        return math.inf
    left, right = reference.numpy(), cue.numpy()
    squared = (left ** 2).mean(1)[:, None] + (right ** 2).mean(1)[None, :] - 2 * (left @ right.T) / WIDTH
    cost = np.sqrt(np.maximum(squared, 0))
    table = np.full((length + 1, width + 1), np.inf)
    table[0, 0] = 0.
    for diagonal in range(2, length + width + 1):
        row = np.arange(max(1, diagonal - width), min(length, diagonal - 1) + 1)
        column = diagonal - row
        local = cost[row - 1, column - 1]
        same_rate = table[row - 1, column - 1] + local
        faster = np.where(row >= 2, table[row - 2, column - 1] + local + cost[row - 2, column - 1] + .06, np.inf)
        slower = np.where(column >= 2, table[row - 1, column - 2] + (local + cost[row - 1, column - 2]) * .5 + .06, np.inf)
        table[row, column] = np.minimum(same_rate, np.minimum(faster, slower))
    return float(table[length, width]) / length
