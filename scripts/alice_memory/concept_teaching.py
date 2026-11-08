"""Asynchronous external teaching shares the existing language worker slot."""
from __future__ import annotations

import copy
import hashlib

from .concept_language import pair, validate_plan
from .concept_memory import ConceptLesson, scalar
from .language_input import references

TERMINAL = ('completed', 'uncertain', 'failed', 'cancelled')
FIELDS = {'id', 'question', 'source', 'issued', 'expires', 'retry_at', 'status', 'plan', 'error', 'deferrals', 'learning'}


class TeachingLane:
    terminal = TERMINAL
    job_kind = 'lesson'
    stage = 'lesson'

    def __init__(self, coordinator, concepts):
        self.coordinator, self.concepts = coordinator, concepts
        self.jobs = {}
        self.next_id = 1
        self.worker = None
        self.active_id = None
        self.closed = False

    def submit(self, question, origin='person', ttl=300.):
        references(question)
        scalar(ttl, 5, 3600)
        if self.closed or origin not in ('person', 'environment'):
            raise ValueError("Only explicitly submitted external lessons may teach.")
        if len(self.jobs) >= 4 or self.next_id >= 1000000:
            raise ValueError("Teaching queue budget reached.")
        number = self.next_id
        now = self.coordinator.clock
        source = origin + '-lesson-' + hashlib.sha256(question.encode('utf-8')).hexdigest()
        self.jobs[number] = {'id': number, 'question': question, 'source': source, 'issued': now,
                             'expires': now + ttl, 'retry_at': now, 'status': 'waiting',
                             'plan': None, 'error': None, 'deferrals': 0, 'learning': None}
        self.next_id += 1
        return number

    def release(self):
        try:
            if self.worker is not None:
                self.worker.close()
        finally:
            self.worker, self.active_id = None, None
            if self.coordinator.external_worker_owner is self:
                self.coordinator.release_worker(self)

    def cancel(self, number):
        job = self.jobs[number]
        if job['status'] in self.terminal:
            return
        job.update(status='cancelled', error='cancelled')
        if self.active_id == number:
            self.worker.cancel()
            self.release()

    def finish(self, job, result):
        if result['status'] == 'deferred':
            job.update(status='waiting', retry_at=self.coordinator.clock + self.coordinator.retry_seconds,
                       error='resource_admission_deferred', deferrals=job['deferrals'] + 1)
            return 'deferred'
        if result['status'] != 'ready':
            job.update(status='failed', error=str(result.get('value'))[:2048])
            return 'failed'
        plan = validate_plan(result['value'], job['question'], self.coordinator.model)
        job['plan'] = copy.deepcopy(plan)
        if plan['uncertain']:
            job.update(status='uncertain', error=None)
            return 'uncertain'
        item = ConceptLesson(plan['concept'], tuple(pair(plan['input_fragment'])), tuple(pair(plan['output_fragment'])),
                             job['source'], self.concepts.sequence + 1, job['issued'], 'taught')
        job['learning'] = self.concepts.teach(item, self.coordinator.clock)
        job.update(status='completed', error=None)
        return 'learned'

    def poll(self):
        if self.closed:
            raise ValueError("Teaching supervisor is closed.")
        events = []
        for number, job in self.jobs.items():
            if job['status'] not in self.terminal and self.coordinator.clock > job['expires']:
                self.cancel(number)
                job.update(status='failed', error=self.job_kind + '_expired')
                events.append({self.job_kind: number, 'event': 'expired'})
        if self.worker is None:
            return events
        number = self.active_id
        job = self.jobs[number]
        try:
            result = self.worker.poll()
            if result is None:
                return events
            self.release()
            event = self.finish(job, result)
        except (OSError, RuntimeError, ValueError) as error:
            self.release()
            job.update(status='failed', error=str(error)[:2048])
            event = 'failed'
        events.append({self.job_kind: number, 'event': event})
        return events

    def operation(self, job):
        return {'stage': self.stage, 'endpoint': self.coordinator.endpoint, 'model': self.coordinator.model,
                'question': job['question'], 'view': 'current', 'required': [], 'evidence': []}

    def start(self):
        if self.closed or self.worker is not None:
            return []
        waiting = [job for job in self.jobs.values() if job['status'] == 'waiting' and job['retry_at'] <= self.coordinator.clock]
        if not waiting or not self.coordinator.reserve_worker(self):
            return []
        job = min(waiting, key=lambda item: item['id'])
        operation = self.operation(job)
        try:
            self.worker = self.coordinator.worker_factory(operation)
            self.active_id = job['id']
            job['status'] = 'parsing'
            return [{'lesson': job['id'], 'event': 'started'}]
        except (OSError, RuntimeError, ValueError) as error:
            self.release()
            job.update(status='failed', error=str(error)[:2048])
            return [{'lesson': job['id'], 'event': 'failed'}]

    def take(self, number):
        job = self.jobs[number]
        if job['status'] not in self.terminal:
            return None
        return self.jobs.pop(number)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.release()

    def snapshot(self):
        jobs = copy.deepcopy(list(self.jobs.values()))
        for job in jobs:
            if job['status'] == 'parsing':
                job['status'] = 'waiting'
        return {'format': 1, 'next_id': self.next_id, 'jobs': jobs}


