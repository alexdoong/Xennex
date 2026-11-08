"""Learned context-dependent relevance, trained only on credited external feedback."""
import copy
import hashlib
import math

import torch

from .concept_memory import scalar
from .importance import Consequence
from .native_links import context_value
from .native_reference import validate_reference
from .online_memory import OnlineMemory

KEY_SIZE = 16 * 16 + 9
BASIS = 'dct128-to16-bilinear-priority5-known3-bias1-v1'
RULES = ('covered-linear-v1', 'variance-damped-v2')


def key(current, past, candidate):
    positions = torch.arange(128, dtype=torch.float64) + .5
    frequencies = torch.arange(1, 17, dtype=torch.float64)
    basis = torch.cos(math.pi / 128 * frequencies[:, None] * positions) * math.sqrt(2. / 16)
    left, right = basis @ context_value(current), basis @ context_value(past)
    values = [candidate[name] for name in ('score', 'freshness', 'importance', 'reactivation', 'experienced_impact')]
    return torch.cat((torch.outer(left, right).flatten(), torch.tensor([*values, *candidate['known'], 1.], dtype=torch.float64)))


def key_hash(value):
    return hashlib.sha256(value.detach().contiguous().numpy().tobytes()).hexdigest()


class RecallPreference:
    def __init__(self):
        self.read_rule = 'variance-damped-v2'
        self.bank = OnlineMemory(KEY_SIZE, 1)
        self.next_id = 1
        self.pending = {}
        self.sources = []

    def advance(self, now):
        for number in list(self.pending):
            if now > self.pending[number]['issued'] + 60:
                del self.pending[number]

    @torch.no_grad()
    def rank(self, candidates, contexts, current):
        current = context_value(current)
        result = []
        for raw in candidates:
            candidate = copy.deepcopy(raw)
            past = contexts.read(candidate['id'])
            candidate['context_supported'] = False
            if past is not None and current.norm() >= .05:
                features = key(current, past, candidate)
                variance = self.bank.variance(features)
                if int(self.bank.writes) and variance <= 25:
                    relevance = float((self.bank.weights @ features).clamp(-1, 1))
                    influence = 1. if self.read_rule == 'covered-linear-v1' else 1. / (1. + float(variance))
                    candidate.update(context_supported=True, contextual_relevance=relevance,
                                     context_variance=float(variance), context_influence=influence,
                                     priority=candidate['priority'] + .5 * relevance * influence)
            result.append(candidate)
        return sorted(result, key=lambda item: (-item['priority'], item['id']))

    @torch.no_grad()
    def credit(self, entries, contexts, current, moments, now):
        self.advance(now)
        if not entries or self.next_id >= 1000000:
            return None
        chosen = entries[0]['candidate']
        past = contexts.read(chosen['id'])
        if past is None or context_value(current).norm() < .05:
            return None
        if len(self.pending) >= 16:
            # Passive recollections need not receive a consequence. Keep bounded
            # recent credit instead of starving every subsequent interaction.
            oldest = min(self.pending, key=lambda item: (self.pending[item]['held'], self.pending[item]['issued'], item))
            del self.pending[oldest]
        number = self.next_id
        self.next_id += 1
        self.pending[number] = {'key': key(current, past, chosen), 'issued': now, 'held': False,
                                'moment_ref': moments.reference(chosen['id'])}
        return number

    def hold(self, number):
        if number in self.pending:
            self.pending[number]['held'] = True

    def learn(self, outcome, now):
        if not isinstance(outcome, Consequence):
            raise ValueError('Recall preference requires a sourced external consequence.')
        outcome.validate()
        scalar(outcome.acquired_at, 0, now)
        choice = self.pending.get(outcome.action_id)
        if choice is None or not choice['issued'] <= outcome.acquired_at <= choice['issued'] + 60:
            return {'learned': False, 'reason': 'unknown_or_expired_recollection'}
        if int(self.bank.writes) >= 1000000:
            raise ValueError('Recall preference update budget reached.')
        candidate = copy.deepcopy(self.bank)
        candidate.write(choice['key'], torch.tensor([outcome.benefit], dtype=torch.float64), strength=10.)
        source = {'id': outcome.action_id, 'moment_ref': copy.deepcopy(choice['moment_ref']),
                  'issued': choice['issued'], 'acquired_at': outcome.acquired_at, 'origin': outcome.origin,
                  'benefit': outcome.benefit, 'key_sha256': key_hash(choice['key'])}
        self.bank = candidate
        self.sources.append(source)
        self.sources[:] = self.sources[-512:]
        del self.pending[outcome.action_id]
        return {'learned': True, 'moment': source['moment_ref']['id'], 'autobiographical_write': False}

    def snapshot(self):
        return {'format': 3, 'basis': BASIS, 'read_rule': self.read_rule,
                'bank': {name: value.clone() for name, value in self.bank.state_dict().items()},
                'next_id': self.next_id, 'pending': copy.deepcopy(self.pending), 'sources': copy.deepcopy(self.sources)}


