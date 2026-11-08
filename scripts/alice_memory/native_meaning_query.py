"""A named sensory cue locates the moment; learned relation versions answer it."""
from __future__ import annotations

import hashlib
import json
import copy

from .native_query import NativeQueryLane, resolve as sensory_resolve, signature as sensory_signature, restore as restore_queries
from .native_meaning_language import validate_plan, validate_evidence, validate_expression
from .native_reference import validate_reference
from .concept_memory import scalar
from .concept_query import FIELDS
from .written_symbols import symbol
from . import reference_language as referenced


def validate_binding(value, native, now):
    if not isinstance(value, dict) or set(value) != {'version', 'moment_ref', 'relation'} or type(value['version']) is not int or not 0 <= value['version'] < len(native.interpretations.records) or symbol(value['relation']) != value['relation']:
        raise ValueError('Invalid referenced interpretation binding.')
    validate_reference(value['moment_ref'], now, native.moments.next_id)
    source = native.interpretations.records[value['version']]
    if source['moment_ref'] != value['moment_ref'] or native.interpretations.relations[source['relation']] != value['relation'] or source['acquired_at'] > now:
        raise ValueError('Referenced query changed its learned report/episode.')
    current = native.moments.reference(source['moment'])
    if current is not None and current != value['moment_ref']:
        raise ValueError('Referenced query changed its retained episode.')
    return value


def reference_signature(native, binding):
    value = hashlib.sha256()
    memory = native.interpretations
    metadata = {'binding': binding, 'entities': memory.entities, 'relations': memory.relations,
                'records': memory.records, 'last': memory.last,
                'sensory_episode_retained': native.moments.get(binding['moment_ref']['id']) is not None}
    value.update(json.dumps(metadata, ensure_ascii=False, sort_keys=True).encode())
    for key, tensor in sorted(memory.bank.state_dict().items()):
        value.update(key.encode())
        value.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return value.hexdigest()


def resolve_reference(native, binding, plan, question, computed_at=None):
    validate_binding(binding, native, native.clock)
    views = ['initial', 'current'] if plan['view'] == 'comparison' else [plan['view']]
    evidence = {'kind': 'referenced_interpretation', 'relation': binding['relation'], 'view': plan['view'],
        'moment_ref': copy.deepcopy(binding['moment_ref']),
        'reports': {view: native.interpret(binding['moment_ref']['id'], binding['relation'], view) for view in views},
        'sensory_episode_retained': native.moments.get(binding['moment_ref']['id']) is not None,
        'signature': reference_signature(native, binding), 'query_sha256': referenced.sha(question),
        'computed_at': native.clock if computed_at is None else computed_at}
    referenced.validate_evidence(evidence)
    return evidence


def signature(native, plan, sensory):
    selected = sensory['candidate_ids'][0] if sensory['candidate_count'] == 1 else None
    if selected is not None and native.moments.get(selected) is None:
        return None
    value = hashlib.sha256(sensory_signature(native, plan, selected).encode())
    value.update(json.dumps(plan, ensure_ascii=False, sort_keys=True).encode())
    memory = native.interpretations
    value.update(json.dumps({'entities': memory.entities, 'relations': memory.relations, 'records': memory.records,
                             'last': memory.last}, ensure_ascii=False, sort_keys=True).encode())
    for key, tensor in sorted(memory.bank.state_dict().items()):
        value.update(key.encode())
        value.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return value.hexdigest()


def resolve(native, plan, question, computed_at=None, reactivate=True):
    sensory = sensory_resolve(native, plan, question, computed_at, reactivate)
    views = ['initial', 'current'] if plan['view'] == 'comparison' else [plan['view']]
    reports = {} if not sensory['supported'] else {view: native.interpret(sensory['moment_id'], plan['relation'], view) for view in views}
    evidence = {'kind': 'native_meaning', 'name': plan['name'], 'relation': plan['relation'], 'view': plan['view'],
                'sensory': sensory, 'reports': reports, 'signature': signature(native, plan, sensory),
                'query_sha256': sensory['query_sha256'], 'computed_at': sensory['computed_at']}
    validate_evidence(evidence)
    return evidence


