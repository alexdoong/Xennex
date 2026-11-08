"""Actual nonverbal use of named sensory memory, separate from factual claims."""
import hashlib

from .concept_query_language import evidence_hash
from .native_sensor import MODALITIES, NativeObservation
from .native_query import tensor_hash
from .dialogue_evocation_evidence import signature, validate


def name_cues(native, name):
    for modality in MODALITIES:
        meaning = native.evoke(name, modality)
        if meaning['supported']:
            return [NativeObservation(modality, meaning['latent'], native.clock, 0,
                hashlib.sha256(('dialogue-name:' + name).encode()).hexdigest(), origin='self')]
    return []


def basis_signature(native, entries, name):
    # Working state includes this very reactivation and decays on idle. Source
    # revisions, rather than its live value, determine whether to rebuild.
    digest = hashlib.sha256()
    digest.update(evidence_hash({'implicit': native.implicit_recall, 'names': native.names}).encode())
    for bank in native.writers.values():
        for name, value in sorted(bank.state_dict().items()):
            digest.update(name.encode()); digest.update(tensor_hash(value).encode())
    policy = native.recall_preference
    if policy is not None:
        digest.update(policy.read_rule.encode())
        for name, value in sorted(policy.bank.state_dict().items()):
            digest.update(name.encode()); digest.update(tensor_hash(value).encode())
    for entry in entries:
        reference = native.moments.reference(entry['moment_ref']['id'])
        digest.update(evidence_hash(reference).encode())
        if reference is not None:
            digest.update(tensor_hash(native.moments.routes[native.moments.slot(reference['id'])]).encode())
            for name, value in sorted(native.moments.bank(reference['id']).snapshot().items()):
                digest.update(name.encode())
                digest.update((tensor_hash(value) if hasattr(value, 'numpy') else str(value)).encode())
    return digest.hexdigest()


def capture(native, name, question):
    cues = name_cues(native, name)
    if not cues:
        return None
    from .native_reactivation import activate
    result = activate(native, cues, native.clock, None, describe=True)
    value = {'kind': 'dialogue_evocation', 'name': name,
             'query_sha256': hashlib.sha256(question.encode()).hexdigest(), 'computed_at': native.clock,
             'candidate_count': result['candidate_count'], 'entries': result['evocations'],
             'choice': result['recall_choice'], 'credit_sha256': None, 'basis_signature': '', 'signature': ''}
    if value['choice'] is not None:
        from .native_recall_preference import key_hash
        native.recall_preference.hold(value['choice'])
        value['credit_sha256'] = key_hash(native.recall_preference.pending[value['choice']]['key'])
    value['basis_signature'] = basis_signature(native, value['entries'], name)
    value['signature'] = signature(value)
    return validate(value, question, native.clock)


def current(native, value):
    return value['basis_signature'] == basis_signature(native, value['entries'], value['name'])


def validate_binding(native, value):
    if value['choice'] is None:
        return
    policy = native.recall_preference
    if policy is None:
        raise ValueError('Evocation credit has no native policy owner.')
    source = policy.pending.get(value['choice'])
    if source is not None:
        from .native_recall_preference import key_hash
        credit_hash = key_hash(source['key'])
    else:
        source = next((item for item in policy.sources if item['id'] == value['choice']), None)
        credit_hash = None if source is None else source['key_sha256']
    if source is not None and (source['moment_ref'] != value['entries'][0]['moment_ref'] or
            source['issued'] != value['computed_at'] or credit_hash != value['credit_sha256']):
        raise ValueError('Dialogue evocation changed its actually executed credit.')
