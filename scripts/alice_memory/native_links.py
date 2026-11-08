"""Cross-modal latent expectations learned from attended co-occurrences.

Linear correspondence is the supplied model family. A prediction is neither a
sensory recollection nor a newly observed event, and never trains itself.
"""
from __future__ import annotations

import copy
import math

import torch
from torch.nn import functional as F

from .concept_memory import scalar
from .native_sensor import DIMENSION, MODALITIES, NativeObservation
from .online_memory import OnlineMemory
from .semantic_retention import DEFAULT_SECONDS, RULE, spectrum, view

KEY_SIZE = DIMENSION + 1
CONTEXT_KEY_SIZE = DIMENSION + 8 + 16 * 8 + 1
FEATURE_BASIS = 'dct128-source1to16-context17to24-v1'
PAIRS = tuple(source + ':' + target for source in MODALITIES for target in MODALITIES if source != target)


def key(packet):
    return torch.cat((packet.latent.double(), torch.ones(1, dtype=torch.float64)))


def context_value(context):
    if not isinstance(context, torch.Tensor) or context.device.type != 'cpu' or context.dtype not in (torch.float32, torch.float64) or context.shape != (DIMENSION,) or not torch.isfinite(context).all() or context.norm() > 1.00001:
        raise ValueError('Invalid previous native context.')
    return context.double()


def contextual_key(packet, context):
    # Fixed orthogonal compression supplies interactions without a full128²
    # outer product. The correspondence coefficients, not this basis, learn.
    positions = torch.arange(DIMENSION, dtype=torch.float64) + .5
    frequencies = torch.arange(1, 25, dtype=torch.float64)
    basis = torch.cos(math.pi / DIMENSION * frequencies[:, None] * positions) * math.sqrt(2. / DIMENSION)
    visual = (basis[:16] @ packet.latent.double()) * math.sqrt(DIMENSION / 16.)
    history = (basis[16:] @ context_value(context)) * math.sqrt(DIMENSION / 8.)
    return torch.cat((packet.latent.double(), history, torch.outer(visual, history).flatten(),
                      torch.ones(1, dtype=torch.float64)))