class NativeMeaningQueryLane(NativeQueryLane):
    job_kind = 'native_meaning_query'
    parse_stage = 'meaning_parse'
    expression_stage = 'meaning_expression'
    plan_validator = staticmethod(validate_plan)
    evidence_validator = staticmethod(validate_evidence)
    expression_validator = staticmethod(validate_expression)
    evidence_resolver = staticmethod(resolve)

    def submit(self, question, ttl=300.):
        number = super().submit(question, ttl)
        self.jobs[number]['binding'] = None
        return number

    def submit_reference(self, question, binding, ttl=300.):
        validate_binding(binding, self.native, self.coordinator.clock)
        number = self.submit(question, ttl)
        self.jobs[number]['binding'] = copy.deepcopy(binding)
        return number

    def operation(self, job, parsing):
        operation = super().operation(job, parsing)
        if job.get('binding') is not None:
            operation['stage'] = 'reference_parse' if parsing else 'reference_expression'
        return operation

    def snapshot(self):
        payload = super().snapshot()
        payload['format'] = 2
        return payload

    def resolve(self, job):
        if job.get('binding') is None:
            return super().resolve(job)
        job['evidence'] = resolve_reference(self.native, job['binding'], job['plan'], job['question'])
        job.update(status='ready_to_express', proposal=None, error=None)
        return True

    def finish(self, job, result):
        if job.get('binding') is None:
            return super().finish(job, result)
        if result['status'] == 'deferred':
            job.update(status='waiting' if job['status'] == 'parsing' else 'ready_to_express',
                       retry_at=self.coordinator.clock + self.coordinator.retry_seconds,
                       error='resource_admission_deferred', deferrals=job['deferrals'] + 1)
            return 'deferred'
        if result['status'] != 'ready':
            job.update(status='failed', error=str(result.get('value'))[:2048])
            return 'failed'
        if job['status'] == 'parsing':
            job['plan'] = copy.deepcopy(referenced.validate_plan(result['value'], job['question'], self.coordinator.model))
            if job['plan']['uncertain']:
                job.update(status='uncertain', error=None)
                return 'uncertain'
            self.resolve(job)
            return 'resolved'
        if not self.current(job['evidence']):
            job['revisions'] += 1
            self.resolve(job)
            return 'revised'
        job['proposal'] = copy.deepcopy(referenced.validate_expression(result['value'], job['evidence'], self.coordinator.model))
        job.update(status='completed', error=None)
        return 'completed'

    def current(self, evidence):
        job = next((item for item in self.jobs.values() if item['evidence'] is evidence), None)
        if job is not None and job.get('binding') is not None:
            return evidence['signature'] == reference_signature(self.native, job['binding'])
        return job is not None and evidence['signature'] == signature(self.native, job['plan'], evidence['sensory'])


def restore(payload, coordinator, native):
    if not isinstance(payload, dict) or set(payload) != {'format', 'next_id', 'jobs'} or type(payload['format']) is not int or payload['format'] not in (1, 2) or type(payload['next_id']) is not int or not 1 <= payload['next_id'] <= 1000000 or not isinstance(payload['jobs'], list) or len(payload['jobs']) > 4:
        raise ValueError('Invalid meaning query checkpoint.')
    plain, bound, identifiers = [], [], set()
    for original in payload['jobs']:
        job = copy.deepcopy(original)
        expected = FIELDS if payload['format'] == 1 else FIELDS | {'binding'}
        if not isinstance(job, dict) or set(job) != expected or type(job['id']) is not int or not 1 <= job['id'] < payload['next_id'] or job['id'] in identifiers:
            raise ValueError('Invalid saved meaning query job.')
        identifiers.add(job['id'])
        if payload['format'] == 1:
            job['binding'] = None
        if job['binding'] is None:
            job.pop('binding')
            plain.append(job)
        else:
            bound.append(job)
    lane = restore_queries({'format': 1, 'next_id': payload['next_id'], 'jobs': plain}, coordinator, native, NativeMeaningQueryLane)
    for job in lane.jobs.values():
        job['binding'] = None
    for job in bound:
        from .language_input import references
        references(job['question'])
        scalar(job['issued'], 0, coordinator.clock)
        scalar(job['expires'], job['issued'] + 5, job['issued'] + 3600)
        scalar(job['retry_at'], 0, coordinator.clock + 60)
        validate_binding(job['binding'], native, job['issued'])
        if job['status'] not in ('waiting', 'ready_to_express', 'completed', 'uncertain', 'failed', 'cancelled') or any(type(job[key]) is not int or not 0 <= job[key] <= 1000000 for key in ('deferrals', 'revisions')):
            raise ValueError('Invalid saved referenced query phase/counter.')
        if job['error'] is not None and (not isinstance(job['error'], str) or len(job['error']) > 2048):
            raise ValueError('Invalid saved referenced query error.')
        plan, evidence, proposal = job['plan'], job['evidence'], job['proposal']
        if plan is not None:
            referenced.validate_plan(plan, job['question'], coordinator.model)
        if evidence is not None:
            referenced.validate_evidence(evidence)
            if plan is None or plan['uncertain'] or evidence['view'] != plan['view'] or evidence['relation'] != job['binding']['relation'] or evidence['moment_ref'] != job['binding']['moment_ref'] or evidence['query_sha256'] != referenced.sha(job['question']):
                raise ValueError('Saved referenced query changed its context/perspective.')
            scalar(evidence['computed_at'], job['issued'], coordinator.clock)
            if evidence['signature'] == reference_signature(native, job['binding']) and evidence != resolve_reference(native, job['binding'], plan, job['question'], evidence['computed_at']):
                raise ValueError('Saved referenced interpretation disagrees with learned weights.')
        if proposal is not None:
            if evidence is None:
                raise ValueError('Referenced expression lost its evidence.')
            referenced.validate_expression(proposal, evidence, coordinator.model)
        if job['status'] in ('ready_to_express', 'completed') and (plan is None or plan['uncertain'] or evidence is None):
            raise ValueError('Saved referenced query has no learned evidence.')
        if (job['status'] == 'completed') != (proposal is not None):
            raise ValueError('Saved referenced expression phase changed.')
        if job['status'] == 'waiting' and any(item is not None for item in (plan, evidence, proposal)):
            raise ValueError('Unparsed referenced query asserts a result.')
        if job['status'] == 'uncertain' and (plan is None or not plan['uncertain'] or evidence is not None):
            raise ValueError('Uncertain referenced query asserts a memory.')
        lane.jobs[job['id']] = job
    return lane
