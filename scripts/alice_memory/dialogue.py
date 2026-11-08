"""Bounded expression lane on the same owner; the input was perceived as native text."""
import copy

from .concept_memory import scalar
from .concept_teaching import TeachingLane
from .dialogue_language import validate_context, validate_expression, validate_input
from .native_feedback_language import message_valid
from .native_meaning_query import validate_binding, reference_signature, resolve_reference
from .concept_query_language import evidence_hash

FIELDS = {'id', 'question', 'input', 'about', 'binding', 'issued', 'expires', 'retry_at', 'status', 'error',
          'deferrals', 'context', 'proposal', 'revisions', 'model'}


class DialogueLane(TeachingLane):
    job_kind = 'dialogue'
    stage = 'dialogue'

    def __init__(self, owner):
        super().__init__(owner.agent, owner.native)
        self.owner = owner
        self.model = None

    def configure(self, model):
        from .language import LocalLanguage
        if self.closed:
            raise ValueError('Dialogue supervisor is closed.')
        if model is not None:
            LocalLanguage(self.coordinator.endpoint, model)
        self.model = model

    def snapshot(self):
        result = super().snapshot()
        result.update(format=2, model=self.model)
        return result

    def submit(self, question, received, binding=None, about=None):
        message_valid(question)
        validate_input(received, question)
        from .interaction_inbox import identity
        if (about is None) != (binding is None):
            raise ValueError('Dialogue requires a matching selected topic and binding.')
        if about is not None:
            identity(about)
        if binding is not None:
            validate_binding(binding, self.owner.native, self.owner.clock)
        if self.closed or len(self.jobs) >= 4 or self.next_id >= 1000000:
            raise ValueError('Dialogue queue budget reached.')
        number, now = self.next_id, self.owner.clock
        self.jobs[number] = {'id': number, 'question': question, 'input': copy.deepcopy(received),
            'binding': copy.deepcopy(binding), 'about': about, 'issued': now, 'expires': now + 300., 'retry_at': now,
            'status': 'waiting', 'error': None, 'deferrals': 0, 'context': None, 'proposal': None, 'revisions': 0,
            'model': self.model if self.model is not None else self.coordinator.model}
        self.next_id += 1
        return number

    def signature(self, job, association=None):
        memory = None if job['binding'] is None else reference_signature(self.owner.native, job['binding'])
        body = {'input': job['input'], 'about': job['about'], 'binding': job['binding'], 'memory': memory}
        if association is not None:
            body['association'] = association['signature']
        return evidence_hash(body)

    def context(self, job):
        turns = sorted((record for record in self.owner.interactions.records.values()
            if record['request']['action'] == 'talk' and record['status'] == 'completed'
            and record['request']['payload']['about'] == job['about']), key=lambda item: item['request']['sequence'])[-2:]
        history = [{'question': turn['request']['payload']['text'][:256],
                    'reply': turn['result']['data']['proposal']['text'][:512],
                    'origin': 'self_generated_response'} for turn in turns]
        native = self.owner.native
        from .dialogue_recall import resolve
        association = None if job['binding'] is not None else resolve(native, job['question'], job['input'], reactivate=True)
        memory = None if job['binding'] is None else resolve_reference(native, job['binding'], {'view': 'comparison'}, job['question'])
        context = {'kind': 'dialogue_context_v2', 'input': copy.deepcopy(job['input']), 'about': job['about'],
            'state': {'clock': self.owner.clock, 'attention_mode': native.attention.mode,
                      'perceptions': native.observations, 'names': native.names.copy()},
            'memory': memory, 'history': history, 'association': association, 'signature': self.signature(job, association)}
        validate_context(context, job['question'])
        return context

    def operation(self, job):
        job['context'] = self.context(job)
        return {'stage': self.stage, 'endpoint': self.coordinator.endpoint, 'model': job['model'],
                'question': job['question'], 'view': 'current', 'required': [], 'evidence': [copy.deepcopy(job['context'])]}

    def current(self, evidence):
        job = next((item for item in self.jobs.values() if item['context'] is evidence), None)
        if job is None:
            return False
        from .dialogue_recall import resolve
        captured = evidence.get('association')
        evocation = None if captured is None else captured.get('evocation')
        if evocation is not None:
            from .dialogue_evocation import current
            if not current(self.owner.native, evocation):
                return False
        association = resolve(self.owner.native, job['question'], job['input'], evocation=evocation) if captured is not None else None
        if evocation is not None:
            from .dialogue_recall import same_content
            return same_content(captured, association) and evidence['signature'] == self.signature(job, captured)
        return evidence['signature'] == self.signature(job, association)

    def revise(self, job):
        job['revisions'] += 1
        self.resolve(job)

    def resolve(self, job):
        job.update(proposal=None, context=None)
        if job['revisions'] > 3:
            job.update(status='failed', error='dialogue_context_kept_changing')
        else:
            job.update(status='waiting', error=None)

    def finish(self, job, result):
        if result['status'] == 'deferred':
            job.update(status='waiting', retry_at=self.coordinator.clock + self.coordinator.retry_seconds,
                       error='resource_admission_deferred', deferrals=job['deferrals'] + 1)
            return 'deferred'
        if result['status'] != 'ready':
            job.update(status='failed', error=str(result.get('value'))[:2048])
            return 'failed'
        if not self.current(job['context']):
            self.revise(job)
            return 'revised'
        job['proposal'] = copy.deepcopy(validate_expression(result['value'], job['context'], job['question'], job['model']))
        job.update(status='completed', error=None)
        return 'completed'


