"""Explicit relevance feedback bound to a published, actually evoked memory."""
import copy

from .dialogue_evocation_evidence import validate as validate_evocation
from .importance import Consequence


def evocation(record):
    if record['request']['action'] != 'talk' or record['status'] != 'completed' or record['published'] < record['revision']:
        return None
    association = record['result']['data']['evidence'].get('association')
    return None if association is None else association.get('evocation')


def available(owner):
    policy = owner.native.recall_preference
    if policy is None:
        return []
    result = []
    for identifier, record in owner.interactions.records.items():
        captured = evocation(record)
        if captured is None:
            continue
        choice = policy.pending.get(captured['choice'])
        if choice is not None and owner.clock <= choice['issued'] + 60:
            result.append({'about': identifier, 'age_seconds': max(0., owner.clock - choice['issued'])})
    return result


def apply(session, record):
    payload = record['request']['payload']
    parent = session.records.get(payload['about'])
    captured = None if parent is None else evocation(parent)
    if captured is None or captured['choice'] is None:
        raise ValueError('Relevance feedback requires a published conversation with an actual recollection.')
    from .dialogue_evocation import validate_binding
    validate_binding(session.owner.native, captured)
    learned = session.owner.native.learn_recall_preference(Consequence(captured['choice'], record['issued'],
        payload['relevance'], 0., 0., origin='person'))
    if not learned['learned']:
        raise ValueError('This recollection no longer has an available feedback credit.')
    return {'learning': {**learned, 'kind': 'recollection_relevance'},
            'data': {'about': payload['about'], 'evocation': copy.deepcopy(captured)}}


def validate_record(record, owner, records):
    payload, value = record['request']['payload'], record['result']
    learning, data = value['learning'], value['data']
    if not isinstance(data, dict) or set(data) != {'about', 'evocation'} or data['about'] != payload['about']:
        raise ValueError('Relevance feedback changed its original conversation.')
    captured = data['evocation']
    if not isinstance(captured, dict):
        raise ValueError('Relevance feedback lost its actual evocation.')
    from .dialogue_evocation import validate_binding
    from .native_reference import number, validate_reference
    validate_evocation(captured, None, owner.clock)
    if not captured['entries']:
        raise ValueError('Relevance feedback changed its captured evocation.')
    parent = next((item for item in records if item['request']['id'] == payload['about']), None)
    if parent is not None:
        original = evocation(parent)
        if original != captured:
            raise ValueError('Relevance feedback changed its original published evocation.')
        validate_evocation(captured, parent['request']['payload']['text'], owner.clock)
    policy = owner.native.recall_preference
    source = None if policy is None else next((item for item in policy.sources if item['id'] == captured.get('choice')), None)
    if source is None or source['origin'] != 'person' or source['benefit'] != payload['relevance'] or source['acquired_at'] != record['issued'] or source['issued'] != captured.get('computed_at'):
        raise ValueError('Relevance feedback lost its learned external consequence.')
    validate_binding(owner.native, captured)
    number(captured['computed_at'], 0, record['issued'])
    reference = validate_reference(captured['entries'][0]['moment_ref'], captured['computed_at'])
    expected = {'learned': True, 'moment': reference['id'], 'autobiographical_write': False,
                'kind': 'recollection_relevance'}
    if learning != expected or value['error'] is not None or value['question'] is not None:
        raise ValueError('Relevance feedback changed its learning receipt.')
