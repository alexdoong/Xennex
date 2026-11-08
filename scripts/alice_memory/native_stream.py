"""Persisted native frame queue on the existing mind owner and inference slot."""
from __future__ import annotations

import copy
import re

from .concept_memory import scalar
from .grounded_mind import WrittenName
from .native_inbox import FRAME, manifest_fields, validate_frame_details
from .native_regions import DETECTION_STATUSES, MAX_REGIONS, validate_regions
from .native_sensor import NativeObservation
from .written_symbols import symbol

TERMINAL = ('completed', 'ignored', 'failed')
LEGACY_FIELDS = {'id', 'frame', 'manifest', 'source_sequence', 'issued', 'received_wall', 'acquired_at', 'expires',
          'retry_at', 'status', 'deferrals', 'result', 'error'}
FIELDS = LEGACY_FIELDS | {'moment_ref'}


class NativeStream:
    def __init__(self, owner):
        self.owner = owner
        self.stream_id = None
        self.last_source_sequence = -1
        self.next_id = 1 + max([-1, *owner.native.label_sequence.values(),
                                *(item['sequence'] for item in owner.native.last.values())])
        self.jobs = {}
        self.deliveries = []
        self.factory = self.inbox = None
        self.feedback = None
        self.worker = None
        self.active = []
        self.closed = False

    def configure(self, inbox, factory, feedback=None):
        if feedback is not None and not callable(feedback):
            raise ValueError('Native feedback observer must be a local callable.')
        if self.worker is not None or self.closed or (self.stream_id is not None and inbox.stream_id != self.stream_id):
            raise ValueError("Native stream configuration conflicts with its source or worker.")
        self.stream_id, self.inbox, self.factory = inbox.stream_id, inbox, factory
        self.feedback = feedback

    def ingest(self, frame, manifest, wall_now):
        if self.closed or self.inbox is None or self.factory is None:
            raise ValueError("Native stream is not configured.")
        self.next_id = max(self.next_id, 1 + max([-1, *self.owner.native.label_sequence.values(),
                                                *(item['sequence'] for item in self.owner.native.last.values())]))
        if len(self.jobs) >= 4 or self.next_id > 1000000:
            return False
        if manifest['stream_id'] != self.stream_id:
            raise ValueError("Native frame belongs to a different source stream.")
        if manifest['sequence'] <= self.last_source_sequence:
            return False
        age = wall_now - manifest['captured_wall']
        scalar(age, 0, 3600.)
        number, now = self.next_id, self.owner.clock
        acquired = max(0., now - age)
        self.jobs[number] = {'id': number, 'frame': frame, 'manifest': copy.deepcopy(manifest),
                             'source_sequence': manifest['sequence'], 'issued': now, 'received_wall': wall_now, 'acquired_at': acquired,
                             'expires': None, 'retry_at': now, 'status': 'waiting',
                             'deferrals': 0, 'result': None, 'error': None, 'moment_ref': None}
        self.last_source_sequence = manifest['sequence']
        self.next_id += 1
        return True

    def reserve(self):
        return True if self.owner.teaching is None else self.owner.agent.reserve_worker(self)

    def release(self):
        try:
            if self.worker is not None:
                self.worker.close()
        finally:
            self.worker, self.active = None, []
            if self.owner.teaching is not None and self.owner.agent.external_worker_owner is self:
                self.owner.agent.release_worker(self)

    def start(self):
        if self.closed or self.factory is None or self.worker is not None:
            return []
        waiting = [job for job in self.jobs.values() if job['status'] == 'waiting' and job['retry_at'] <= self.owner.clock]
        if not waiting or not self.reserve():
            return []
        selected = sorted(waiting, key=lambda item: item['id'])
        try:
            self.worker = self.factory(copy.deepcopy(selected))
            self.active = [job['id'] for job in selected]
            for job in selected:
                job['status'] = 'encoding'
            return [{'frame': number, 'event': 'started'} for number in self.active]
        except (OSError, RuntimeError, ValueError) as error:
            self.release()
            for job in selected:
                job.update(status='failed', error=str(error)[:1024])
            return [{'frame': job['id'], 'event': 'failed'} for job in selected]

    def poll(self):
        if self.factory is None:
            return []
        events = []
        # A captured frame remains real input after resource waits or shutdown.
        # The worker has a finite deadline; the queued perception does not expire.
        if self.worker is None:
            return events
        active = self.active.copy()
        try:
            result = self.worker.poll()
            if result is None:
                return events
            self.release()
            if result['status'] == 'deferred' or result.get('error') == 'resource_limit_crossed':
                for number in active:
                    job = self.jobs[number]
                    if job['status'] not in TERMINAL:
                        job.update(status='waiting', retry_at=self.owner.clock + 5., deferrals=job['deferrals'] + 1,
                                   error=(result.get('error') or 'resource_admission_deferred')[:1024])
                return events + [{'frame': number, 'event': 'deferred'} for number in active]
            if result['status'] != 'ready':
                raise ValueError(result.get('error') or 'native_worker_failed')
            packets = result['packets']
            regions = result.get('regions', {})
            statuses = result.get('region_status', {})
            acoustic = result.get('acoustic', {})
            spoken = {number for number in active if self.jobs[number]['manifest'].get('word_audio')}
            if not isinstance(acoustic, dict) or set(acoustic) != spoken or any(type(number) is not int for number in acoustic):
                raise ValueError('Native frame receipt changed its acoustic word sources.')
            requested = {number for number in active if 'image_regions' in self.jobs[number]['manifest']}
            if (not isinstance(statuses, dict) or not set(statuses) <= set(active) - requested
                    or any(type(number) is not int or status not in DETECTION_STATUSES for number, status in statuses.items())):
                raise ValueError('Native frame receipt changed its region detection outcomes.')
            expected_regions = requested | {number for number, status in statuses.items() if status == 'detected'}
            if not isinstance(regions, dict) or set(regions) != expected_regions or any(type(number) is not int for number in regions):
                raise ValueError('Native frame receipt changed its visual regions.')
            for number in active:
                job = self.jobs[number]
                if job['status'] in TERMINAL:
                    continue
                batch = [packet for packet in packets if packet.sequence == number]
                expected = job['manifest']['files']
                if len(batch) != len(expected) or {packet.modality for packet in batch} != {item['modality'] for item in expected}:
                    raise ValueError("Native frame receipt changed its modalities.")
                for packet in batch:
                    packet.validate()
                    item = next(item for item in expected if item['modality'] == packet.modality)
                    if packet.sample_sha256 != item['sha256'] or packet.acquired_at != job['acquired_at'] or packet.origin != job['manifest']['origin']:
                        raise ValueError("Native frame receipt changed its source.")
                context = {'stream_id': self.stream_id, 'source_sequence': job['source_sequence'],
                           'captured_wall': job['manifest']['captured_wall'], 'received_wall': job['received_wall']}
                visual = regions.get(number)
                if number in expected_regions or number in statuses:
                    image = next((packet for packet in batch if packet.modality == 'image'), None)
                    if image is None:
                        raise ValueError('Visual detection requires an image in its own frame.')
                    if number in expected_regions:
                        validate_regions(visual, image.sample_sha256, job['manifest'].get('image_regions'))
                encoded = self.owner.observe_native(batch, context, regions=visual)
                job['moment_ref'] = self.owner.native.moments.reference(encoded.get('moment'))
                modalities = encoded.get('attention', {}).get('modalities', [])
                recognized = [{'modality': packet.modality, **self.owner.native.recognize(packet)}
                              for packet in batch if packet.modality in modalities]
                learning = None
                if encoded['encoded'] and job['manifest']['name'] is not None and number not in spoken:
                    lesson = WrittenName(job['manifest']['name'], job['acquired_at'], number, job['manifest']['origin'])
                    try:
                        learning = self.owner.native.teach(lesson, self.owner.clock)
                    except ValueError as error:
                        learning = {'learned': False, 'reason': 'native_association_error'}
                        events.append({'frame': number, 'event': 'native_teaching_failed', 'reason': str(error)[:1024]})
                pronunciation = self.pronounce(job, modalities, acoustic[number]) if number in spoken else None
                job.update(status='completed' if encoded['encoded'] else 'ignored', error=None,
                           result={'encoded': encoded['encoded'], 'learning': learning, 'recognized': recognized,
                                   'received': encoded.get('received', 0), 'attention': encoded.get('attention')})
                association = encoded.get('audio_association')
                if association is not None and association['supported']:
                    job['result']['audio_association'] = association
                if pronunciation is not None:
                    job['result']['pronunciation'] = pronunciation
                if number in expected_regions:
                    job['result']['region_count'] = len(visual['boxes']) if 'image' in modalities else 0
                if number in statuses:
                    job['result']['region_status'] = statuses[number]
                    job['result'].setdefault('region_count', 0)
                if self.feedback is not None and encoded.get('attention', {}).get('id') is not None:
                    try:
                        observation = {key: copy.deepcopy(job['result'][key]) for key in ('attention', 'received', 'encoded')}
                        outcome = self.feedback(observation, self.owner.clock)
                        if outcome is not None:
                            from .importance import Consequence
                            if not isinstance(outcome, Consequence) or outcome.action_id != encoded['attention']['id']:
                                raise ValueError('Feedback changed its attention action reference.')
                            learning = self.owner.learn_native_attention(outcome)
                            events.append({'frame': number, 'event': 'attention_feedback', **learning})
                    except (OSError, RuntimeError, ValueError, TypeError) as error:
                        events.append({'frame': number, 'event': 'attention_feedback_failed', 'reason': str(error)[:1024]})
                events.append({'frame': number, 'event': job['status']})
        except (OSError, RuntimeError, ValueError) as error:
            self.release()
            for number in active:
                job = self.jobs[number]
                if job['status'] not in TERMINAL:
                    job.update(status='failed', error=str(error)[:1024])
            events.extend({'frame': number, 'event': 'failed'} for number in active)
        return events

    def pronounce(self, job, modalities, pattern):
        if 'audio' not in modalities:
            return {'status': 'unattended'}
        if pattern is None:
            return {'status': 'unusable_audio'}
        from .native_pronunciation import recognize, teach
        memory = self.owner.native.moments
        moment, name = job['moment_ref']['id'], job['manifest']['name']
        return recognize(memory, moment, pattern) if name is None else teach(memory, moment, name, pattern)

    def committed(self, numbers, record, previous=None):
        if previous is None or previous['file'] == record['file']:
            return
        proof = {**record, 'previous_file': previous['file'], 'previous_sha256': previous['sha256']}
        for number in numbers:
            job = self.jobs.get(number)
            if job is None or job['status'] not in TERMINAL:
                continue
            self.inbox.acknowledge(job, proof)
            self.deliveries.append(copy.deepcopy(job))
            self.deliveries[:] = self.deliveries[-16:]
            del self.jobs[number]

    def close(self):
        self.closed = True
        for number in self.active:
            if self.jobs[number]['status'] == 'encoding':
                self.jobs[number]['status'] = 'waiting'
        self.release()

    def snapshot(self):
        self.next_id = max(self.next_id, 1 + max([-1, *self.owner.native.label_sequence.values(),
                                                *(item['sequence'] for item in self.owner.native.last.values())]))
        jobs = copy.deepcopy(list(self.jobs.values()))
        for job in jobs:
            if job['status'] == 'encoding':
                job['status'] = 'waiting'
        return {'format': 2, 'stream_id': self.stream_id, 'last_source_sequence': self.last_source_sequence,
                'next_id': self.next_id, 'jobs': jobs, 'deliveries': copy.deepcopy(self.deliveries)}


