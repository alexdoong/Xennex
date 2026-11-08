"""External Portuguese statements share the existing single language slot."""
from __future__ import annotations

import copy

from .concept_memory import scalar
from .concept_teaching import TeachingLane
from .language_input import references
from .native_interpretation import NativeStatement
from .native_statement_language import sha, validate_plan
from .native_name_language import modality_mentions
from .context_report_language import REPORT_KIND, validate_plan as validate_context, language_source, subject_value
from .native_reference import validate_reference
from .written_symbols import symbol

FIELDS = {'id', 'question', 'origin', 'sequence', 'issued', 'expires', 'retry_at', 'status', 'plan', 'error', 'deferrals', 'learning'}
CURRENT_FIELDS = FIELDS | {'binding'}


def validate_binding(binding, native, issued):
    if not isinstance(binding, dict) or set(binding) != {'moment_ref', 'received_at', 'selected', 'relation', 'corrects'} or type(binding['selected']) is not bool:
        raise ValueError('Invalid contextual report binding.')
    reference = validate_reference(binding['moment_ref'], issued, native.moments.next_id)
    scalar(binding['received_at'], reference['acquired_at'], issued)
    if not binding['selected'] and issued > binding['received_at'] + 30.:
        raise ValueError('Implicit contextual report is not recent.')
    current = native.moments.reference(reference['id'])
    if current is not None and current != reference:
        raise ValueError('Contextual report changed its original perception.')
    relation, corrections = binding['relation'], binding['corrects']
    if relation is not None and symbol(relation) != relation:
        raise ValueError('Contextual relation is not canonical.')
    if not isinstance(corrections, list) or len(corrections) > 32 or any(type(item) is not int or not 0 <= item < len(native.interpretations.records) for item in corrections) or corrections != sorted(set(corrections)) or (corrections and relation is None):
        raise ValueError('Invalid contextual correction versions.')
    for index in corrections:
        source = native.interpretations.records[index]
        if source['moment_ref'] != reference or native.interpretations.relations[source['relation']] != relation or source['acquired_at'] > issued:
            raise ValueError('Contextual correction refers to another event/relation.')
    return binding


def bound_plan(plan, binding):
    relation = binding['relation'] if plan['relation_fragment'] is None else symbol(plan['relation_fragment'])
    if relation is None or (binding['corrects'] and relation != binding['relation']):
        raise ValueError('Contextual report needs the original explicit relation.')
    return {'moment': binding['moment_ref']['id'], 'relation': relation,
            'subject': subject_value(plan['subject_fragment']), 'corrects': binding['corrects'].copy()}


class NativeStatementLane(TeachingLane):
    job_kind = 'native_statement'
    stage = 'interpretation_parse'

    def __init__(self, coordinator, native):
        super().__init__(coordinator, native)
        self.native = native

    def submit(self, message, origin='person', ttl=300.):
        references(message)
        scalar(ttl, 5, 3600)
        if self.closed or origin not in ('person', 'environment') or len(self.jobs) >= 4 or self.next_id >= 1000000:
            raise ValueError('Native statement queue is closed/full or source is not external.')
        sequence = max([self.native.interpretations.last.get(origin, -1)] + [job['sequence'] for job in self.jobs.values() if job['origin'] == origin]) + 1
        if sequence >= 1000000:
            raise ValueError('Native statement sequence budget reached.')
        number, now = self.next_id, self.coordinator.clock
        self.jobs[number] = {'id': number, 'question': message, 'origin': origin, 'sequence': sequence,
            'issued': now, 'expires': now + ttl, 'retry_at': now, 'status': 'waiting', 'plan': None,
            'error': None, 'deferrals': 0, 'learning': None, 'binding': None}
        self.next_id += 1
        return number

    def submit_context(self, message, moment=None, correction=None, origin='person', ttl=300.):
        now = self.coordinator.clock
        if correction is not None:
            if moment is not None:
                raise ValueError('Correction cannot select a new perception.')
            binding = copy.deepcopy(validate_binding(correction, self.native, now))
        else:
            if moment is not None and type(moment) is not int:
                raise ValueError('Contextual report needs an observed integer moment.')
            trace = self.native.moments.get(moment) if moment is not None else max(self.native.moments.traces, key=lambda item: item['id'], default=None)
            if trace is None or now < trace['received_at'] or (moment is None and now > trace['received_at'] + 30.):
                raise ValueError('Contextual report needs a recently attended perception.')
            reference = self.native.moments.reference(trace['id'])
            changed = any(self.native.last.get(modality + ':' + source['origin'], {}).get('sequence') != source['sequence'] for modality, source in reference['sources'].items())
            newer = max((item['acquired_at'] for item in self.native.last.values()), default=0.) > reference['acquired_at'] + .025000001
            if moment is None and (changed or newer):
                raise ValueError('Latest input did not preserve this implicit report target.')
            binding = {'moment_ref': reference, 'received_at': trace['received_at'], 'selected': moment is not None,
                       'relation': None, 'corrects': []}
        if any(modality not in binding['moment_ref']['sources'] for modality in modality_mentions(message)):
            raise ValueError('The declared reporting modality was not attended in this event.')
        number = self.submit(message, origin, ttl)
        self.jobs[number]['binding'] = binding
        return number

    def operation(self, job):
        operation = super().operation(job)
        if job['binding'] is not None:
            operation['stage'] = 'context_report_parse'
        return operation

    def snapshot(self):
        payload = super().snapshot()
        payload['format'] = 2
        return payload

    def finish(self, job, result):
        if result['status'] == 'deferred':
            job.update(status='waiting', retry_at=self.coordinator.clock + self.coordinator.retry_seconds,
                       error='resource_admission_deferred', deferrals=job['deferrals'] + 1)
            return 'deferred'
        if result['status'] != 'ready':
            job.update(status='failed', error=str(result.get('value'))[:2048])
            return 'failed'
        contextual = job['binding'] is not None
        validator = validate_context if contextual else validate_plan
        plan = validator(result['value'], job['question'], self.coordinator.model)
        if contextual and plan['kind'] != REPORT_KIND:
            raise ValueError('A new contextual report requires the current literal guard.')
        job['plan'] = copy.deepcopy(plan)
        if plan['uncertain']:
            job.update(status='uncertain', error=None)
            return 'uncertain'
        if contextual:
            validate_binding(job['binding'], self.native, job['issued'])
            if not job['binding']['corrects'] and self.native.moments.reference(job['binding']['moment_ref']['id']) != job['binding']['moment_ref']:
                raise ValueError('Original contextual report target is no longer retained.')
        body = bound_plan(plan, job['binding']) if contextual else plan
        lesson = NativeStatement(body['moment'], body['relation'], body['subject'], sha(job['question']),
                                 job['sequence'], job['issued'], job['origin'], tuple(body['corrects']))
        job['learning'] = self.native.teach_interpretation(lesson, language_source(plan) if contextual else None)
        if not job['learning']['learned']:
            job.update(status='failed', error=job['learning']['reason'])
            return 'failed'
        job.update(status='completed', error=None)
        return 'learned'


