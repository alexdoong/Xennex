"""Named sensory questions evoke weights on the existing continuous owner."""
from __future__ import annotations

import copy
import hashlib
import json

from .concept_memory import scalar
from .concept_query import ConceptQueryLane, FIELDS
from .concept_teaching import TeachingLane
from .native_query_language import MODALITIES, sha, validate_plan, validate_evidence, validate_expression, window_numbers
from .native_sensor import NativeObservation


def tensor_hash(value):
    return hashlib.sha256(value.detach().cpu().contiguous().numpy().tobytes()).hexdigest()


def signature(native, plan, selected=None):
    value = hashlib.sha256()
    metadata = {'names': native.names, 'sources': native.sources, 'moments': native.moments.next_id,
                'retained': [{key: trace[key] for key in ('id', 'acquired_at', 'known', 'sources', 'source_context')}
                             for trace in native.moments.traces],
                'relative_window_available': plan['window_fragment'] is None or plan['basis'] == 'utc'
                    or window_numbers(plan['window_fragment'])[1] <= native.clock}
    value.update(json.dumps(metadata, ensure_ascii=False, sort_keys=True).encode())
    for modality in MODALITIES:
        for key, tensor in sorted(native.writers[modality].state_dict().items()):
            value.update(key.encode())
            value.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    value.update(native.moments.routes[:len(native.moments.traces)].numpy().tobytes())
    if selected is not None:
        bank = native.moments.bank(selected)
        for key, tensor in sorted(bank.snapshot().items()):
            value.update(key.encode())
            value.update(tensor.detach().cpu().contiguous().numpy().tobytes() if hasattr(tensor, 'numpy') else str(tensor).encode())
    return value.hexdigest()


def resolve(native, plan, question, computed_at=None, reactivate=True):
    window = None if plan['window_fragment'] is None else window_numbers(plan['window_fragment'])
    evidence = {'kind': 'native_recall', 'name': plan['name'], 'cue_modalities': [], 'window': window,
                'basis': plan['basis'], 'supported': False, 'reason': 'unlearned_native_meaning',
                'candidate_count': 0, 'candidate_ids': [], 'moment_id': None, 'acquired_at': None,
                'modalities': [], 'evoked_sha256': {}, 'query_sha256': sha(question),
                'computed_at': native.clock if computed_at is None else computed_at, 'signature': '',
                'confidence_is_calibrated': False}
    cues = []
    for modality in plan['modalities'] or list(MODALITIES):
        meaning = native.evoke(plan['name'], modality)
        if not meaning['supported']:
            if plan['modalities']:
                evidence['reason'] = meaning['reason']
                cues = []
                break
            continue
        cues.append(NativeObservation(modality, meaning['latent'], native.clock, 0,
                    sha('native-name-cue:' + plan['name'] + ':' + modality), origin='self'))
        if not plan['modalities']:
            break  # Fixed primary cue, not selection by desired answer/candidate count.
    if cues:
        evidence['cue_modalities'] = [cue.modality for cue in cues]
        if window is not None and plan['basis'] == 'relative' and window[1] > native.clock:
            evidence['reason'] = 'future_window'
        else:
            result = native.recall_moments(cues, window=window if plan['basis'] == 'relative' else None,
                        utc_window=window if plan['basis'] == 'utc' else None, reactivate=reactivate)
            evidence.update(supported=result['supported'], reason=result['reason'],
                            candidate_count=len(result['candidates']),
                            candidate_ids=sorted(item['id'] for item in result['candidates'])[:8])
            if result['supported']:
                evidence.update(moment_id=result['moment']['id'], acquired_at=result['moment']['acquired_at'],
                    modalities=[item for item in MODALITIES if item in result['representations']],
                    evoked_sha256={key: tensor_hash(value) for key, value in result['representations'].items()})
    selected = evidence['candidate_ids'][0] if evidence['candidate_count'] == 1 else None
    evidence['signature'] = signature(native, plan, selected)
    validate_evidence(evidence)
    return evidence


