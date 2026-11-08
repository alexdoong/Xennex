"""Language queries consult learned concept weights on the single mind owner."""
from __future__ import annotations

import copy

from .concept_language import pair
from .concept_memory import scalar
from .concept_query_language import sha, validate_evidence, validate_expression, validate_plan
from .concept_teaching import TeachingLane, TERMINAL
from .language_input import references

FIELDS = {'id', 'question', 'issued', 'expires', 'retry_at', 'status', 'plan', 'error', 'deferrals',
          'evidence', 'proposal', 'revisions'}


class ConceptQueryLane(TeachingLane):
    terminal = (*TERMINAL, 'unsupported')
    job_kind = 'concept_query'
    parse_stage = 'concept_parse'
    expression_stage = 'concept_expression'

    def submit(self, question, ttl=300.):
        references(question)
        scalar(ttl, 5, 3600)
        if self.closed or len(self.jobs) >= 4 or self.next_id >= 1000000:
            raise ValueError("Conceptual query queue is closed or full.")
        number, now = self.next_id, self.coordinator.clock
        self.jobs[number] = {'id': number, 'question': question, 'issued': now, 'expires': now + ttl,
                             'retry_at': now, 'status': 'waiting', 'plan': None, 'error': None,
                             'deferrals': 0, 'evidence': None, 'proposal': None, 'revisions': 0}
        self.next_id += 1
        return number

    def current(self, evidence):
        return all(name in self.concepts.banks and int(self.concepts.banks[name].writes) == version
                   for name, version in evidence['premises'].items())

    def resolve(self, job):
        plan = job['plan']
        result = self.concepts.compose(plan['chain'], pair(plan['input_fragment']))
        job['proposal'] = None
        if not result['supported']:
            job.update(status='unsupported', evidence=None, error='concept_not_learned_or_outside_coverage')
            return False
        job['evidence'] = {'kind': 'deduced', 'chain': plan['chain'].copy(), 'input': pair(plan['input_fragment']),
                           'value': result['value'], 'premises': result['premises'],
                           'query_sha256': sha(job['question']), 'computed_at': self.coordinator.clock}
        job.update(status='ready_to_express', error=None)
        return True

    def finish(self, job, result):
        if result['status'] == 'deferred':
            stage = 'waiting' if job['status'] == 'parsing' else 'ready_to_express'
            job.update(status=stage, retry_at=self.coordinator.clock + self.coordinator.retry_seconds,
                       error='resource_admission_deferred', deferrals=job['deferrals'] + 1)
            return 'deferred'
        if result['status'] != 'ready':
            job.update(status='failed', error=str(result.get('value'))[:2048])
            return 'failed'
        if job['status'] == 'parsing':
            plan = validate_plan(result['value'], job['question'], self.coordinator.model)
            job['plan'] = copy.deepcopy(plan)
            if plan['uncertain']:
                job.update(status='uncertain', error=None)
                return 'uncertain'
            return 'resolved' if self.resolve(job) else 'unsupported'
        if not self.current(job['evidence']):
            job['revisions'] += 1
            return 'revised' if self.resolve(job) else 'unsupported'
        proposal = validate_expression(result['value'], job['evidence'], self.coordinator.model)
        job.update(status='completed', proposal=copy.deepcopy(proposal), error=None)
        return 'completed'

    def operation(self, job, parsing):
        return {'stage': self.parse_stage if parsing else self.expression_stage,
                'endpoint': self.coordinator.endpoint, 'model': self.coordinator.model,
                'question': job['question'], 'view': 'current', 'required': [],
                'evidence': [] if parsing else [copy.deepcopy(job['evidence'])]}

    def start(self):
        if self.closed or self.worker is not None:
            return []
        waiting = [job for job in self.jobs.values() if job['status'] in ('waiting', 'ready_to_express')
                   and job['retry_at'] <= self.coordinator.clock]
        if not waiting or not self.coordinator.reserve_worker(self):
            return []
        job = min(waiting, key=lambda item: item['id'])
        if job['status'] == 'ready_to_express' and not self.resolve(job):
            self.release()
            return [{self.job_kind: job['id'], 'event': 'unsupported'}]
        parsing = job['status'] == 'waiting'
        operation = self.operation(job, parsing)
        try:
            self.worker = self.coordinator.worker_factory(operation)
            self.active_id = job['id']
            job['status'] = 'parsing' if parsing else 'expressing'
            return [{self.job_kind: job['id'], 'event': 'started'}]
        except (OSError, RuntimeError, ValueError) as error:
            self.release()
            job.update(status='failed', error=str(error)[:2048])
            return [{self.job_kind: job['id'], 'event': 'failed'}]

    def take(self, number):
        job = self.jobs[number]
        if job['status'] == 'completed' and not self.current(job['evidence']):
            job['revisions'] += 1
            self.resolve(job)
        result = super().take(number)
        if result is not None:
            result.update(numeric_text_verified=result['status'] == 'completed',
                          free_text_semantics_verified=False, autobiographical_write=False)
        return result

    def snapshot(self):
        result = super().snapshot()
        for job in result['jobs']:
            if job['status'] == 'expressing':
                job['status'] = 'ready_to_express'
        return result


