"""A Portuguese naming message is bound to one recent perceived episode."""
import copy

from .concept_memory import scalar
from .concept_teaching import TeachingLane
from .native_feedback_language import message_valid
from .native_name_language import validate_plan, language_source, sha, modality_mentions
from .native_reference import validate_reference
from .native_sensor import MODALITIES
from .written_symbols import symbol

FIELDS = {'id', 'question', 'origin', 'moment_ref', 'received_at', 'focus', 'issued', 'expires', 'retry_at', 'status', 'plan', 'error', 'deferrals', 'learning'}
CURRENT_FIELDS = FIELDS | {'selected', 'reply'}


class NativeNameLane(TeachingLane):
    job_kind = 'native_name'
    stage = 'name_parse'

    def __init__(self, coordinator, native):
        super().__init__(coordinator, native)
        self.native = native

    def submit(self, message, focus=None, moment=None, origin='person', ttl=300.):
        message_valid(message)
        scalar(ttl, 5, 3600)
        if self.closed or origin not in ('person', 'environment') or len(self.jobs) >= 4 or self.next_id >= 1000000 or (focus is not None and focus not in MODALITIES):
            raise ValueError('Invalid or unavailable native naming queue.')
        if moment is not None and type(moment) is not int:
            raise ValueError('Naming requires an observed integer moment.')
        trace = (self.native.moments.get(moment) if moment is not None else
                 max(self.native.moments.traces, key=lambda item: item['id'], default=None))
        now = self.coordinator.clock
        if trace is None or now < trace['received_at'] or (moment is None and now > trace['received_at'] + 30.):
            raise ValueError('Naming requires a recently perceived retained moment.')
        reference = self.native.moments.reference(trace['id'])
        changed = any(self.native.last.get(modality + ':' + source['origin'], {}).get('sequence') != source['sequence'] for modality, source in reference['sources'].items())
        newer = max((item['acquired_at'] for item in self.native.last.values()), default=0.) > reference['acquired_at'] + .025000001
        if moment is None and (changed or newer):
            raise ValueError('The latest input did not preserve this naming target; select an observed moment explicitly.')
        if focus is not None and focus not in reference['sources']:
            raise ValueError('Naming focus was not attended in this moment.')
        if any(job['moment_ref']['id'] == reference['id'] and job['origin'] == origin and sha(job['question']) == sha(message) for job in self.jobs.values()):
            raise ValueError('This naming message is already queued for its perception.')
        number = self.next_id
        self.jobs[number] = {'id': number, 'question': message, 'origin': origin, 'moment_ref': reference, 'received_at': trace['received_at'], 'focus': focus,
            'issued': now, 'expires': now + ttl, 'retry_at': now, 'status': 'waiting', 'plan': None,
            'error': None, 'deferrals': 0, 'learning': None, 'selected': moment is not None, 'reply': None}
        self.next_id += 1
        return number

    def clarification(self, number):
        job = self.jobs[number]
        if self.closed or job['status'] not in ('failed', 'uncertain') or job['learning'] is not None or self.coordinator.clock > job['expires']:
            return None
        if self.native.moments.reference(job['moment_ref']['id']) != job['moment_ref']:
            return None
        hinted = modality_mentions(job['question'])
        focus = job['focus'] or (hinted[0] if len(hinted) == 1 else None)
        if focus is None and len(job['moment_ref']['sources']) == 1:
            focus = next(iter(job['moment_ref']['sources']))
        if focus is not None and focus not in job['moment_ref']['sources']:
            return None
        questions = {'image': 'Como você chama o que estava mostrando?',
                     'audio': 'Como você chama o som que estava ouvindo?',
                     'text': 'Qual nome você está dando ao que estava escrito?',
                     None: 'Você está dando nome à imagem, ao som ou ao texto?'}
        return {'question': questions[focus], 'focus': focus, 'moment_ref': copy.deepcopy(job['moment_ref']),
                'response_format': 'single_word', 'initiative_is_supplied': True}

    def reply(self, number, word, focus=None):
        canonical = symbol(word)
        question = self.clarification(number)
        if question is None:
            raise ValueError('Naming reply requires an unresolved retained teaching context.')
        job = self.jobs[number]
        target = question['focus'] if focus is None else focus
        if target not in job['moment_ref']['sources'] or (question['focus'] is not None and target != question['focus']):
            raise ValueError('Reply did not resolve the original naming focus.')
        now = self.coordinator.clock
        source = {'kind': 'external_word_reply', 'reply_sha256': sha(word), 'request_sha256': sha(job['question'])}
        learning = self.native.teach_retained_name(canonical, job['moment_ref'], target, job['origin'], now, source)
        if learning['learned'] is not True:
            raise ValueError('Original naming target is no longer available for teaching.')
        job.update(status='completed', error=None, learning=learning,
                   reply={'word': word, 'focus': target, 'received_at': now})
        return copy.deepcopy(learning)

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
        plan = validate_plan(result['value'], job['question'], self.coordinator.model)
        job['plan'] = copy.deepcopy(plan)
        if plan['uncertain']:
            job.update(status='uncertain', error=None)
            return 'uncertain'
        modality = plan['modality']
        if modality == 'unspecified':
            modality = job['focus']
            if modality is None and len(job['moment_ref']['sources']) == 1:
                modality = next(iter(job['moment_ref']['sources']))
        if modality is None or (job['focus'] is not None and job['focus'] != modality):
            job.update(status='failed', error='ambiguous_or_conflicting_naming_focus')
            return 'failed'
        job['learning'] = self.native.teach_retained_name(plan['name_fragment'], job['moment_ref'], modality,
                                                        job['origin'], job['issued'], language_source(plan))
        if not job['learning']['learned']:
            job.update(status='failed', error=job['learning']['reason'])
            return 'failed'
        job.update(status='completed', error=None)
        return 'learned'