def restore(payload, coordinator, native):
    if not isinstance(payload, dict) or set(payload) != {'format', 'next_id', 'jobs'} or type(payload['format']) is not int or payload['format'] not in (1, 2) or type(payload['next_id']) is not int or not 1 <= payload['next_id'] <= 1000000 or not isinstance(payload['jobs'], list) or len(payload['jobs']) > 4:
        raise ValueError('Invalid native statement queue checkpoint.')
    lane = NativeStatementLane(coordinator, native)
    lane.next_id = payload['next_id']
    sequences = {}
    for original in payload['jobs']:
        job = copy.deepcopy(original)
        if not isinstance(job, dict) or set(job) != (FIELDS if payload['format'] == 1 else CURRENT_FIELDS) or type(job['id']) is not int or not 1 <= job['id'] < lane.next_id or job['id'] in lane.jobs:
            raise ValueError('Invalid saved native statement job.')
        if payload['format'] == 1:
            job['binding'] = None
        references(job['question'])
        scalar(job['issued'], 0, coordinator.clock)
        scalar(job['expires'], job['issued'] + 5, job['issued'] + 3600)
        scalar(job['retry_at'], 0, coordinator.clock + 60)
        if job['origin'] not in ('person', 'environment') or type(job['sequence']) is not int or not 0 <= job['sequence'] < 1000000 or job['sequence'] <= sequences.get(job['origin'], -1):
            raise ValueError('Invalid saved native statement source sequence.')
        sequences[job['origin']] = job['sequence']
        if job['status'] not in ('waiting', *lane.terminal) or type(job['deferrals']) is not int or not 0 <= job['deferrals'] <= 1000000:
            raise ValueError('Invalid saved native statement phase/counter.')
        if job['error'] is not None and (not isinstance(job['error'], str) or len(job['error']) > 2048):
            raise ValueError('Invalid saved native statement error.')
        plan = job['plan']
        contextual = job['binding'] is not None
        if contextual:
            validate_binding(job['binding'], native, job['issued'])
        if plan is not None:
            (validate_context if contextual else validate_plan)(plan, job['question'], coordinator.model)
        if job['status'] == 'completed':
            learning = job['learning']
            if plan is None or plan['uncertain'] or not isinstance(learning, dict) or set(learning) != {'learned', 'version', 'kind', 'corrected', 'autobiographical_write'} or learning['learned'] is not True or learning['kind'] != 'reported_interpretation' or learning['autobiographical_write'] is not False or type(learning['version']) is not int or not 0 <= learning['version'] < len(native.interpretations.records):
                raise ValueError('Completed native statement lost its learning record.')
            source = native.interpretations.records[learning['version']]
            body = bound_plan(plan, job['binding']) if contextual else plan
            if source['moment'] != body['moment'] or native.interpretations.relations[source['relation']] != body['relation'] or source['corrects'] != body['corrects'] or learning['corrected'] != body['corrects'] or source['source_sha256'] != sha(job['question']) or source['sequence'] != job['sequence'] or source['origin'] != job['origin'] or source['acquired_at'] != job['issued']:
                raise ValueError('Saved native statement changed its learned source.')
            if contextual and (source['moment_ref'] != job['binding']['moment_ref'] or source.get('language') != language_source(plan)):
                raise ValueError('Saved contextual report lost its perception/language proof.')
        elif job['learning'] is not None:
            learning = job['learning']
            if job['status'] != 'failed' or not isinstance(learning, dict) or set(learning) != {'learned', 'reason'} or learning['learned'] is not False or not isinstance(learning['reason'], str) or len(learning['reason']) > 256:
                raise ValueError('Unfinished native statement asserts learning.')
        if job['status'] == 'waiting' and plan is not None:
            raise ValueError('Unparsed native statement has a plan.')
        if job['status'] == 'uncertain' and (plan is None or not plan['uncertain']):
            raise ValueError('Uncertain native statement has no uncertainty plan.')
        lane.jobs[job['id']] = job
    return lane
