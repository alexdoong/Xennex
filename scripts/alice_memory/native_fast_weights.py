"""Exact RLS factors for at most three writes in a native sensory moment.

These are weight/covariance factors, not a table queried by matching examples.
With P initially 1000 I, each RLS update adds one outer product to W and
subtracts one outer product from P. Queries evaluate those factors directly.
"""
from __future__ import annotations

import torch

KEY_SIZE = 132
VALUE_SIZE = 384
RANK = 3


class NativeFastWeights:
    def __init__(self):
        self.inputs = torch.zeros(RANK, KEY_SIZE, dtype=torch.float64)
        self.outputs = torch.zeros(RANK, VALUE_SIZE, dtype=torch.float64)
        self.covariance = torch.zeros(RANK, KEY_SIZE, dtype=torch.float64)
        self.writes = 0

    def variance(self, key):
        return float(1000. * (key @ key) - ((self.covariance[:self.writes] @ key) ** 2).sum())

    def read(self, key):
        return (self.inputs[:self.writes] @ key) @ self.outputs[:self.writes]

    def write(self, key, value):
        if self.writes >= RANK or key.shape != (KEY_SIZE,) or value.shape != (VALUE_SIZE,) or key.dtype != torch.float64 or value.dtype != torch.float64 or not torch.isfinite(key).all() or not torch.isfinite(value).all():
            raise ValueError("Invalid native fast-weight update.")
        projected = 1000. * key - self.covariance[:self.writes].T @ (self.covariance[:self.writes] @ key)
        denominator = .1 + key @ projected
        if denominator <= 0 or not torch.isfinite(denominator):
            raise ValueError("Native fast-weight covariance diverged.")
        index = self.writes
        self.outputs[index] = value - self.read(key)
        self.inputs[index] = projected / denominator
        self.covariance[index] = projected / denominator.sqrt()
        self.writes += 1

    def snapshot(self):
        return {'inputs': self.inputs.clone(), 'outputs': self.outputs.clone(),
                'covariance': self.covariance.clone(), 'writes': self.writes}


def restore(payload):
    expected = {'inputs', 'outputs', 'covariance', 'writes'}
    if not isinstance(payload, dict) or set(payload) != expected or type(payload['writes']) is not int or not 1 <= payload['writes'] <= RANK:
        raise ValueError("Invalid native fast-weight fields/rank.")
    result = NativeFastWeights()
    for name, shape in (('inputs', (RANK, KEY_SIZE)), ('outputs', (RANK, VALUE_SIZE)), ('covariance', (RANK, KEY_SIZE))):
        value = payload[name]
        if not isinstance(value, torch.Tensor) or value.device.type != 'cpu' or value.dtype != torch.float64 or value.shape != shape or not torch.isfinite(value).all() or value.abs().max() > 10000:
            raise ValueError("Invalid native fast-weight factors.")
        if value[payload['writes']:].count_nonzero():
            raise ValueError("Unused native factor rows contain hidden state.")
        setattr(result, name, value.clone())
    result.writes = payload['writes']
    spectrum = torch.linalg.eigvalsh(result.covariance[:result.writes] @ result.covariance[:result.writes].T)
    if spectrum.max() >= 1000. + 1e-8:
        raise ValueError("Native covariance factors are not positive definite.")
    return result
