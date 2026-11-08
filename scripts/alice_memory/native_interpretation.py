"""Versioned learned relations about sensory moments, not rewritten perception.

Strings name the vocabulary/addresses. Relation values live in RLS weights;
provenance stores no subject or example/answer table. External reports are not
promoted to directly observed facts. Explicit corrections name active versions.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass

import torch
from torch import nn
from torch.nn import functional as F

from .concept_memory import scalar
from .written_symbols import symbol
from .native_reference import MAX_MOMENT_ID, validate_reference

CAPACITY = 4096
ENTITIES = 64
RELATIONS = 32


class SlotWeights(nn.Module):
    """Exact diagonal RLS for one-hot version addresses, initially P=1000 I."""
    def __init__(self, capacity=CAPACITY):
        super().__init__()
        self.register_buffer('weights', torch.zeros(capacity, ENTITIES, dtype=torch.float64))
        self.register_buffer('precision', torch.full((capacity,), 1000., dtype=torch.float64))

    def write(self, slot, value):
        if type(slot) is not int or not 0 <= slot < len(self.weights) or not isinstance(value, torch.Tensor) or value.shape != (ENTITIES,) or value.dtype != torch.float64 or value.device.type != 'cpu' or not torch.isfinite(value).all():
            raise ValueError('Invalid native interpretation weight update.')
        variance = self.precision[slot].clone()
        gain = variance / (.1 + variance)
        row = self.weights[slot] + gain * (value - self.weights[slot])
        precision = variance - gain * variance
        if not torch.isfinite(row).all() or not torch.isfinite(precision) or precision <= 0:
            raise ValueError('Native interpretation RLS diverged.')
        self.weights[slot].copy_(row)
        self.precision[slot].copy_(precision)


@dataclass(frozen=True)
class NativeStatement:
    moment: int
    relation: str
    subject: str
    source_sha256: str
    sequence: int
    acquired_at: float
    origin: str = 'person'
    corrects: tuple[int, ...] = ()

    def validate(self):
        if type(self.moment) is not int or not 0 <= self.moment < MAX_MOMENT_ID or symbol(self.relation) != self.relation or symbol(self.subject) != self.subject:
            raise ValueError('Invalid native statement address/vocabulary.')
        if not isinstance(self.source_sha256, str) or re.fullmatch(r'[0-9a-f]{64}', self.source_sha256) is None or type(self.sequence) is not int or not 0 <= self.sequence < 1000000:
            raise ValueError('Invalid native statement provenance.')
        scalar(self.acquired_at, 0, 1e12)
        if self.origin not in ('person', 'environment', 'self') or not isinstance(self.corrects, tuple) or len(self.corrects) > 32 or self.corrects != tuple(sorted(set(self.corrects))) or any(type(item) is not int or not 0 <= item < CAPACITY for item in self.corrects):
            raise ValueError('Invalid native statement origin/correction links.')


class NativeInterpretations:
    def __init__(self, capacity=CAPACITY):
        if type(capacity) is not int or not 1 <= capacity <= CAPACITY:
            raise ValueError('Invalid native interpretation capacity.')
        self.capacity = capacity
        self.bank = SlotWeights(capacity)
        self.entities, self.relations, self.records = [], [], []
        self.last = {}

    def versions(self, moment, relation, view='current'):
        if type(moment) is not int or not 0 <= moment < MAX_MOMENT_ID or view not in ('initial', 'current'):
            raise ValueError('Invalid interpretation query address/view.')
        relation = symbol(relation)
        if relation not in self.relations:
            return []
        index = self.relations.index(relation)
        records = [item for item in self.records if item['moment'] == moment and item['relation'] == index]
        if view == 'initial':
            return [records[0]['id']] if records else []
        superseded = {number for item in records for number in item['corrects']}
        return [item['id'] for item in records if item['id'] not in superseded]

    def teach(self, statement, moments, now, language=None):
        if not isinstance(statement, NativeStatement):
            raise ValueError('Native interpretation requires a typed external statement.')
        statement.validate()
        if language is not None:
            from .context_report_language import validate_source
            validate_source(language)
            if language['message_sha256'] != statement.source_sha256:
                raise ValueError('Contextual language source changed its report.')
        if statement.origin == 'self':
            return {'learned': False, 'reason': 'self_statement_is_not_external_evidence'}
        reference = moments.reference(statement.moment)
        if reference is None:
            reference = next((item['moment_ref'] for item in self.records if item['moment'] == statement.moment), None)
        if reference is None:
            raise ValueError('Native statement refers to an unobserved or forgotten moment.')
        scalar(statement.acquired_at, reference['acquired_at'], now)
        if statement.sequence <= self.last.get(statement.origin, -1):
            return {'learned': False, 'reason': 'stale_statement'}
        if self.records and statement.acquired_at < self.records[-1]['acquired_at']:
            raise ValueError('Native statements must arrive in temporal order.')
        if len(self.records) >= self.capacity or (statement.subject not in self.entities and len(self.entities) >= ENTITIES) or (statement.relation not in self.relations and len(self.relations) >= RELATIONS):
            raise ValueError('Native interpretation budget reached; previous versions retained.')
        active = self.versions(statement.moment, statement.relation)
        if any(number not in active for number in statement.corrects):
            raise ValueError('Correction refers to a stale/different interpretation version.')
        if len(active) - len(statement.corrects) + 1 > 32:
            raise ValueError('Native interpretation conflict set is full.')
        entities = self.entities.copy()
        relations = self.relations.copy()
        if statement.subject not in entities:
            entities.append(statement.subject)
        if statement.relation not in relations:
            relations.append(statement.relation)
        slot = len(self.records)
        target = F.one_hot(torch.tensor(entities.index(statement.subject)), ENTITIES).double()
        record = {'id': slot, 'moment': statement.moment, 'relation': relations.index(statement.relation),
                  'kind': 'external_statement', 'source_sha256': statement.source_sha256,
                  'origin': statement.origin, 'sequence': statement.sequence, 'acquired_at': statement.acquired_at,
                  'corrects': list(statement.corrects), 'moment_ref': copy.deepcopy(reference)}
        if language is not None:
            record['language'] = copy.deepcopy(language)
        self.bank.write(slot, target)
        self.entities, self.relations = entities, relations
        self.records.append(record)
        self.last[statement.origin] = statement.sequence
        return {'learned': True, 'version': slot, 'kind': 'reported_interpretation',
                'corrected': list(statement.corrects), 'autobiographical_write': False}

    def query(self, moment, relation, view='current'):
        versions = self.versions(moment, relation, view)
        result = {'supported': False, 'kind': 'reported_interpretation', 'moment': moment,
                  'relation': symbol(relation), 'view': view, 'versions': versions,
                  'subject': None, 'sources': [], 'confidence_is_calibrated': False,
                  'directly_observed': False, 'autobiographical_write': False}
        if not versions:
            return {**result, 'reason': 'unlearned_interpretation'}
        subjects = []
        for number in versions:
            scores = self.bank.weights[number, :len(self.entities)]
            order = scores.argsort(descending=True)
            first = int(order[0])
            score = float(scores[first])
            margin = score - (float(scores[int(order[1])]) if len(order) > 1 else 0.)
            if not torch.isfinite(scores).all() or score < .7 or margin < .2 or self.bank.precision[number] > 25:
                return {**result, 'reason': 'outside_learned_coverage'}
            subjects.append(self.entities[first])
        sources = [copy.deepcopy(self.records[number]) for number in versions]
        if len(set(subjects)) > 1:
            return {**result, 'reason': 'conflicting_statements', 'sources': sources}
        return {**result, 'supported': True, 'reason': 'supported', 'subject': subjects[0], 'sources': sources}

    def snapshot(self):
        return {'format': 3, 'capacity': self.capacity, 'entities': self.entities.copy(),
                'relations': self.relations.copy(), 'records': copy.deepcopy(self.records),
                'last': self.last.copy(), 'bank': {name: value.clone() for name, value in self.bank.state_dict().items()}}


def restore(payload, moments, now):
    fields = {'format', 'capacity', 'entities', 'relations', 'records', 'last', 'bank'}
    if not isinstance(payload, dict) or set(payload) != fields or type(payload['format']) is not int or payload['format'] not in (1, 2, 3):
        raise ValueError('Invalid native interpretation checkpoint.')
    result = NativeInterpretations(payload['capacity'])
    for name, limit in (('entities', ENTITIES), ('relations', RELATIONS)):
        values = payload[name]
        if not isinstance(values, list) or len(values) > limit or len(values) != len(set(values)) or any(symbol(item) != item for item in values):
            raise ValueError('Invalid native interpretation vocabulary.')
        setattr(result, name, values.copy())
    records = payload['records']
    if not isinstance(records, list) or len(records) > result.capacity:
        raise ValueError('Invalid native interpretation version count.')
    seen_relations, last, previous_time = set(), {}, 0.
    for index, record in enumerate(records):
        record = copy.deepcopy(record)
        expected = {'id', 'moment', 'relation', 'kind', 'source_sha256', 'origin', 'sequence', 'acquired_at', 'corrects'}
        if payload['format'] >= 2:
            expected.add('moment_ref')
        if payload['format'] == 3 and isinstance(record, dict) and 'language' in record:
            expected.add('language')
        if not isinstance(record, dict) or set(record) != expected or type(record['id']) is not int or record['id'] != index or record['kind'] != 'external_statement' or type(record['relation']) is not int or not 0 <= record['relation'] < len(result.relations) or type(record['moment']) is not int or not 0 <= record['moment'] < moments.next_id:
            raise ValueError('Invalid native interpretation provenance/address.')
        if not isinstance(record['corrects'], list):
            raise ValueError('Invalid native correction link fields.')
        statement = NativeStatement(record['moment'], result.relations[record['relation']], 'placeholder',
                                    record['source_sha256'], record['sequence'], record['acquired_at'], record['origin'], tuple(record['corrects']))
        statement.validate()
        if 'language' in record:
            from .context_report_language import validate_source
            validate_source(record['language'])
            if record['language']['message_sha256'] != record['source_sha256']:
                raise ValueError('Saved contextual language changed its report hash.')
        if record['origin'] == 'self' or record['sequence'] <= last.get(record['origin'], -1):
            raise ValueError('Invalid native interpretation source ordering.')
        current = moments.reference(record['moment'])
        reference = record.get('moment_ref', current)
        validate_reference(reference, now, moments.next_id)
        if reference['id'] != record['moment'] or (current is not None and current != reference) or any(item['moment'] == record['moment'] and item['moment_ref'] != reference for item in result.records):
            raise ValueError('Native report changed its original event reference.')
        record['moment_ref'] = copy.deepcopy(reference)
        scalar(record['acquired_at'], max(previous_time, reference['acquired_at']), now)
        active = result.versions(record['moment'], result.relations[record['relation']])
        if any(number not in active for number in record['corrects']) or len(active) - len(record['corrects']) + 1 > 32:
            raise ValueError('Invalid native interpretation correction lineage.')
        result.records.append(copy.deepcopy(record))
        seen_relations.add(record['relation'])
        last[record['origin']] = record['sequence']
        previous_time = record['acquired_at']
    if seen_relations != set(range(len(result.relations))) or payload['last'] != last or (not records and result.entities) or (records and not result.entities):
        raise ValueError('Native interpretation registry lost its sources.')
    saved, expected = payload['bank'], result.bank.state_dict()
    if not isinstance(saved, dict) or set(saved) != set(expected):
        raise ValueError('Invalid native interpretation weight fields.')
    for name, tensor in saved.items():
        if not isinstance(tensor, torch.Tensor) or tensor.device.type != 'cpu' or tensor.dtype != expected[name].dtype or tensor.shape != expected[name].shape or not torch.isfinite(tensor).all():
            raise ValueError('Invalid native interpretation weights.')
    count = len(records)
    weights, precision = saved['weights'], saved['precision']
    if weights.abs().max() > 1.1 or weights[count:].count_nonzero() or weights[:, len(result.entities):].count_nonzero() or not torch.allclose(precision[:count], torch.full_like(precision[:count], 1000. - 1000. * (1000. / 1000.1)), atol=1e-8, rtol=0) or not torch.equal(precision[count:], torch.full_like(precision[count:], 1000.)):
        raise ValueError('Native interpretation weights contain unused/divergent state.')
    result.bank.load_state_dict(saved)
    result.last = last
    return result