def restore(payload, coordinator, native):
    if not isinstance(payload, dict) or set(payload) != {'format', 'next_id', 'jobs'} or type(payload['format']) is not int or payload['format'] not in (1, 2) or type(payload['next_id']) is not int or not 1 <= payload['next_id'] <= 1000000 or not isinstance(payload['jobs'], list) or len(payload['jobs']) > 4:
        raise ValueError('Invalid sensory naming queue checkpoint.')
    lane = NativeNameLane(coordinator, native)
    lane.next_id = payload['next_id']
    for original in payload['jobs']:
        job = copy.deepcopy(original)
        expected_fields = FIELDS if payload['format'] == 1 else CURRENT_FIELDS
        if not isinstance(job, dict) or set(job) != expected_fields or type(job['id']) is not int or not 1 <= job['id'] < lane.next_id or job['id'] in lane.jobs:
            raise ValueError('Invalid saved naming job.')
        if payload['format'] == 1:
            job.update(selected=False, reply=None)
        if type(job['selected']) is not bool:
            raise ValueError('Invalid saved naming selection mode.')
        message_valid(job['question'])
        validate_reference(job['moment_ref'], coordinator.clock, native.moments.next_id)
        scalar(job['received_at'], job['moment_ref']['acquired_at'], coordinator.clock)
        scalar(job['issued'], job['received_at'], coordinator.clock if job['selected'] else min(coordinator.clock, job['received_at'] + 30.))
        scalar(job['expires'], job['issued'] + 5, job['issued'] + 3600)
        scalar(job['retry_at'], 0, coordinator.clock + 60)
        if job['origin'] not in ('person', 'environment') or (job['focus'] is not None and job['focus'] not in job['moment_ref']['sources']) or job['status'] not in ('waiting', *lane.terminal) or type(job['deferrals']) is not int or not 0 <= job['deferrals'] <= 1000000 or (job['error'] is not None and (not isinstance(job['error'], str) or len(job['error']) > 2048)):
            raise ValueError('Invalid saved naming phase/focus.')
        current = native.moments.reference(job['moment_ref']['id'])
        if current is not None and current != job['moment_ref']:
            raise ValueError('Naming queue changed its retained perception.')
        if current is not None and native.moments.get(current['id'])['received_at'] != job['received_at']:
            raise ValueError('Naming queue changed its perception receipt time.')
        plan = job['plan']
        if plan is not None:
            validate_plan(plan, job['question'], coordinator.model)
        if job['status'] == 'completed':
            learning = job['learning']
            expected = {'learned', 'name', 'modalities', 'autobiographical_write', 'source_index', 'retained_moment'}
            if not isinstance(learning, dict) or set(learning) != expected or learning['learned'] is not True or learning['autobiographical_write'] is not False or type(learning['source_index']) is not int or not 0 <= learning['source_index'] < len(native.sources):
                raise ValueError('Completed naming job lost its learned association.')
            index = learning['source_index']
            source = native.sources[index]
            proof = next((proof for proof in native.naming_proofs if proof['source_index'] == index), None)
            reply = job['reply']
            if reply is None:
                if plan is None or plan['uncertain']:
                    raise ValueError('Completed naming job has no validated lesson or reply.')
                modality = plan['modality'] if plan['modality'] != 'unspecified' else job['focus']
                if modality is None and len(job['moment_ref']['sources']) == 1:
                    modality = next(iter(job['moment_ref']['sources']))
                canonical, issued, provenance = symbol(plan['name_fragment']), job['issued'], language_source(plan)
            else:
                if not isinstance(reply, dict) or set(reply) != {'word', 'focus', 'received_at'} or reply['focus'] not in job['moment_ref']['sources']:
                    raise ValueError('Invalid saved word clarification.')
                scalar(reply['received_at'], job['issued'], min(coordinator.clock, job['expires']))
                modality, canonical, issued = reply['focus'], symbol(reply['word']), reply['received_at']
                hinted = modality_mentions(job['question'])
                requested = job['focus'] or (hinted[0] if len(hinted) == 1 else None)
                if requested is not None and requested != modality:
                    raise ValueError('Saved word reply changed the requested modality.')
                provenance = {'kind': 'external_word_reply', 'reply_sha256': sha(reply['word']), 'request_sha256': sha(job['question'])}
            if learning['modalities'] != [modality] or (job['focus'] is not None and job['focus'] != modality) or learning['name'] != canonical or source['name'] != learning['name'] or list(source['samples']) != learning['modalities'] or source['origin'] != job['origin'] or learning['retained_moment'] != job['moment_ref']['id'] or proof != {'source_index': index, 'moment_ref': job['moment_ref'], 'issued': issued, 'received_at': job['received_at'], 'language': provenance}:
                raise ValueError('Completed naming job changed its source/perception.')
        elif job['learning'] is not None:
            if job['status'] != 'failed' or not isinstance(job['learning'], dict) or set(job['learning']) != {'learned', 'reason'} or job['learning']['learned'] is not False or not isinstance(job['learning']['reason'], str):
                raise ValueError('Uncompleted naming job asserted learning.')
        if job['status'] != 'completed' and job['reply'] is not None:
            raise ValueError('Uncompleted naming job contains a learned reply.')
        if (job['status'] == 'waiting' and plan is not None) or (job['status'] == 'uncertain' and (plan is None or not plan['uncertain'])):
            raise ValueError('Saved naming phase disagrees with its proposal.')
        lane.jobs[job['id']] = job
    return lane