class NativeLinks:
    def __init__(self, clock=0., historical_frames=0, retention_seconds=DEFAULT_SECONDS):
        scalar(retention_seconds, 1., 1e12)
        self.retention_seconds = float(retention_seconds)
        self.clock = clock
        self.historical_frames = historical_frames
        self.frames = 0
        self.banks = {pair: OnlineMemory(KEY_SIZE, DIMENSION) for pair in PAIRS}
        self.context_frames = 0
        self.contextual_banks = {pair: OnlineMemory(CONTEXT_KEY_SIZE, DIMENSION) for pair in PAIRS}
        self.updated_at = {group: {pair: None for pair in PAIRS} for group in ('general', 'contextual')}
        self._spectra = {}

    def aged(self, pair, conditioned, now):
        group = 'contextual' if conditioned else 'general'
        bank = (self.contextual_banks if conditioned else self.banks)[pair]
        anchor = self.updated_at[group][pair]
        if anchor is None or now == anchor:
            return bank.weights, bank.precision
        cached = self._spectra.get((group, pair))
        if cached is None or cached[0] is not bank or not torch.equal(cached[1], bank.precision):
            information, basis = spectrum(bank.precision)
            cached = (bank, bank.precision.clone(), information, basis)
            self._spectra[group, pair] = cached
        return view(bank.weights, cached[2], cached[3], now - anchor, self.retention_seconds)

    def advance(self, now):
        self.clock = scalar(now, self.clock, 1e12)

    @torch.no_grad()
    def observe(self, packets, now, context=None):
        scalar(now, self.clock, 1e12)
        if not isinstance(packets, (list, tuple)) or not 1 <= len(packets) <= 3 or any(not isinstance(packet, NativeObservation) for packet in packets):
            raise ValueError('Cross-modal learning requires an external synchronized frame.')
        for packet in packets:
            packet.validate()
            scalar(packet.acquired_at, 0, now)
            if packet.origin == 'self':
                raise ValueError('Cross-modal hypotheses cannot teach themselves.')
        if len({packet.modality for packet in packets}) != len(packets) or max(packet.acquired_at for packet in packets) - min(packet.acquired_at for packet in packets) > .025:
            raise ValueError('Cross-modal learning requires distinct synchronized modalities.')
        if self.frames + self.historical_frames >= 1000000:
            raise ValueError('Cross-modal lifetime budget reached.')
        contextual = context is not None and context_value(context).norm() >= .05
        candidates, conditioned, errors = {}, {}, {}
        for source in packets:
            for target in packets:
                if source.modality == target.modality:
                    continue
                pair = source.modality + ':' + target.modality
                prior_context = context if contextual and int(self.contextual_banks[pair].writes) else None
                prior = self._predict(source, target.modality, prior_context, now)
                if prior['supported']:
                    errors[pair] = float((prior['latent'].double() - target.latent.double()).square().sum())
                candidate = copy.deepcopy(self.banks[pair])
                weights, precision = self.aged(pair, False, now)
                candidate.weights.copy_(weights)
                candidate.precision.copy_(precision)
                candidate.write(key(source), target.latent.double(), strength=10.)
                if any(not torch.isfinite(value).all() for value in candidate.state_dict().values()):
                    raise ValueError('Cross-modal update diverged; prior links retained.')
                candidates[pair] = candidate
                if contextual:
                    candidate = copy.deepcopy(self.contextual_banks[pair])
                    weights, precision = self.aged(pair, True, now)
                    candidate.weights.copy_(weights)
                    candidate.precision.copy_(precision)
                    candidate.write(contextual_key(source, context), target.latent.double(), strength=10.)
                    if any(not torch.isfinite(value).all() for value in candidate.state_dict().values()):
                        raise ValueError('Contextual cross-modal update diverged; prior links retained.')
                    conditioned[pair] = candidate
        self.banks.update(candidates)
        self.contextual_banks.update(conditioned)
        for group, updates in (('general', candidates), ('contextual', conditioned)):
            for pair in updates:
                self.updated_at[group][pair] = now
                self._spectra.pop((group, pair), None)
        self.context_frames += int(bool(conditioned))
        self.frames += 1
        self.clock = now
        return {'learned_pairs': sorted(candidates), 'conditioned_pairs': sorted(conditioned), 'errors': errors,
                'kind': 'observed_co_occurrence', 'prediction_is_hypothesis': True}

    @torch.no_grad()
    def predict(self, packet, target, context=None):
        return self._predict(packet, target, context, self.clock)

    @torch.no_grad()
    def _predict(self, packet, target, context, now):
        if not isinstance(packet, NativeObservation):
            raise ValueError('Cross-modal expectation requires a typed cue.')
        packet.validate()
        if target not in MODALITIES or target == packet.modality:
            raise ValueError('Cross-modal target must be another modality.')
        conditioned = context is not None
        if conditioned:
            context = context_value(context)
        pair = packet.modality + ':' + target
        bank = (self.contextual_banks if conditioned else self.banks)[pair]
        result = {'supported': False, 'kind': 'cross_modal_expectation', 'source_modality': packet.modality,
                  'target_modality': target, 'latent': None, 'training_pairs': int(bank.writes),
                  'conditioned_on_context': conditioned, 'confidence_is_calibrated': False,
                  'directly_observed': False, 'autobiographical_write': False,
                  'familiarity': 0., 'retention_rule': RULE}
        if conditioned and context.norm() < .05:
            return {**result, 'reason': 'no_conditioning_context'}
        if not int(bank.writes):
            return {**result, 'reason': 'no_observed_correspondence'}
        cue = contextual_key(packet, context) if conditioned else key(packet)
        weights, precision = self.aged(pair, conditioned, now)
        variance = float(cue @ precision @ cue)
        vector = weights @ cue
        result['familiarity'] = max(0., min(1., 1. - variance / (1000. * float(cue @ cue))))
        result['prediction_norm'] = float(vector.norm())
        if variance > 25. or vector.norm() < .1:
            return {**result, 'reason': 'outside_learned_coverage', 'variance': variance}
        return {**result, 'supported': True, 'reason': 'supported', 'variance': variance,
                'latent': F.normalize(vector.float(), dim=0)}

    def snapshot(self):
        return {'format': 3, 'clock': self.clock, 'historical_frames': self.historical_frames,
                'retention_rule': RULE, 'retention_seconds': self.retention_seconds,
                'updated_at': copy.deepcopy(self.updated_at),
                'frames': self.frames, 'banks': {pair: {key: value.clone() for key, value in bank.state_dict().items()}
                                               for pair, bank in self.banks.items()},
                'context_frames': self.context_frames, 'feature_basis': FEATURE_BASIS,
                'contextual_banks': {pair: {key: value.clone() for key, value in bank.state_dict().items()}
                                     for pair, bank in self.contextual_banks.items()}}