def selected_modalities(content, available, owner, job):
    legacy = {'encoded', 'learning', 'recognized'}
    current = legacy | {'received', 'attention'}
    boxes = job['manifest'].get('image_regions')
    expected = (legacy, current) if boxes is None else (current | {'region_count'},)
    automatic = isinstance(content, dict) and 'region_status' in content
    if automatic:
        if boxes is not None or 'image' not in available or content['region_status'] not in DETECTION_STATUSES:
            raise ValueError('Saved visual detection changed its source or outcome.')
        expected = (current | {'region_count', 'region_status'},)
    sound_association = isinstance(content, dict) and 'audio_association' in content
    if sound_association:
        expected = tuple(fields | {'audio_association'} for fields in expected if fields != legacy)
    spoken = job['manifest'].get('word_audio')
    if spoken:
        expected = tuple(fields | {'pronunciation'} for fields in expected if fields != legacy)
    if not isinstance(content, dict) or set(content) not in expected or type(content['encoded']) is not int or not 0 <= content['encoded'] <= len(available) or not isinstance(content['recognized'], list):
        raise ValueError('Saved native completion has no bounded result.')
    reference = job.get('moment_ref')
    if reference is not None:
        validate_job_reference(reference, owner, job)
    if set(content) == legacy:
        selected = available
    else:
        received, decision = content['received'], content['attention']
        if type(received) is not int or not 0 <= content['encoded'] <= received <= len(available):
            raise ValueError('Saved native receipt changed available/attended counts.')
        if decision is None:
            if received or content['encoded']:
                raise ValueError('Native receipt lost its attention allocation.')
            selected = []
        else:
            if not isinstance(decision, dict) or set(decision) != {'id', 'action', 'modalities', 'reason'} or decision['action'] not in ('image', 'audio', 'text', 'all', 'quiet') or decision['reason'] not in ('configured_allocation', 'feedback_budget', 'explore_unlearned_consequence', 'learned_consequence_value'):
                raise ValueError('Invalid saved attention allocation.')
            if decision['id'] is not None and (type(decision['id']) is not int or not 1 <= decision['id'] < owner.native.attention.next_id):
                raise ValueError('Saved attention decision changed its identity.')
            selected = decision['modalities']
            if not isinstance(selected, list) or len(set(selected)) != len(selected) or any(name not in available for name in selected) or len(selected) != content['encoded']:
                raise ValueError('Saved native acquisition changed its selected modalities.')
            expected = [] if decision['action'] == 'quiet' else ([decision['action']] if decision['action'] != 'all' else selected)
            if selected != expected or (decision['action'] == 'all' and len(selected) != received):
                raise ValueError('Saved native action disagrees with acquisition.')
        traces = [trace for trace in owner.native.moments.traces if trace['source_context'] is not None
                  and trace['source_context']['stream_id'] == job['manifest']['stream_id']
                  and trace['source_context']['source_sequence'] == job['source_sequence']]
        if bool(selected) != bool(reference or traces) or len(traces) > 1:
            raise ValueError('Saved attended acquisition lost its sensory moment.')
        if reference or traces:
            trace = reference or traces[0]
            if set(trace['sources']) != set(selected) or any(trace['sources'][item['modality']] != {'origin': job['manifest']['origin'], 'sequence': job['id'], 'sha256': item['sha256']} for item in job['manifest']['files'] if item['modality'] in selected):
                raise ValueError('Saved attention acquisition changed its neural sources.')
    if len(content['recognized']) != len(selected) or {item.get('modality') for item in content['recognized'] if isinstance(item, dict)} != set(selected):
        raise ValueError('Saved recognition includes unattended or duplicate modalities.')
    if sound_association:
        from .native_audio_naming import validate_association
        if selected != ['audio'] or reference is None:
            raise ValueError('Saved sound association lacks its attended audio-only cue.')
        validate_association(content['audio_association'], owner.native, reference)
    if spoken:
        from .native_pronunciation import validate_result
        if content['learning'] is not None:
            raise ValueError('A pronunciation lesson cannot teach an ordinary sound name.')
        validate_result(content['pronunciation'], owner.native.moments, reference, selected == ['audio'],
                        job['manifest']['name'])
    if boxes is not None or automatic:
        saved = content['region_count']
        recorded = 'image' in selected and (boxes is not None or content['region_status'] == 'detected')
        lower = len(boxes) if recorded and boxes is not None else int(recorded)
        upper = MAX_REGIONS if recorded and automatic else lower
        if type(saved) is not int or not lower <= saved <= upper:
            raise ValueError('Saved visual detail count disagrees with attended regions.')
        moments = owner.native.moments
        if reference is not None and moments.get(reference['id']) is not None:
            record = moments.regions.get(reference['id'])
            if (saved and (record is None or len(record['boxes']) != saved or (boxes is not None and record['boxes'] != boxes))) or (not saved and record is not None):
                raise ValueError('Saved visual regions disagree with their retained moment.')
    return selected