def restore(payload, coordinator, concepts):
    if not isinstance(payload, dict) or set(payload) != {'format', 'next_id', 'jobs'} or type(payload['format']) is not int or payload['format'] != 1:
        raise ValueError("Invalid conceptual query checkpoint.")
    if type(payload['next_id']) is not int or not 1 <= payload['next_id'] <= 1000000 or not isinstance(payload['jobs'], list) or len(payload['jobs']) > 4:
        raise ValueError("Invalid conceptual query bounds.")
    lane = ConceptQueryLane(coordinator, concepts)
    lane.next_id = payload['next_id']
    for original in payload['jobs']:
        job = copy.deepcopy(original)
        if not isinstance(job, dict) or set(job) != FIELDS or type(job['id']) is not int or not 1 <= job['id'] < lane.next_id or job['id'] in lane.jobs:
            raise ValueError("Invalid saved conceptual query.")
        references(job['question'])
        scalar(job['issued'], 0, coordinator.clock)
        scalar(job['expires'], job['issued'] + 5, job['issued'] + 3600)
        scalar(job['retry_at'], 0, coordinator.clock + 60)
        if job['status'] not in ('waiting', 'ready_to_express', *lane.terminal):
            raise ValueError("Invalid saved conceptual query phase.")
        for name in ('deferrals', 'revisions'):
            if type(job[name]) is not int or not 0 <= job[name] <= 1000000:
                raise ValueError("Invalid saved conceptual query counter.")
        if job['error'] is not None and (not isinstance(job['error'], str) or len(job['error']) > 2048):
            raise ValueError("Invalid saved conceptual query error.")
        plan, evidence, proposal = job['plan'], job['evidence'], job['proposal']
        if plan is not None:
            validate_plan(plan, job['question'], coordinator.model)
        if evidence is not None:
            validate_evidence(evidence)
            if plan is None or plan['uncertain'] or evidence['chain'] != plan['chain'] or evidence['input'] != pair(plan['input_fragment']) or evidence['query_sha256'] != sha(job['question']):
                raise ValueError("Saved conceptual evidence changed its query.")
            scalar(evidence['computed_at'], job['issued'], coordinator.clock)
            if any(name not in concepts.banks or version > int(concepts.banks[name].writes) for name, version in evidence['premises'].items()):
                raise ValueError("Saved conceptual evidence lost its learned premise.")
            if lane.current(evidence):
                expected = concepts.compose(evidence['chain'], evidence['input'])
                if not expected['supported'] or evidence['value'] != expected['value']:
                    raise ValueError("Saved deduction disagrees with its learned weights.")
        if proposal is not None:
            if evidence is None:
                raise ValueError("Saved expression has no learned deduction.")
            validate_expression(proposal, evidence, coordinator.model)
        if job['status'] == 'waiting' and any(item is not None for item in (plan, evidence, proposal)):
            raise ValueError("Unparsed query already asserts a result.")
        if job['status'] in ('ready_to_express', 'completed') and (plan is None or plan['uncertain'] or evidence is None):
            raise ValueError("Resolved query has no learned deduction.")
        if (job['status'] == 'completed') != (proposal is not None):
            raise ValueError("Saved conceptual expression phase changed.")
        if job['status'] == 'uncertain' and (plan is None or not plan['uncertain']):
            raise ValueError("Uncertain query changed its plan.")
        if job['status'] == 'unsupported' and (plan is None or plan['uncertain'] or evidence is not None):
            raise ValueError("Unsupported query asserts learned support.")
        lane.jobs[job['id']] = job
    return lane
