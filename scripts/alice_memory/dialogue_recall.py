"""A learned written name evokes sensory weights; no transcript supplies the answer."""
import copy
import re
import unicodedata

from .concept_query_language import evidence_hash
from .written_symbols import symbol

FIELDS = {'kind', 'names', 'reason', 'sensory', 'binding', 'memory', 'signature'}
REASONS = ('unattended', 'no_name_cue', 'ambiguous_name_cues', 'sensory_unavailable',
           'no_report', 'ambiguous_relations', 'recalled_topic')


def name_cues(question, names):
    tokens = set(re.findall(r'\w+', unicodedata.normalize('NFKC', question).casefold()))
    return sorted(name for name in names if name in tokens)


def signature(value):
    body = {'names': value['names'], 'reason': value['reason'], 'binding': value['binding'],
        'sensory': None if value['sensory'] is None else value['sensory']['signature'],
        'memory': None if value['memory'] is None else value['memory']['signature']}
    if 'evocation' in value:
        body['evocation'] = value['evocation']['signature']
    return evidence_hash(body)


def validate(value, question, received):
    from .native_query_language import validate_evidence as validate_sensory
    from .reference_language import validate_evidence as validate_memory, sha
    if not isinstance(value, dict) or set(value) not in (FIELDS, FIELDS | {'evocation'}) or value['kind'] != 'dialogue_association' or value['reason'] not in REASONS:
        raise ValueError('Invalid dialogue association fields.')
    names = value['names']
    if not isinstance(names, list) or len(names) > 64 or any(not isinstance(name, str) for name in names) or names != sorted(set(names)) or any(symbol(name) != name for name in names):
        raise ValueError('Invalid dialogue association cues.')
    tokens = set(re.findall(r'\w+', unicodedata.normalize('NFKC', question).casefold()))
    if any(name not in tokens for name in names) or (not received['acquired'] and value['reason'] != 'unattended'):
        raise ValueError('Dialogue association is not grounded in the attended message.')
    reason = value['reason']
    if reason == 'unattended' and (received['acquired'] or names) or reason == 'no_name_cue' and names or reason == 'ambiguous_name_cues' and len(names) < 2:
        raise ValueError('Dialogue association changed its cue status.')
    sensory = value['sensory']
    if reason in ('unattended', 'no_name_cue', 'ambiguous_name_cues'):
        if sensory is not None:
            raise ValueError('Dialogue association invented an evoked episode.')
    else:
        if len(names) != 1:
            raise ValueError('Dialogue association requires one learned cue.')
        validate_sensory(sensory)
        if sensory['name'] != names[0] or sensory['query_sha256'] != sha(question) or sensory['supported'] != (reason != 'sensory_unavailable'):
            raise ValueError('Dialogue association changed its sensory evidence.')
    if reason != 'recalled_topic':
        if value['memory'] is not None or value['binding'] is not None:
            raise ValueError('Unresolved dialogue association asserts a reported fact.')
    else:
        memory, binding = value['memory'], value['binding']
        validate_memory(memory)
        if not isinstance(binding, dict) or set(binding) != {'version', 'moment_ref', 'relation'} or type(binding['version']) is not int or not 0 <= binding['version'] < 4096:
            raise ValueError('Invalid associated report binding.')
        if binding['moment_ref'] != memory['moment_ref'] or binding['relation'] != memory['relation'] or memory['moment_ref']['id'] != sensory['moment_id'] or memory['query_sha256'] != sha(question) or memory['view'] != 'comparison':
            raise ValueError('Dialogue association changed its evoked report.')
    if 'evocation' in value:
        from .dialogue_evocation_evidence import validate as validate_evocation
        validate_evocation(value['evocation'], question, 1e12)
        if not received['acquired'] or names != [value['evocation']['name']]:
            raise ValueError('Evocation requires its actually attended learned name.')
    if value['signature'] != signature(value):
        raise ValueError('Dialogue association changed its captured signature.')
    return value


def resolve(native, question, received, reactivate=False, evocation=None):
    if type(reactivate) is not bool:
        raise ValueError('Invalid dialogue recall reactivation policy.')
    value = {'kind': 'dialogue_association', 'names': [], 'reason': 'unattended',
             'sensory': None, 'binding': None, 'memory': None, 'signature': ''}
    if received['acquired']:
        value['names'] = name_cues(question, native.names)
        value['reason'] = 'no_name_cue' if not value['names'] else 'ambiguous_name_cues'
        if len(value['names']) == 1:
            recall_report(native, question, value, reactivate and not native.implicit_recall)
            if evocation is None and reactivate and native.implicit_recall:
                from .dialogue_evocation import capture
                evocation = capture(native, value['names'][0], question)
            if evocation is not None:
                value['evocation'] = copy.deepcopy(evocation)
    value['signature'] = signature(value)
    return validate(value, question, received)


def recall_report(native, question, value, reactivate):
    from .native_query import resolve as sensory_resolve
    from .native_meaning_query import resolve_reference
    plan = {'name': value['names'][0], 'modalities': [], 'window_fragment': None, 'basis': 'relative'}
    sensory = sensory_resolve(native, plan, question, reactivate=reactivate)
    value.update(sensory=sensory, reason='sensory_unavailable')
    if not sensory['supported']:
        return
    sources = [record for record in native.interpretations.records if record['moment'] == sensory['moment_id']]
    roles = {record['relation'] for record in sources}
    value['reason'] = 'no_report' if not roles else 'ambiguous_relations'
    if len(roles) != 1:
        return
    source = max(sources, key=lambda record: record['id'])
    binding = {'version': source['id'], 'moment_ref': copy.deepcopy(source['moment_ref']),
               'relation': native.interpretations.relations[source['relation']]}
    value.update(reason='recalled_topic', binding=binding,
                 memory=resolve_reference(native, binding, {'view': 'comparison'}, question))


def memory(context):
    if context['memory'] is not None:
        return context['memory']
    association = context.get('association')
    return None if association is None else association['memory']


def same_content(left, right):
    def content(value):
        if isinstance(value, dict):
            return {key: content(item) for key, item in value.items() if key not in ('signature', 'computed_at')}
        if isinstance(value, list):
            return [content(item) for item in value]
        return value
    left, right = content(left), content(right)
    if (left['sensory'] is not None and right['sensory'] is not None and
            left['sensory']['reason'] == right['sensory']['reason'] == 'ambiguous_moments'):
        # More observations of the same cue do not make a captured ambiguous
        # evocation false. A change from a unique answer to ambiguity still does.
        for value in (left, right):
            value['sensory'].pop('candidate_count', None)
            value['sensory'].pop('candidate_ids', None)
    return left == right