def validate_job_reference(reference, owner, job):
    from .native_reference import validate_reference
    validate_reference(reference, owner.clock, owner.native.moments.next_id)
    if reference['acquired_at'] != job['acquired_at'] or reference['source_context'] != {
        'stream_id': job['manifest']['stream_id'], 'source_sequence': job['source_sequence'],
        'captured_wall': job['manifest']['captured_wall'], 'received_wall': job['received_wall']}:
        raise ValueError('Saved native receipt changed its original acquisition reference.')
    current_ref = owner.native.moments.reference(reference['id'])
    if current_ref is not None and current_ref != reference:
        raise ValueError('Saved native receipt points to another sensory event.')
    files = {item['modality']: item for item in job['manifest']['files']}
    if any(name not in files or source != {'origin': job['manifest']['origin'], 'sequence': job['id'],
            'sha256': files[name]['sha256']} for name, source in reference['sources'].items()):
        raise ValueError('Saved native receipt changed its original neural sources.')


def restore(payload, owner):
    expected = {'format', 'stream_id', 'last_source_sequence', 'next_id', 'jobs', 'deliveries'}
    if not isinstance(payload, dict) or set(payload) != expected or type(payload['format']) is not int or payload['format'] not in (1, 2):
        raise ValueError("Invalid native stream checkpoint.")
    stream_id = payload['stream_id']
    if stream_id is not None and (not isinstance(stream_id, str) or re.fullmatch(r'[0-9a-f]{32}', stream_id) is None):
        raise ValueError("Invalid native stream identity.")
    if type(payload['last_source_sequence']) is not int or not -1 <= payload['last_source_sequence'] < 1000000 or type(payload['next_id']) is not int or not 0 <= payload['next_id'] <= 1000001:
        raise ValueError("Invalid native stream counters.")
    if not isinstance(payload['jobs'], list) or len(payload['jobs']) > 4 or not isinstance(payload['deliveries'], list) or len(payload['deliveries']) > 16:
        raise ValueError("Invalid native stream queue bounds.")
    result = NativeStream(owner)
    if payload['next_id'] < result.next_id:
        raise ValueError("Native stream counter would replay an older sensory sequence.")
    result.stream_id, result.last_source_sequence, result.next_id = stream_id, payload['last_source_sequence'], payload['next_id']
    ids, sequences = [], []
    for original in (*payload['deliveries'], *payload['jobs']):
        job = copy.deepcopy(original)
        fields = LEGACY_FIELDS if payload['format'] == 1 else FIELDS
        if not isinstance(job, dict) or set(job) != fields or type(job['id']) is not int or not 0 <= job['id'] < result.next_id or job['id'] in ids:
            raise ValueError("Invalid saved native job.")
        ids.append(job['id'])
        match = FRAME.fullmatch(job['frame']) if isinstance(job['frame'], str) else None
        manifest = job['manifest']
        if match is None or not manifest_fields(manifest) or stream_id is None or manifest['stream_id'] != stream_id:
            raise ValueError("Invalid saved native frame identity.")
        if type(job['source_sequence']) is not int or not 0 <= job['source_sequence'] <= result.last_source_sequence or job['source_sequence'] != int(match[1]) or type(manifest['sequence']) is not int or manifest['sequence'] != job['source_sequence'] or job['source_sequence'] in sequences:
            raise ValueError("Invalid saved native frame sequence.")
        sequences.append(job['source_sequence'])
        scalar(manifest['captured_wall'], 0, 1e12)
        if manifest['name'] is not None and symbol(manifest['name']) != manifest['name']:
            raise ValueError("Invalid saved native name.")
        if manifest['origin'] not in ('person', 'environment') or not isinstance(manifest['files'], list) or not 1 <= len(manifest['files']) <= 3:
            raise ValueError("Invalid saved native modalities/origin.")
        modalities = []
        for item in manifest['files']:
            if not isinstance(item, dict) or set(item) != {'modality', 'file', 'size', 'sha256'} or item['modality'] not in ('image', 'audio', 'text') or not isinstance(item['file'], str) or re.fullmatch(r'[0-9a-f]{32}\.(png|wav|txt)', item['file']) is None or type(item['size']) is not int or not 1 <= item['size'] <= 8000000 or not isinstance(item['sha256'], str) or re.fullmatch(r'[0-9a-f]{64}', item['sha256']) is None:
                raise ValueError("Invalid saved native signal record.")
            modalities.append(item['modality'])
        if len(set(modalities)) != len(modalities):
            raise ValueError("Saved native frame repeated a modality.")
        validate_frame_details(manifest, modalities)
        scalar(job['issued'], 0, owner.clock)
        scalar(job['received_wall'], manifest['captured_wall'], manifest['captured_wall'] + 3600.)
        scalar(job['acquired_at'], max(0., job['issued'] - 3600.), job['issued'])
        if job['acquired_at'] != max(0., job['issued'] - (job['received_wall'] - manifest['captured_wall'])):
            raise ValueError("Saved native time mapping changed its source.")
        if job['expires'] is not None:
            # Read the first experimental 44 checkpoints without discarding
            # their pending frames because their earlier TTL elapsed offline.
            scalar(job['expires'], job['issued'] + 300., job['issued'] + 300.)
        scalar(job['retry_at'], 0, owner.clock + 5.)
        if job['status'] not in ('waiting', *TERMINAL) or type(job['deferrals']) is not int or not 0 <= job['deferrals'] <= 1000000 or (job['error'] is not None and (not isinstance(job['error'], str) or len(job['error']) > 1024)):
            raise ValueError("Invalid saved native phase/error.")
        content = job['result']
        if payload['format'] == 1:
            trace = next((trace for trace in owner.native.moments.traces if trace['source_context'] is not None
                          and trace['source_context']['stream_id'] == stream_id
                          and trace['source_context']['source_sequence'] == job['source_sequence']), None)
            job['moment_ref'] = None if trace is None else owner.native.moments.reference(trace['id'])
        elif job['moment_ref'] is not None:
            validate_job_reference(job['moment_ref'], owner, job)
            if job['status'] not in ('completed', 'failed'):
                raise ValueError('Uncompleted native receipt asserts an archived event.')
        if job['status'] in ('completed', 'ignored'):
            selected = selected_modalities(content, modalities, owner, job)
            if (job['status'] == 'completed') != (content['encoded'] > 0):
                raise ValueError("Saved native perception count changed its phase.")
            learning = content['learning']
            if learning is not None and not isinstance(learning, dict):
                raise ValueError("Invalid saved native learning record.")
            if learning is not None and learning.get('learned') is True:
                if set(learning) != {'learned', 'name', 'modalities', 'autobiographical_write'} or learning['name'] != manifest['name'] or set(learning['modalities']) != set(selected) or learning['autobiographical_write'] is not False:
                    raise ValueError("Saved native lesson changed its teaching claim.")
                matching = [item for item in owner.native.sources if item['sequence'] == job['id'] and item['origin'] == manifest['origin']
                            and item['name'] == manifest['name'] and item['acquired_at'] == job['acquired_at']
                            and item['samples'] == {item['modality']: item['sha256'] for item in manifest['files'] if item['modality'] in selected}]
                if len(matching) != 1:
                    raise ValueError("Saved native lesson lost its neural source.")
            elif learning is not None:
                if set(learning) != {'learned', 'reason'} or learning['learned'] is not False or learning['reason'] not in ('stale_label', 'self_generated_name', 'no_synchronized_native_percept', 'native_association_error'):
                    raise ValueError("Invalid saved native refusal.")
            for item in content['recognized']:
                if not isinstance(item, dict) or item.get('modality') not in selected or type(item.get('supported')) is not bool:
                    raise ValueError("Invalid saved native recognition.")
                if item['supported']:
                    if set(item) != {'modality', 'supported', 'name', 'score', 'margin', 'variance', 'confidence_is_calibrated', 'autobiographical_write'} or item['name'] not in owner.native.names or item['confidence_is_calibrated'] is not False or item['autobiographical_write'] is not False:
                        raise ValueError("Invalid saved native recognized name.")
                    for field in ('score', 'margin'):
                        scalar(item[field], -10000., 10000.)
                    scalar(item['variance'], 0., 1000000.)
                elif set(item) not in ({'modality', 'supported', 'reason'}, {'modality', 'supported', 'reason', 'variance'}) or item['reason'] not in ('no_learned_names', 'outside_learned_coverage'):
                    raise ValueError("Invalid saved native recognition refusal.")
                elif 'variance' in item:
                    scalar(item['variance'], 0., 1000000.)
        elif content is not None:
            raise ValueError("Uncompleted native frame asserts a result.")
        if original in payload['deliveries']:
            if job['status'] not in TERMINAL:
                raise ValueError("Saved native delivery is unfinished.")
            result.deliveries.append(job)
        else:
            result.jobs[job['id']] = job
    if stream_id is None and (result.last_source_sequence != -1 or ids):
        raise ValueError("Native work has no source stream.")
    return result