def restore(payload, owner):
    if not isinstance(payload, dict) or type(payload.get('format')) is not int or payload['format'] not in (1, 2):
        raise ValueError('Invalid dialogue queue checkpoint.')
    fields = {'format', 'next_id', 'jobs'} | ({'model'} if payload['format'] == 2 else set())
    if set(payload) != fields or type(payload['next_id']) is not int or not 1 <= payload['next_id'] <= 1000000 or not isinstance(payload['jobs'], list) or len(payload['jobs']) > 4:
        raise ValueError('Invalid dialogue queue checkpoint.')
    lane = DialogueLane(owner)
    lane.configure(payload.get('model'))
    lane.next_id = payload['next_id']
    for raw in payload['jobs']:
        job = copy.deepcopy(raw)
        expected = FIELDS - ({'model'} if payload['format'] == 1 else set())
        if not isinstance(job, dict) or set(job) != expected or type(job['id']) is not int or not 1 <= job['id'] < lane.next_id or job['id'] in lane.jobs:
            raise ValueError('Invalid dialogue job identity.')
        if payload['format'] == 1:
            job['model'] = owner.agent.model
        from .language import LocalLanguage
        LocalLanguage(owner.agent.endpoint, job['model'])
        message_valid(job['question'])
        validate_input(job['input'], job['question'])
        from .interaction_inbox import identity
        if (job['about'] is None) != (job['binding'] is None):
            raise ValueError('Dialogue job changed its topic binding.')
        if job['about'] is not None:
            identity(job['about'])
        if job['binding'] is not None:
            validate_binding(job['binding'], owner.native, owner.clock)
        for field, low, high in (('issued', 0, owner.clock), ('expires', job['issued'] + 300., job['issued'] + 300.), ('retry_at', 0, owner.clock + 60)):
            scalar(job[field], low, high)
        if job['status'] not in ('waiting', 'completed', 'failed', 'cancelled') or type(job['deferrals']) is not int or job['deferrals'] < 0 or type(job['revisions']) is not int or not 0 <= job['revisions'] <= 4 or (job['error'] is not None and (not isinstance(job['error'], str) or len(job['error']) > 2048)):
            raise ValueError('Invalid dialogue job state.')
        if job['context'] is not None:
            validate_context(job['context'], job['question'])
            if job['context']['input'] != job['input']:
                raise ValueError('Dialogue context changed its received experience.')
            if job['context']['about'] != job['about'] or (job['binding'] is None) != (job['about'] is None):
                raise ValueError('Dialogue context changed its selected topic.')
            memory = job['context']['memory']
            if memory is not None and (memory['moment_ref'] != job['binding']['moment_ref'] or memory['relation'] != job['binding']['relation']):
                raise ValueError('Dialogue memory changed its bound episode/relation.')
            association = job['context'].get('association')
            captured = {'input': job['input'], 'about': job['about'], 'binding': job['binding'], 'memory': None if memory is None else memory['signature']}
            if association is not None:
                captured['association'] = association['signature']
                if association['binding'] is not None:
                    validate_binding(association['binding'], owner.native, owner.clock)
                if association.get('evocation') is not None:
                    from .dialogue_evocation import validate_binding as validate_evocation_binding
                    validate_evocation_binding(owner.native, association['evocation'])
            if job['context']['signature'] != evidence_hash(captured):
                raise ValueError('Dialogue context changed its captured signature.')
        if job['status'] == 'completed':
            validate_expression(job['proposal'], job['context'], job['question'], job['model'])
        elif job['proposal'] is not None:
            raise ValueError('Uncompleted dialogue asserts a generated response.')
        lane.jobs[job['id']] = job
    return lane