def restore(payload, moments, now):
    fields = {'format', 'basis', 'bank', 'next_id', 'pending', 'sources'}
    if isinstance(payload, dict) and payload.get('format') in (2, 3):
        fields.add('read_rule')
    if not isinstance(payload, dict) or set(payload) != fields or type(payload['format']) is not int or payload['format'] not in (1, 2, 3) or payload['basis'] != BASIS:
        raise ValueError('Invalid recall preference checkpoint.')
    result = RecallPreference()
    result.read_rule = payload.get('read_rule', 'covered-linear-v1')
    if result.read_rule not in RULES:
        raise ValueError('Invalid contextual recall read rule.')
    expected, saved = result.bank.state_dict(), payload['bank']
    if not isinstance(saved, dict) or set(saved) != set(expected) or any(not isinstance(x, torch.Tensor) or x.device.type != 'cpu' or x.dtype != expected[name].dtype or x.shape != expected[name].shape or not torch.isfinite(x).all() for name, x in saved.items()):
        raise ValueError('Invalid recall preference tensors.')
    result.bank.load_state_dict(saved)
    writes = int(result.bank.writes)
    precision = result.bank.precision
    if not 0 <= writes <= 1000000 or result.bank.weights.abs().max() > 10000 or not torch.allclose(precision, precision.T, atol=1e-8, rtol=0) or torch.linalg.cholesky_ex(precision).info.item() != 0:
        raise ValueError('Invalid recall preference learned state.')
    if writes == 0 and (result.bank.weights.count_nonzero() or not torch.equal(precision, torch.eye(KEY_SIZE, dtype=torch.float64) * 1000)):
        raise ValueError('Untrained recall preference contains learned state.')
    if type(payload['next_id']) is not int or not 1 <= payload['next_id'] <= 1000000 or not isinstance(payload['pending'], dict) or len(payload['pending']) > 16 or not isinstance(payload['sources'], list) or len(payload['sources']) != min(writes, 512):
        raise ValueError('Invalid recall preference history bounds.')
    result.next_id = payload['next_id']
    def reference(value):
        validate_reference(value, now, moments.next_id)
        retained = moments.reference(value['id'])
        if retained is not None and retained != value:
            raise ValueError('Recall feedback changed its actual sensory episode.')
    consumed = set()
    for source in payload['sources']:
        if not isinstance(source, dict) or set(source) != {'id', 'moment_ref', 'issued', 'acquired_at', 'origin', 'benefit', 'key_sha256'} or source['origin'] not in ('person', 'environment'):
            raise ValueError('Invalid recall preference source.')
        number = source['id']
        if type(number) is not int or not 1 <= number < result.next_id or number in consumed:
            raise ValueError('Reused recall preference feedback identity.')
        consumed.add(number)
        scalar(source['issued'], 0, now)
        scalar(source['acquired_at'], source['issued'], min(now, source['issued'] + 60))
        scalar(source['benefit'], -1, 1)
        reference(source['moment_ref'])
        if not isinstance(source['key_sha256'], str) or len(source['key_sha256']) != 64 or any(x not in '0123456789abcdef' for x in source['key_sha256']):
            raise ValueError('Invalid recall preference source hash.')
    for number, choice in payload['pending'].items():
        expected = {'key', 'issued', 'moment_ref'} | ({'held'} if payload['format'] == 3 else set())
        if type(number) is not int or not 1 <= number < result.next_id or number in consumed or not isinstance(choice, dict) or set(choice) != expected:
            raise ValueError('Invalid pending recall choice.')
        if payload['format'] == 3 and type(choice['held']) is not bool:
            raise ValueError('Invalid held recollection credit.')
        value = choice['key']
        if not isinstance(value, torch.Tensor) or value.device.type != 'cpu' or value.dtype != torch.float64 or value.shape != (KEY_SIZE,) or not torch.isfinite(value).all() or value.abs().max() > 128:
            raise ValueError('Invalid captured recall preference features.')
        if value[:256].norm() > 8.001 or (value[256:261].abs() > 1.00001).any() or not ((value[261:264] == 0) | (value[261:264] == 1)).all() or float(value[-1]) != 1.:
            raise ValueError('Pending recall features changed their context/priority structure.')
        scalar(choice['issued'], 0, now)
        reference(choice['moment_ref'])
    result.pending, result.sources = copy.deepcopy(payload['pending']), copy.deepcopy(payload['sources'])
    if payload['format'] < 3:
        for choice in result.pending.values():
            choice['held'] = False
    return result
