"""Learned consequence values select which modalities enter acquisition.

Action set, exploration and utility are supplied capabilities. Values are
learned from externally sourced feedback, not from claiming to understand.
Quiet is an available allocation, not a penalty or a subjective state.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict

import torch

from .concept_memory import scalar
from .importance import Consequence
from .native_sensor import DIMENSION, MODALITIES
from .native_reference import validate_reference
from .online_memory import OnlineMemory

ACTIONS = (*MODALITIES, 'all', 'quiet')
MODES = ('full', 'learned', 'quiet')
KEY_SIZE = DIMENSION + 1


class NativeAttention:
    def __init__(self):
        self.mode = 'full'
        self.next_id = 1
        self.banks = {action: OnlineMemory(KEY_SIZE, 3) for action in ACTIONS}
        self.visits = {action: 0 for action in ACTIONS}
        self.pending = {}
        self.sources = []

    def configure(self, mode):
        if mode not in MODES:
            raise ValueError('Invalid native attention mode.')
        self.mode = mode

    def choose(self, context, available, now):
        scalar(now, 0, 1e12)
        if not isinstance(context, torch.Tensor) or context.shape != (DIMENSION,) or context.dtype != torch.float32 or context.device.type != 'cpu' or not torch.isfinite(context).all() or context.norm() > 1.00001:
            raise ValueError('Attention requires the preceding bounded native context.')
        if not isinstance(available, (list, tuple)) or not 1 <= len(available) <= 3 or len(set(available)) != len(available) or any(name not in MODALITIES for name in available):
            raise ValueError('Attention requires available modality names, not future contents.')
        for number in list(self.pending):
            if now > self.pending[number]['issued'] + 60:
                del self.pending[number]
        if self.mode != 'learned':
            return {'id': None, 'action': 'all' if self.mode == 'full' else 'quiet',
                    'modalities': list(available) if self.mode == 'full' else [], 'reason': 'configured_allocation'}
        key = torch.cat((context.double(), torch.ones(1, dtype=torch.float64)))
        options = [action for action in ACTIONS if action in available or action == 'quiet' or (action == 'all' and len(available) > 1)]
        uncertain = [action for action in options if int(self.banks[action].writes) < 3 or self.banks[action].variance(key) > 25]
        if uncertain:
            action = min(uncertain, key=lambda item: (self.visits[item], ACTIONS.index(item)))
            reason = 'explore_unlearned_consequence'
        else:
            def score(item):
                benefit, social, effort = (self.banks[item].weights @ key).clamp(-1, 1).tolist()
                return benefit + .5 * social - .25 * max(0., effort)
            action = max(options, key=lambda item: (score(item), -ACTIONS.index(item)))
            reason = 'learned_consequence_value'
        if len(self.pending) >= 16 or self.next_id >= 1000000:
            return {'id': None, 'action': 'quiet', 'modalities': [], 'reason': 'feedback_budget'}
        number = self.next_id
        self.next_id += 1
        self.visits[action] += 1
        self.pending[number] = {'action': action, 'key': key.clone(), 'issued': now, 'moment_ref': None}
        selected = list(available) if action == 'all' else ([] if action == 'quiet' else [action])
        return {'id': number, 'action': action, 'modalities': selected, 'reason': reason}

    def bind_moment(self, number, reference):
        choice = self.pending.get(number)
        if choice is None or choice['moment_ref'] is not None:
            raise ValueError('Attention acquisition is missing or already bound.')
        validate_binding(reference, choice['action'], choice['issued'])
        choice['moment_ref'] = copy.deepcopy(reference)

    def learn(self, outcome, now, language=None):
        if not isinstance(outcome, Consequence):
            raise ValueError('Native attention feedback requires an external consequence.')
        outcome.validate()
        scalar(outcome.acquired_at, 0, now)
        if language is not None:
            from .native_feedback_language import validate_source
            validate_source(language)
        choice = self.pending.get(outcome.action_id)
        if choice is None or not choice['issued'] <= outcome.acquired_at <= choice['issued'] + 60:
            return {'learned': False, 'reason': 'unknown_or_expired_attention_action'}
        if len(self.sources) >= 512:
            raise ValueError('Attention feedback budget reached; earlier learned values retained.')
        candidate = copy.deepcopy(self.banks[choice['action']])
        candidate.write(choice['key'], torch.tensor([outcome.benefit, outcome.social, outcome.effort], dtype=torch.float64), strength=10.)
        if any(not torch.isfinite(tensor).all() for tensor in candidate.state_dict().values()):
            raise ValueError('Attention feedback diverged; earlier values retained.')
        digest = hashlib.sha256(json.dumps(asdict(outcome), sort_keys=True).encode()).hexdigest()
        self.banks[choice['action']] = candidate
        self.sources.append({'id': outcome.action_id, 'action': choice['action'], 'origin': outcome.origin,
                             'acquired_at': outcome.acquired_at, 'sha256': digest,
                             'moment_ref': copy.deepcopy(choice['moment_ref']), 'language': copy.deepcopy(language)})
        del self.pending[outcome.action_id]
        return {'learned': True, 'action': choice['action'], 'autobiographical_write': False}

    def snapshot(self):
        return {'format': 3, 'mode': self.mode, 'next_id': self.next_id, 'visits': self.visits.copy(),
                'pending': copy.deepcopy(self.pending), 'sources': copy.deepcopy(self.sources),
                'banks': {action: {key: value.clone() for key, value in bank.state_dict().items()}
                          for action, bank in self.banks.items()}}


def restore(payload, now):
    fields = {'format', 'mode', 'next_id', 'visits', 'pending', 'sources', 'banks'}
    if not isinstance(payload, dict) or set(payload) != fields or type(payload['format']) is not int or payload['format'] not in (1, 2, 3) or payload['mode'] not in MODES or type(payload['next_id']) is not int or not 1 <= payload['next_id'] <= 1000000:
        raise ValueError('Invalid native attention checkpoint.')
    visits = payload['visits']
    if not isinstance(visits, dict) or set(visits) != set(ACTIONS) or any(type(value) is not int or not 0 <= value <= 1000000 for value in visits.values()) or sum(visits.values()) != payload['next_id'] - 1:
        raise ValueError('Invalid native attention decisions count.')
    pending, sources = copy.deepcopy(payload['pending']), copy.deepcopy(payload['sources'])
    if not isinstance(pending, dict) or len(pending) > 16 or not isinstance(sources, list) or len(sources) > 512:
        raise ValueError('Invalid native attention feedback budget.')
    counts = {action: 0 for action in ACTIONS}
    ids = set()
    for source in sources:
        source_fields = {'id', 'action', 'origin', 'acquired_at', 'sha256'}
        if payload['format'] in (2, 3):
            source_fields.add('moment_ref')
        if payload['format'] == 3:
            source_fields.add('language')
        if not isinstance(source, dict) or set(source) != source_fields or type(source['id']) is not int or not 1 <= source['id'] < payload['next_id'] or source['id'] in ids or source['action'] not in ACTIONS or source['origin'] not in ('person', 'environment') or not isinstance(source['sha256'], str) or len(source['sha256']) != 64 or any(c not in '0123456789abcdef' for c in source['sha256']):
            raise ValueError('Invalid native attention feedback source.')
        if payload['format'] == 1:
            source['moment_ref'] = None
        if payload['format'] in (1, 2):
            source['language'] = None
        if source['language'] is not None:
            from .native_feedback_language import validate_source
            validate_source(source['language'])
        scalar(source['acquired_at'], 0, now)
        validate_binding(source['moment_ref'], source['action'], source['acquired_at'])
        counts[source['action']] += 1
        ids.add(source['id'])
    for number, decision in pending.items():
        decision_fields = {'action', 'key', 'issued'}
        if payload['format'] in (2, 3):
            decision_fields.add('moment_ref')
        if type(number) is not int or not 1 <= number < payload['next_id'] or number in ids or not isinstance(decision, dict) or set(decision) != decision_fields or decision['action'] not in ACTIONS:
            raise ValueError('Invalid pending native attention action.')
        if payload['format'] == 1:
            decision['moment_ref'] = None
        scalar(decision['issued'], 0, now)
        validate_binding(decision['moment_ref'], decision['action'], decision['issued'])
        key = decision['key']
        if not isinstance(key, torch.Tensor) or key.device.type != 'cpu' or key.dtype != torch.float64 or key.shape != (KEY_SIZE,) or not torch.isfinite(key).all() or key[-1] != 1 or key[:-1].norm() > 1.00001:
            raise ValueError('Invalid pending native attention context.')
    if any(counts[action] + sum(item['action'] == action for item in pending.values()) > visits[action] for action in ACTIONS):
        raise ValueError('Attention feedback disagrees with its decisions.')
    result = NativeAttention()
    result.mode, result.next_id, result.visits = payload['mode'], payload['next_id'], visits.copy()
    result.pending, result.sources = copy.deepcopy(pending), copy.deepcopy(sources)
    saved = payload['banks']
    if not isinstance(saved, dict) or set(saved) != set(ACTIONS):
        raise ValueError('Invalid native attention value banks.')
    for action, bank in result.banks.items():
        state, reference = saved[action], bank.state_dict()
        if not isinstance(state, dict) or set(state) != set(reference) or any(not isinstance(value, torch.Tensor) or value.device.type != 'cpu' or value.dtype != reference[key].dtype or value.shape != reference[key].shape or not torch.isfinite(value).all() for key, value in state.items()):
            raise ValueError('Invalid native attention value tensors.')
        bank.load_state_dict(state)
        if int(bank.writes) != counts[action] or bank.weights.abs().max() > 10000 or not torch.allclose(bank.precision, bank.precision.T, atol=1e-8, rtol=0) or torch.linalg.cholesky_ex(bank.precision).info.item() != 0:
            raise ValueError('Invalid native attention values/covariance/count.')
        if not counts[action] and (bank.weights.count_nonzero() or not torch.equal(bank.precision, torch.eye(KEY_SIZE, dtype=torch.float64) * 1000)):
            raise ValueError('Untrained attention action contains learned values.')
    return result


def validate_binding(reference, action, now):
    if reference is None:
        return
    validate_reference(reference, now)
    known = {name for index, name in enumerate(MODALITIES) if reference['known'][index]}
    if action == 'quiet' or (action in MODALITIES and known != {action}) or (action == 'all' and len(known) < 2):
        raise ValueError('Attention consequence points to unselected sensory modalities.')