def restore(payload, coordinator, concepts):
    if not isinstance(payload, dict) or set(payload) != {'format', 'next_id', 'jobs'} or type(payload['format']) is not int or payload['format'] != 1:
        raise ValueError("Invalid teaching checkpoint.")
    if type(payload['next_id']) is not int or not 1 <= payload['next_id'] <= 1000000 or not isinstance(payload['jobs'], list) or len(payload['jobs']) > 4:
        raise ValueError("Invalid teaching queue bounds.")
    result = TeachingLane(coordinator, concepts)
    result.next_id = payload['next_id']
    for original in payload['jobs']:
        job = copy.deepcopy(original)
        if not isinstance(job, dict) or set(job) != FIELDS or type(job['id']) is not int or not 1 <= job['id'] < result.next_id or job['id'] in result.jobs:
            raise ValueError("Invalid saved teaching job.")
        references(job['question'])
        source_hash = hashlib.sha256(job['question'].encode('utf-8')).hexdigest()
        if job['source'] not in ('person-lesson-' + source_hash, 'environment-lesson-' + source_hash):
            raise ValueError("Teaching source no longer matches its message.")
        scalar(job['issued'], 0, coordinator.clock)
        scalar(job['expires'], job['issued'] + 5, job['issued'] + 3600)
        scalar(job['retry_at'], 0, coordinator.clock + 60)
        if job['status'] not in ('waiting', *TERMINAL) or type(job['deferrals']) is not int or not 0 <= job['deferrals'] <= 1000000:
            raise ValueError("Invalid saved teaching phase/counter.")
        if job['error'] is not None and (not isinstance(job['error'], str) or len(job['error']) > 2048):
            raise ValueError("Invalid saved teaching error.")
        plan = job['plan']
        if plan is not None:
            validate_plan(plan, job['question'], coordinator.model)
        if job['status'] == 'completed':
            learning = job['learning']
            if plan is None or plan['uncertain'] or not isinstance(learning, dict) or set(learning) != {'learned', 'kind', 'version', 'invalidated'} or learning['learned'] is not True or learning['kind'] != 'taught':
                raise ValueError("Completed lesson has no valid learning record.")
            bank = concepts.banks.get(plan['concept'])
            if bank is None or type(learning['version']) is not int or not 1 <= learning['version'] <= int(bank.writes):
                raise ValueError("Saved lesson version is missing from the learned concept.")
            record = concepts.sources[plan['concept']][learning['version'] - 1]
            if record['source'] != job['source'] or record['acquired_at'] != job['issued']:
                raise ValueError("Saved lesson has no matching learned source.")
            if not isinstance(learning['invalidated'], list) or any(type(number) is not int or number not in concepts.hypotheses for number in learning['invalidated']):
                raise ValueError("Invalid saved lesson dependencies.")
        elif job['learning'] is not None:
            raise ValueError("Uncompleted lesson asserts a learned result.")
        if job['status'] == 'uncertain' and (plan is None or not plan['uncertain']):
            raise ValueError("Uncertain teaching phase changed its plan.")
        if job['status'] == 'waiting' and plan is not None:
            raise ValueError("Unparsed teaching job already contains a plan.")
        result.jobs[job['id']] = job
    return result
