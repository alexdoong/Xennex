"""Online next-observation prediction from native experience, without names.

This is a supplied linear model family, not open causal understanding. Targets
arrive as real percepts; missing modalities, idle time and predictions never
teach themselves. Acquisition time controls ordering and continuity.
"""
from __future__ import annotations

import copy

import torch
from torch.nn import functional as F

from .concept_memory import scalar
from .native_sensor import DIMENSION, MODALITIES, NativeObservation
from .online_memory import OnlineMemory

KEY_SIZE = 4 * DIMENSION + 5
CONTINUITY_SECONDS = 2.


class NativeDynamics:
    def __init__(self, clock=0., historical_frames=0):
        self.banks = {name: OnlineMemory(KEY_SIZE, DIMENSION) for name in MODALITIES}
        self.clock = clock
        self.historical_frames = historical_frames
        self.frames = self.pairs = self.late = self.discontinuous = 0
        self.last = None
        self.last_error = {}

    def advance(self, now):
        scalar(now, self.clock, 1e12)
        self.clock = now

    def key(self):
        frame = self.last
        return torch.cat((frame['values'].flatten(), frame['context'], frame['known'].double(),
                          torch.tensor([frame['gap'], 1.], dtype=torch.float64)))

    def predict(self, now=None):
        now = self.clock if now is None else scalar(now, self.clock, 1e12)
        result = {'kind': 'next_observation_hypothesis', 'supported': False,
                  'modalities': {}, 'autobiographical_write': False, 'confidence_is_calibrated': False}
        if self.last is None:
            return {**result, 'reason': 'no_native_context'}
        if now - self.last['acquired_at'] > CONTINUITY_SECONDS:
            return {**result, 'reason': 'old_native_context'}
        key = self.key()
        for name, bank in self.banks.items():
            vector = bank.weights @ key
            if int(bank.writes) >= 3 and bank.variance(key) <= 25 and vector.norm() >= .1:
                result['modalities'][name] = F.normalize(vector.float(), dim=0)
        return {**result, 'supported': bool(result['modalities']),
                'reason': 'supported' if result['modalities'] else 'outside_learned_coverage'}

    @torch.no_grad()
    def observe(self, packets, now):
        if not isinstance(packets, (list, tuple)) or not 1 <= len(packets) <= 3 or any(not isinstance(packet, NativeObservation) for packet in packets):
            raise ValueError('Native prediction requires one external synchronized frame.')
        for packet in packets:
            packet.validate()
            scalar(packet.acquired_at, 0, now)
            if packet.origin == 'self':
                raise ValueError('Predictions cannot teach themselves as external experience.')
        if len({packet.modality for packet in packets}) != len(packets) or max(packet.acquired_at for packet in packets) - min(packet.acquired_at for packet in packets) > .025:
            raise ValueError('Native prediction frame is not synchronized.')
        self.advance(now)
        at = max(packet.acquired_at for packet in packets)
        self.frames += 1
        self.last_error = {}
        if self.last is not None and at <= self.last['acquired_at']:
            self.late += 1
            return {'learned_pair': False, 'reason': 'nonsequential_native_frame', 'errors': {}}
        gap = 0. if self.last is None else at - self.last['acquired_at']
        joined = self.last is not None and gap <= CONTINUITY_SECONDS
        if joined:
            key = self.key()  # Only context available before this target arrived.
            candidates = {}
            for packet in packets:
                bank = self.banks[packet.modality]
                prediction = bank.weights @ key
                if int(bank.writes) >= 3 and bank.variance(key) <= 25 and prediction.norm() >= .1:
                    predicted = F.normalize(prediction, dim=0)
                    self.last_error[packet.modality] = float((predicted - packet.latent.double()).square().sum())
                candidate = copy.deepcopy(bank)
                candidate.write(key, packet.latent.double(), strength=10.)
                if any(not torch.isfinite(tensor).all() for tensor in candidate.state_dict().values()):
                    raise ValueError('Native prediction update diverged; earlier weights retained.')
                candidates[packet.modality] = candidate
            self.banks.update(candidates)
            self.pairs += 1
        elif self.last is not None:
            self.discontinuous += 1
        values = torch.zeros(3, DIMENSION, dtype=torch.float64)
        known = torch.zeros(3, dtype=torch.bool)
        for packet in packets:
            slot = MODALITIES.index(packet.modality)
            values[slot] = packet.latent.double()
            known[slot] = True
        joint = F.normalize(values[known].mean(0), dim=0)
        context = joint if not joined else F.normalize(.8 * self.last['context'] + .2 * joint, dim=0)
        self.last = {'values': values, 'context': context, 'known': known, 'acquired_at': at,
                     'received_at': now, 'gap': min(gap, CONTINUITY_SECONDS)}
        return {'learned_pair': joined, 'reason': 'observed_transition' if joined else 'new_native_context',
                'errors': self.last_error.copy(), 'prediction_is_hypothesis': True}

    def snapshot(self):
        return {'format': 1, 'clock': self.clock, 'historical_frames': self.historical_frames,
                'frames': self.frames, 'pairs': self.pairs, 'late': self.late, 'discontinuous': self.discontinuous,
                'last': copy.deepcopy(self.last), 'last_error': self.last_error.copy(),
                'banks': {name: {key: tensor.clone() for key, tensor in bank.state_dict().items()}
                          for name, bank in self.banks.items()}}


