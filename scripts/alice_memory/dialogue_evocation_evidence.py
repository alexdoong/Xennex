"""Bounded evocation receipts, readable in a language worker without Torch."""
import hashlib
import re

from .concept_query_language import evidence_hash
from .native_reference import MODALITIES, number, validate_reference
from .written_symbols import symbol

FIELDS = {'kind', 'name', 'query_sha256', 'computed_at', 'candidate_count', 'entries',
          'choice', 'credit_sha256', 'basis_signature', 'signature'}


def signature(value):
    return evidence_hash({key: item for key, item in value.items() if key != 'signature'})


def validate(value, question, now):
    if not isinstance(value, dict) or set(value) != FIELDS or value['kind'] != 'dialogue_evocation':
        raise ValueError('Invalid dialogue evocation.')
    if symbol(value['name']) != value['name'] or not isinstance(value['query_sha256'], str) or re.fullmatch('[0-9a-f]{64}', value['query_sha256']) is None:
        raise ValueError('Evocation changed its received message/name.')
    if question is not None and value['query_sha256'] != hashlib.sha256(question.encode()).hexdigest():
        raise ValueError('Evocation changed its received message.')
    number(value['computed_at'], 0, now)
    if type(value['candidate_count']) is not int or not 0 <= value['candidate_count'] <= 2048 or not isinstance(value['entries'], list) or len(value['entries']) > min(2, value['candidate_count']):
        raise ValueError('Evocation exceeds its bounded sensory candidates.')
    seen = set()
    for entry in value['entries']:
        if not isinstance(entry, dict) or set(entry) != {'moment_ref', 'evoked_sha256'}:
            raise ValueError('Invalid evoked representation evidence.')
        reference = validate_reference(entry['moment_ref'], value['computed_at'])
        hashes = entry['evoked_sha256']
        if reference['id'] in seen or not isinstance(hashes, dict) or set(hashes) != {name for slot, name in enumerate(MODALITIES) if reference['known'][slot]}:
            raise ValueError('Evocation lost its distinct sensory origin.')
        seen.add(reference['id'])
        if any(not isinstance(item, str) or re.fullmatch('[0-9a-f]{64}', item) is None for item in hashes.values()):
            raise ValueError('Invalid evoked sensory hash.')
    if value['choice'] is not None and (not value['entries'] or type(value['choice']) is not int or not 1 <= value['choice'] < 1000000):
        raise ValueError('Evocation invented a feedback credit.')
    if (value['choice'] is None) != (value['credit_sha256'] is None):
        raise ValueError('Evocation lost its actual captured feedback features.')
    if value['credit_sha256'] is not None and (not isinstance(value['credit_sha256'], str) or re.fullmatch('[0-9a-f]{64}', value['credit_sha256']) is None):
        raise ValueError('Invalid evocation credit hash.')
    if not isinstance(value['basis_signature'], str) or re.fullmatch('[0-9a-f]{64}', value['basis_signature']) is None or value['signature'] != signature(value):
        raise ValueError('Evocation changed its captured evidence.')
    return value