def restore(payload, clock, frame_count):
    fields = {'format', 'clock', 'historical_frames', 'frames', 'banks'}
    if isinstance(payload, dict) and payload.get('format') in (2, 3):
        fields.update(('context_frames', 'feature_basis', 'contextual_banks'))
    if isinstance(payload, dict) and payload.get('format') == 3:
        fields.update(('retention_rule', 'retention_seconds', 'updated_at'))
    if not isinstance(payload, dict) or set(payload) != fields or type(payload['format']) is not int or payload['format'] not in (1, 2, 3) or payload['clock'] != clock:
        raise ValueError('Invalid cross-modal link checkpoint.')
    for name in ('historical_frames', 'frames'):
        if type(payload[name]) is not int or not 0 <= payload[name] <= frame_count:
            raise ValueError('Invalid cross-modal lifetime counts.')
    if payload['historical_frames'] + payload['frames'] != frame_count:
        raise ValueError('Cross-modal learning lost its acquired frames.')
    result = NativeLinks(clock, payload['historical_frames'])
    result.frames = payload['frames']
    if payload['format'] in (2, 3):
        if payload['feature_basis'] != FEATURE_BASIS or type(payload['context_frames']) is not int or not 0 <= payload['context_frames'] <= result.frames:
            raise ValueError('Invalid contextual cross-modal basis/count.')
        result.context_frames = payload['context_frames']
        restore_banks(payload['contextual_banks'], result.contextual_banks, result.context_frames)
        count = sum(int(bank.writes) for bank in result.contextual_banks.values())
        if not 2 * result.context_frames <= count <= 6 * result.context_frames:
            raise ValueError('Contextual frame count lost its co-occurrences.')
    restore_banks(payload['banks'], result.banks, result.frames)
    if any(int(result.contextual_banks[pair].writes) > int(result.banks[pair].writes) for pair in PAIRS):
        raise ValueError('Contextual correspondence has more writes than observed pairs.')
    if payload['format'] == 3:
        if payload['retention_rule'] != RULE:
            raise ValueError('Invalid semantic retention policy.')
        result.retention_seconds = float(scalar(payload['retention_seconds'], 1., 1e12))
        stamps = payload['updated_at']
        if not isinstance(stamps, dict) or set(stamps) != {'general', 'contextual'}:
            raise ValueError('Invalid semantic retention anchors.')
        for group, banks in (('general', result.banks), ('contextual', result.contextual_banks)):
            if not isinstance(stamps[group], dict) or set(stamps[group]) != set(PAIRS):
                raise ValueError('Invalid semantic pair anchors.')
            for pair, bank in banks.items():
                stamp = stamps[group][pair]
                if (stamp is None) != (int(bank.writes) == 0):
                    raise ValueError('Semantic anchor lost its observed correspondence.')
                if stamp is not None:
                    scalar(stamp, 0, clock)
                    spectrum(bank.precision)
                if stamp != stamps[group][pair.split(':')[1] + ':' + pair.split(':')[0]]:
                    raise ValueError('Semantic anchors lost reciprocal acquisition time.')
        result.updated_at = copy.deepcopy(stamps)
    else:
        # No historical aging or replay: legacy weights start at checkpoint time.
        for group, banks in (('general', result.banks), ('contextual', result.contextual_banks)):
            result.updated_at[group] = {pair: clock if int(bank.writes) else None for pair, bank in banks.items()}
    return result


def restore_banks(saved_banks, banks, max_writes):
    if not isinstance(saved_banks, dict) or set(saved_banks) != set(PAIRS):
        raise ValueError('Invalid cross-modal learned pairs.')
    for pair, bank in banks.items():
        saved, expected = saved_banks[pair], bank.state_dict()
        if not isinstance(saved, dict) or set(saved) != set(expected) or any(not isinstance(tensor, torch.Tensor) or tensor.device.type != 'cpu' or tensor.dtype != expected[name].dtype or tensor.shape != expected[name].shape or not torch.isfinite(tensor).all() for name, tensor in saved.items()):
            raise ValueError('Invalid cross-modal tensors.')
        bank.load_state_dict(saved)
        writes = int(bank.writes)
        if not 0 <= writes <= max_writes or bank.weights.abs().max() > 10000 or not torch.allclose(bank.precision, bank.precision.T, atol=1e-8, rtol=0) or torch.linalg.cholesky_ex(bank.precision).info.item() != 0:
            raise ValueError('Invalid cross-modal covariance/count.')
        if writes == 0 and (bank.weights.count_nonzero() or not torch.equal(bank.precision, torch.eye(bank.precision.shape[0], dtype=torch.float64) * 1000)):
            raise ValueError('Untrained cross-modal pair contains learned state.')
    if any(int(banks[source + ':' + target].writes) != int(banks[target + ':' + source].writes)
           for source in MODALITIES for target in MODALITIES if source != target):
        raise ValueError('Cross-modal correspondence lost its reciprocal acquisition count.')
