"""External Portuguese feedback shares the owner's one language worker slot."""
import copy

from .concept_memory import scalar
from .concept_teaching import TeachingLane
from .importance import Consequence
from .native_feedback_language import message_valid, validate_plan, language_source

FIELDS = {'id', 'question', 'action_id', 'origin', 'issued', 'expires', 'retry_at', 'status', 'plan', 'error', 'deferrals', 'learning'}


def validate_receipt(learning, source):
    if not isinstance(learning, dict) or set(learning) != {'learned', 'action', 'autobiographical_write', 'memory_impact'} or learning['learned'] is not True or learning['autobiographical_write'] is not False or source is None or learning['action'] != source['action']:
        raise ValueError('Completed feedback lost its learned source.')
    impact = learning['memory_impact']
    if not isinstance(impact, dict) or type(impact.get('learned')) is not bool:
        raise ValueError('Invalid feedback impact receipt.')
    if impact['learned']:
        if set(impact) != {'learned', 'moment', 'autobiographical_write'} or source['moment_ref'] is None or impact['moment'] != source['moment_ref']['id'] or impact['autobiographical_write'] is not False:
            raise ValueError('Feedback receipt changed its acquired event.')
    elif impact != {'learned': False, 'reason': 'no_retained_attended_moment'}:
        raise ValueError('Feedback receipt invents an impact refusal.')


class FeedbackLane(TeachingLane):
    job_kind = 'native_feedback'
    stage = 'feedback_parse'

    def __init__(self, coordinator, owner):
        super().__init__(coordinator, owner.native)
        self.owner = owner

    def submit(self, message, action_id, origin='person', ttl=300.):
        message_valid(message)
        scalar(ttl, 5, 3600)
        now = self.coordinator.clock
        choice = self.owner.native.attention.pending.get(action_id) if type(action_id) is int else None
        if self.closed or origin not in ('person', 'environment') or len(self.jobs) >= 4 or self.next_id >= 1000000 or choice is None or now > choice['issued'] + 60:
            raise ValueError('Feedback requires an external message and a current selected action.')
        if any(job['action_id'] == action_id for job in self.jobs.values()):
            raise ValueError('Feedback for this action is already queued.')
        number = self.next_id
        self.jobs[number] = {'id': number, 'question': message, 'action_id': action_id, 'origin': origin,
            'issued': now, 'expires': now + ttl, 'retry_at': now, 'status': 'waiting', 'plan': None,
            'error': None, 'deferrals': 0, 'learning': None}
        self.next_id += 1
        return number

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
        if plan['reaction'] == 'uncertain':
            job.update(status='uncertain', error=None)
            return 'uncertain'
        social = 1. if plan['reaction'] == 'encouraging' else -1.
        outcome = Consequence(job['action_id'], job['issued'], 0., social, 0., job['origin'])
        job['learning'] = self.owner.learn_native_attention(outcome, language_source(plan))
        if not job['learning']['learned']:
            job.update(status='failed', error=job['learning']['reason'])
            return 'failed'
        job.update(status='completed', error=None)
        return 'learned'


def restore(payload, coordinator, owner):
    if not isinstance(payload, dict) or set(payload) != {'format', 'next_id', 'jobs'} or type(payload['format']) is not int or payload['format'] != 1 or type(payload['next_id']) is not int or not 1 <= payload['next_id'] <= 1000000 or not isinstance(payload['jobs'], list) or len(payload['jobs']) > 4:
        raise ValueError('Invalid Portuguese feedback queue.')
    lane = FeedbackLane(coordinator, owner)
    lane.next_id = payload['next_id']
    actions = set()
    for original in payload['jobs']:
        job = copy.deepcopy(original)
        if not isinstance(job, dict) or set(job) != FIELDS or type(job['id']) is not int or not 1 <= job['id'] < lane.next_id or job['id'] in lane.jobs or type(job['action_id']) is not int or not 1 <= job['action_id'] < owner.native.attention.next_id or job['action_id'] in actions:
            raise ValueError('Invalid saved feedback job or action.')
        actions.add(job['action_id'])
        message_valid(job['question'])
        scalar(job['issued'], 0, coordinator.clock)
        scalar(job['expires'], job['issued'] + 5, job['issued'] + 3600)
        scalar(job['retry_at'], 0, coordinator.clock + 60)
        if job['origin'] not in ('person', 'environment') or job['status'] not in ('waiting', *lane.terminal) or type(job['deferrals']) is not int or not 0 <= job['deferrals'] <= 1000000 or (job['error'] is not None and (not isinstance(job['error'], str) or len(job['error']) > 2048)):
            raise ValueError('Invalid saved feedback phase/source.')
        plan = job['plan']
        if plan is not None:
            validate_plan(plan, job['question'], coordinator.model)
        if job['status'] == 'completed':
            learning = job['learning']
            source = next((item for item in owner.native.attention.sources if item['id'] == job['action_id']), None)
            validate_receipt(learning, source)
            if plan is None or plan['reaction'] == 'uncertain' or source['origin'] != job['origin'] or source['acquired_at'] != job['issued'] or source['language'] != language_source(plan):
                raise ValueError('Completed feedback lost its learned source.')
        elif job['learning'] is not None:
            if job['status'] != 'failed' or not isinstance(job['learning'], dict) or set(job['learning']) != {'learned', 'reason'} or job['learning']['learned'] is not False or not isinstance(job['learning']['reason'], str):
                raise ValueError('Uncompleted feedback asserts learning.')
        if job['status'] == 'waiting' and plan is not None:
            raise ValueError('Unparsed feedback already has a plan.')
        if job['status'] == 'uncertain' and (plan is None or plan['reaction'] != 'uncertain'):
            raise ValueError('Uncertain feedback changed its interpretation.')
        lane.jobs[job['id']] = job
    return lane