class NativeQueryLane(ConceptQueryLane):
    job_kind = 'native_query'
    parse_stage = 'native_parse'
    expression_stage = 'native_expression'
    plan_validator = staticmethod(validate_plan)
    evidence_validator = staticmethod(validate_evidence)
    expression_validator = staticmethod(validate_expression)
    evidence_resolver = staticmethod(resolve)

    def __init__(self, coordinator, native):
        super().__init__(coordinator, native)
        self.native = native

    def current(self, evidence):
        job = next((item for item in self.jobs.values() if item['evidence'] is evidence), None)
        if job is None:
            return False
        selected = evidence['candidate_ids'][0] if evidence['candidate_count'] == 1 else None
        if selected is not None and self.native.moments.get(selected) is None:
            return False
        return evidence['signature'] == signature(self.native, job['plan'], selected)

    def resolve(self, job):
        job['evidence'] = self.evidence_resolver(self.native, job['plan'], job['question'])
        job.update(status='ready_to_express', proposal=None, error=None)
        return True

    def finish(self, job, result):
        if result['status'] == 'deferred':
            job.update(status='waiting' if job['status'] == 'parsing' else 'ready_to_express',
                       retry_at=self.coordinator.clock + self.coordinator.retry_seconds,
                       error='resource_admission_deferred', deferrals=job['deferrals'] + 1)
            return 'deferred'
        if result['status'] != 'ready':
            job.update(status='failed', error=str(result.get('value'))[:2048])
            return 'failed'
        if job['status'] == 'parsing':
            plan = self.plan_validator(result['value'], job['question'], self.coordinator.model)
            job['plan'] = copy.deepcopy(plan)
            if plan['uncertain']:
                job.update(status='uncertain', error=None)
                return 'uncertain'
            self.resolve(job)
            return 'resolved'
        if not self.current(job['evidence']):
            job['revisions'] += 1
            self.resolve(job)
            return 'revised'
        proposal = self.expression_validator(result['value'], job['evidence'], self.coordinator.model)
        job.update(status='completed', proposal=copy.deepcopy(proposal), error=None)
        return 'completed'

    def take(self, number):
        job = self.jobs[number]
        if job['status'] == 'completed' and not self.current(job['evidence']):
            job['revisions'] += 1
            self.resolve(job)
        result = TeachingLane.take(self, number)
        if result is not None:
            result.update(factual_text_verified=result['status'] == 'completed',
                          expression_policy='bounded_grounded_phrases', free_text_semantics_verified=False,
                          autobiographical_write=False, confidence_is_calibrated=False)
        return result


def restore(payload, coordinator, native, lane_type=NativeQueryLane):
    if not isinstance(payload, dict) or set(payload) != {'format', 'next_id', 'jobs'} or type(payload['format']) is not int or payload['format'] != 1 or type(payload['next_id']) is not int or not 1 <= payload['next_id'] <= 1000000 or not isinstance(payload['jobs'], list) or len(payload['jobs']) > 4:
        raise ValueError('Invalid native query checkpoint.')
    lane = lane_type(coordinator, native)
    lane.next_id = payload['next_id']
    for original in payload['jobs']:
        job = copy.deepcopy(original)
        if not isinstance(job, dict) or set(job) != FIELDS or type(job['id']) is not int or not 1 <= job['id'] < lane.next_id or job['id'] in lane.jobs:
            raise ValueError('Invalid saved native query.')
        from .language_input import references
        references(job['question'])
        scalar(job['issued'], 0, coordinator.clock)
        scalar(job['expires'], job['issued'] + 5, job['issued'] + 3600)
        scalar(job['retry_at'], 0, coordinator.clock + 60)
        if job['status'] not in ('waiting', 'ready_to_express', 'completed', 'uncertain', 'failed', 'cancelled'):
            raise ValueError('Invalid saved native query phase.')
        if any(type(job[key]) is not int or not 0 <= job[key] <= 1000000 for key in ('deferrals', 'revisions')):
            raise ValueError('Invalid saved native query counter.')
        if job['error'] is not None and (not isinstance(job['error'], str) or len(job['error']) > 2048):
            raise ValueError('Invalid saved native query error.')
        plan, evidence, proposal = job['plan'], job['evidence'], job['proposal']
        if plan is not None:
            lane.plan_validator(plan, job['question'], coordinator.model)
        if evidence is not None:
            lane.evidence_validator(evidence)
            if plan is None or plan['uncertain'] or evidence['query_sha256'] != sha(job['question']) or evidence['name'] != plan['name']:
                raise ValueError('Saved native evidence changed its source.')
            scalar(evidence['computed_at'], job['issued'], coordinator.clock)
            current = lane.evidence_resolver(native, plan, job['question'], coordinator.clock, reactivate=False)
            if evidence['signature'] == current['signature']:
                expected = lane.evidence_resolver(native, plan, job['question'], evidence['computed_at'], reactivate=False)
                if evidence != expected:
                    raise ValueError('Saved native evidence disagrees with its learned weights.')
        if proposal is not None:
            if evidence is None:
                raise ValueError('Native expression has no evidence.')
            lane.expression_validator(proposal, evidence, coordinator.model)
        if job['status'] in ('ready_to_express', 'completed') and (plan is None or plan['uncertain'] or evidence is None):
            raise ValueError('Saved native query has no grounded evidence.')
        if (job['status'] == 'completed') != (proposal is not None):
            raise ValueError('Saved native expression phase changed.')
        if job['status'] == 'waiting' and any(item is not None for item in (plan, evidence, proposal)):
            raise ValueError('Unparsed native query asserts a result.')
        if job['status'] == 'uncertain' and (plan is None or not plan['uncertain'] or evidence is not None):
            raise ValueError('Uncertain native query asserts a memory.')
        lane.jobs[job['id']] = job
    return lane