def restore(payload, clock, frame_count):
    expected = {'format', 'clock', 'historical_frames', 'frames', 'pairs', 'late', 'discontinuous', 'last', 'last_error', 'banks'}
    if not isinstance(payload, dict) or set(payload) != expected or type(payload['format']) is not int or payload['format'] != 1 or payload['clock'] != clock:
        raise ValueError('Invalid native dynamics checkpoint.')
    for key in ('historical_frames', 'frames', 'pairs', 'late', 'discontinuous'):
        if type(payload[key]) is not int or not 0 <= payload[key] <= frame_count:
            raise ValueError('Invalid native dynamics count.')
    if payload['historical_frames'] + payload['frames'] != frame_count or payload['pairs'] + payload['late'] + payload['discontinuous'] != max(0, payload['frames'] - 1):
        raise ValueError('Native prediction count disagrees with observations.')
    result = NativeDynamics(clock, payload['historical_frames'])
    for key in ('frames', 'pairs', 'late', 'discontinuous'):
        setattr(result, key, payload[key])
    last = payload['last']
    if (last is None) != (result.frames == 0):
        raise ValueError('Native prediction lost its current context.')
    if last is not None:
        if not isinstance(last, dict) or set(last) != {'values', 'context', 'known', 'acquired_at', 'received_at', 'gap'}:
            raise ValueError('Invalid native prediction context fields.')
        values, known = last['values'], last['known']
        if not isinstance(values, torch.Tensor) or values.dtype != torch.float64 or values.device.type != 'cpu' or values.shape != (3, DIMENSION) or not torch.isfinite(values).all() or not isinstance(known, torch.Tensor) or known.dtype != torch.bool or known.device.type != 'cpu' or known.shape != (3,) or not known.any() or values[~known].count_nonzero() or not torch.allclose(values[known].norm(dim=-1), torch.ones(int(known.sum()), dtype=torch.float64), atol=1e-5, rtol=0):
            raise ValueError('Invalid native prediction context vectors.')
        scalar(last['acquired_at'], 0, last['received_at'])
        scalar(last['received_at'], 0, clock)
        scalar(last['gap'], 0, CONTINUITY_SECONDS)
        context = last['context']
        if not isinstance(context, torch.Tensor) or context.device.type != 'cpu' or context.dtype != torch.float64 or context.shape != (DIMENSION,) or not torch.isfinite(context).all() or context.norm() > 1.00001:
            raise ValueError('Invalid native temporal context.')
    errors = payload['last_error']
    if not isinstance(errors, dict) or any(name not in MODALITIES for name in errors):
        raise ValueError('Invalid native prediction errors.')
    for error in errors.values():
        scalar(error, 0, 4.00001)
    saved = payload['banks']
    if not isinstance(saved, dict) or set(saved) != set(MODALITIES):
        raise ValueError('Invalid native prediction banks.')
    for name, bank in result.banks.items():
        state, reference = saved[name], bank.state_dict()
        if not isinstance(state, dict) or set(state) != set(reference) or any(not isinstance(t, torch.Tensor) or t.device.type != 'cpu' or t.dtype != reference[k].dtype or t.shape != reference[k].shape or not torch.isfinite(t).all() for k, t in state.items()):
            raise ValueError('Invalid native prediction tensors.')
        bank.load_state_dict(state)
        if not 0 <= int(bank.writes) <= result.pairs or bank.weights.abs().max() > 10000 or not torch.allclose(bank.precision, bank.precision.T, atol=1e-8, rtol=0) or torch.linalg.cholesky_ex(bank.precision).info.item() != 0:
            raise ValueError('Invalid native prediction covariance/count.')
        if not int(bank.writes) and (bank.weights.count_nonzero() or not torch.equal(bank.precision, torch.eye(KEY_SIZE, dtype=torch.float64) * 1000)):
            raise ValueError('Untrained native predictor contains learned state.')
    result.last, result.last_error = copy.deepcopy(last), errors.copy()
    return result
