"""Open sensory names learned in weights; no synthetic category classifier.

The encoder supplies prior perceptual features. External synchronized names
teach new associations. Covariance and score thresholds are coverage heuristics,
not calibrated confidence or general conceptual understanding.
"""
from __future__ import annotations

import copy
import sqlite3

import torch
from torch.nn import functional as F

from .concept_memory import scalar
from .grounded_mind import WrittenName
from .native_regions import validate_regions
from .native_sensor import DIMENSION, MODALITIES, NativeObservation, REPRESENTATION
from .online_memory import OnlineMemory
from .written_symbols import symbol

CAPACITY = 32


class NativeGrounding:
    def __init__(self, *, implicit_recall=False):
        if type(implicit_recall) is not bool:
            raise ValueError('Invalid implicit native recall configuration.')
        self.implicit_recall = implicit_recall
        self.recall_context = None
        self.recall_preference = None
        self.names = []
        self.readers = {name: OnlineMemory(DIMENSION, CAPACITY) for name in MODALITIES}
        self.writers = {name: OnlineMemory(CAPACITY, DIMENSION) for name in MODALITIES}
        self.sources = []
        self.naming_proofs = []
        self.last = {}
        self.label_sequence = {}
        self.active = None
        self.working = torch.zeros(DIMENSION, dtype=torch.float32)
        self.clock = 0.
        self.observations = 0
        self.received_observations = 0
        from .native_moments import NativeMoments
        self.moments = NativeMoments()
        from .native_interpretation import NativeInterpretations
        self.interpretations = NativeInterpretations()
        from .native_dynamics import NativeDynamics
        self.dynamics = NativeDynamics()
        from .native_attention import NativeAttention
        self.attention = NativeAttention()
        from .native_links import NativeLinks
        self.links = NativeLinks()

    def configure_implicit_recall(self, enabled):
        if type(enabled) is not bool:
            raise ValueError('Implicit recall must be enabled or disabled explicitly.')
        self.implicit_recall = enabled

    def learn_recall_preference(self, outcome):
        if self.recall_preference is None:
            return {'learned': False, 'reason': 'no_contextual_recollection'}
        return self.recall_preference.learn(outcome, self.clock)

    def advance(self, now):
        scalar(now, self.clock, 1e12)
        self.working.mul_(2. ** (-(now - self.clock) / 5.))
        self.clock = now
        if self.recall_preference is not None:
            self.recall_preference.advance(now)
        self.moments.advance(now)
        self.dynamics.advance(now)
        self.links.advance(now)
        self.active = None

    def observe(self, packets, now, source_context=None, *, regions=None):
        if not isinstance(packets, (list, tuple)) or not 1 <= len(packets) <= 3 or any(not isinstance(item, NativeObservation) for item in packets):
            raise ValueError("Native frame requires one to three typed percepts.")
        for item in packets:
            item.validate()
            scalar(item.acquired_at, 0, now)
        if len({item.modality for item in packets}) != len(packets) or max(item.acquired_at for item in packets) - min(item.acquired_at for item in packets) > .025:
            raise ValueError("Native frame modalities must be unique and synchronized.")
        if regions is not None:
            image = next((item for item in packets if item.modality == 'image'), None)
            if image is None:
                raise ValueError('Visual regions require an image in the same frame.')
            validate_regions(regions, image.sample_sha256)
        scalar(now, self.clock, 1e12)
        accepted = [item for item in packets if item.origin != 'self'
                    and item.sequence > self.last.get(item.modality + ':' + item.origin, {}).get('sequence', -1)
                    and item.acquired_at >= self.last.get(item.modality + ':' + item.origin, {}).get('acquired_at', 0)]
        if not accepted:
            return {'encoded': 0, 'reason': 'self_or_stale', 'autobiographical_write': False}
        if self.received_observations + len(accepted) > 6000006:
            raise ValueError("Native observation counter budget reached.")
        prior = self.working * 2. ** (-(now - self.clock) / 5.)
        attention = self.attention.choose(prior, [item.modality for item in accepted], now)
        attended = [item for item in accepted if item.modality in attention['modalities']]
        regions = regions if 'image' in attention['modalities'] else None
        try:
            moment = self.moments.capture(attended, now, source_context, regions=regions) if attended else None
        except BaseException:
            self.attention.pending.pop(attention['id'], None)
            raise
        if attention['id'] is not None:
            self.attention.bind_moment(attention['id'], self.moments.reference(moment))
        if moment is not None and (self.implicit_recall or self.recall_context is not None):
            if self.recall_context is None:
                from .native_recall_context import RecallContexts
                from .native_recall_preference import RecallPreference
                self.recall_context = RecallContexts(self.moments.capacity)
                self.recall_preference = RecallPreference()
            self.recall_context.capture(self.moments, moment, prior)
        self.advance(now)
        for item in accepted:
            self.last[item.modality + ':' + item.origin] = {'sequence': item.sequence, 'acquired_at': item.acquired_at}
        self.received_observations += len(accepted)
        self.observations += len(attended)
        if not attended:
            return {'encoded': 0, 'received': len(accepted), 'reason': 'unattended', 'attention': attention,
                    'autobiographical_write': False}
        current = F.normalize(torch.stack([item.latent for item in attended]).mean(0), dim=0)
        self.working.copy_(F.normalize(self.working + current, dim=0))
        self.active = {'packets': [copy.deepcopy(item) for item in attended], 'consumed': False, 'received_at': now}
        prediction_learning = self.dynamics.observe(attended, now)
        association_learning = self.links.observe(attended, now, prior)
        result = {'encoded': len(attended), 'received': len(accepted), 'attention': attention,
                'representation': REPRESENTATION, 'moment': moment,
                'prediction_learning': prediction_learning, 'association_learning': association_learning,
                'autobiographical_write': True}
        if self.implicit_recall:
            from .native_reactivation import activate
            try:
                result['implicit_reactivation'] = activate(self, attended, now, moment, regions=regions)
            except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
                # The external percept is already acquired. A secondary recall
                # failure must remain visible without pretending acquisition failed.
                result['implicit_reactivation'] = {'supported': False, 'reason': 'recall_read_error',
                                                   'error': str(error)[:1024], 'autobiographical_write': False}
            if attention['modalities'] == ['audio']:
                try:
                    result['audio_association'] = self.recognize_visual_name_from_sound(attended[0], before=moment)
                except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
                    result['audio_association'] = {'supported': False, 'reason': 'recall_read_error',
                                                   'error': str(error)[:1024]}
        return result

    def teach(self, item, now):
        if not isinstance(item, WrittenName):
            raise ValueError("Native association requires an external written-name lesson.")
        item.validate()
        scalar(now, self.clock, 1e12)
        if item.origin == 'self':
            return {'learned': False, 'reason': 'self_generated_name'}
        if item.sequence <= self.label_sequence.get(item.origin, -1):
            return {'learned': False, 'reason': 'stale_label'}
        active = self.active
        if active is None or active['consumed'] or active['received_at'] != now or any(abs(packet.acquired_at - item.acquired_at) > .025 for packet in active['packets']):
            return {'learned': False, 'reason': 'no_synchronized_native_percept'}
        result = self._write_named(item, active['packets'])
        active['consumed'] = True
        return result

    def _write_named(self, item, packets):
        name = symbol(item.text)
        if len(self.sources) >= 512 or (name not in self.names and len(self.names) >= CAPACITY):
            raise ValueError("Native association capacity reached; earlier weights retained.")
        index = self.names.index(name) if name in self.names else len(self.names)
        label = F.one_hot(torch.tensor(index), CAPACITY).double()
        readers, writers = copy.deepcopy(self.readers), copy.deepcopy(self.writers)
        for packet in packets:
            readers[packet.modality].write(packet.latent.double(), label, strength=10.)
            writers[packet.modality].write(label, packet.latent.double(), strength=10.)
        if any(not torch.isfinite(tensor).all() for bank in (*readers.values(), *writers.values()) for tensor in bank.state_dict().values()):
            raise ValueError("Native association update diverged; prior weights retained.")
        self.readers, self.writers = readers, writers
        if name not in self.names:
            self.names.append(name)
        self.sources.append({'name': name, 'origin': item.origin, 'sequence': item.sequence, 'acquired_at': item.acquired_at,
                             'samples': {packet.modality: packet.sample_sha256 for packet in packets}})
        self.label_sequence[item.origin] = item.sequence
        return {'learned': True, 'name': name, 'modalities': list(self.sources[-1]['samples']), 'autobiographical_write': False}

    def teach_retained_name(self, name, reference, modality, origin, issued, language):
        from .native_reference import validate_reference
        from .native_name_language import validate_source
        from .native_moments import cue_key
        validate_reference(reference, self.clock, self.moments.next_id)
        validate_source(language)
        scalar(issued, 0, self.clock)
        if origin not in ('person', 'environment') or modality not in MODALITIES:
            raise ValueError('Named perception requires an external teacher and selected modality.')
        trace = self.moments.get(reference['id'])
        if trace is None:
            return {'learned': False, 'reason': 'no_retained_named_moment'}
        if self.moments.reference(reference['id']) != reference or not trace['received_at'] <= issued <= self.clock:
            raise ValueError('Named perception changed its original experience or teaching time.')
        if modality not in reference['sources']:
            return {'learned': False, 'reason': 'named_modality_was_not_attended'}
        slot = MODALITIES.index(modality)
        route = F.normalize(self.moments.routes[self.moments.slot(reference['id']), slot].float(), dim=0)
        source = reference['sources'][modality]
        cue = NativeObservation(modality, route, reference['acquired_at'], source['sequence'], source['sha256'], origin=source['origin'])
        bank = self.moments.bank(reference['id'])
        key = cue_key(cue)
        value = bank.read(key).reshape(3, DIMENSION)[slot]
        if bank.variance(key) > 25. or value.norm() < .5:
            return {'learned': False, 'reason': 'named_moment_outside_coverage'}
        packet = NativeObservation(modality, F.normalize(value.float(), dim=0), reference['acquired_at'], source['sequence'], source['sha256'], origin=source['origin'])
        sequence = self.label_sequence.get(origin, -1) + 1
        if sequence > 1000000:
            raise ValueError('Native teaching sequence budget reached.')
        item = WrittenName(name, issued, sequence, origin)
        item.validate()
        index = len(self.sources)
        result = self._write_named(item, [packet])
        self.naming_proofs.append({'source_index': index, 'moment_ref': copy.deepcopy(reference),
                                   'issued': issued, 'received_at': trace['received_at'], 'language': copy.deepcopy(language)})
        return {**result, 'source_index': index, 'retained_moment': reference['id']}

    def learn_attention(self, outcome, language=None):
        from .importance import Consequence
        if not isinstance(outcome, Consequence):
            raise ValueError('Attention feedback requires an external consequence.')
        outcome.validate()
        scalar(outcome.acquired_at, 0, self.clock)
        choice = self.attention.pending.get(outcome.action_id)
        prepared = None
        if choice is not None and choice['issued'] <= outcome.acquired_at <= choice['issued'] + 60 and choice['moment_ref'] is not None:
            prepared = self.moments.prepare_impact(choice['moment_ref'], outcome, self.clock)
        result = self.attention.learn(outcome, self.clock, language)
        if result['learned']:
            result['memory_impact'] = (self.moments.commit_impact(prepared, self.attention.sources[-1], self.clock)
                                       if prepared is not None else {'learned': False, 'reason': 'no_retained_attended_moment'})
        return result

    def recognize(self, packet):
        packet.validate()
        if not self.names:
            return {'supported': False, 'reason': 'no_learned_names'}
        bank = self.readers[packet.modality]
        scores = bank.weights @ packet.latent.double()
        order = scores[:len(self.names)].argsort(descending=True)
        best = int(order[0])
        score = float(scores[best])
        margin = score - (float(scores[int(order[1])]) if len(order) > 1 else 0.)
        variance = float(bank.variance(packet.latent.double()))
        if score < .7 or margin < .2 or variance > 25:
            return {'supported': False, 'reason': 'outside_learned_coverage', 'variance': variance}
        return {'supported': True, 'name': self.names[best], 'score': score, 'margin': margin,
                'variance': variance, 'confidence_is_calibrated': False, 'autobiographical_write': False}

    def evoke(self, name, modality):
        name = symbol(name)
        if modality not in MODALITIES:
            raise ValueError("Invalid native recall modality.")
        if name not in self.names or not any(item['name'] == name and modality in item['samples'] for item in self.sources):
            return {'supported': False, 'reason': 'unlearned_native_meaning'}
        index = self.names.index(name)
        label = F.one_hot(torch.tensor(index), CAPACITY).double()
        bank = self.writers[modality]
        latent = bank.weights @ label
        if latent.norm() < .1 or bank.variance(label) > 25:
            return {'supported': False, 'reason': 'unlearned_weights'}
        return {'supported': True, 'name': name, 'modality': modality, 'latent': F.normalize(latent.float(), dim=0),
                'kind': 'learned_meaning', 'autobiographical_write': False}

    def cross(self, packet, target):
        result = self.recognize(packet)
        if not result['supported']:
            return result
        return self.evoke(result['name'], target)

    def recognize_visual_name_from_sound(self, sound, *, before=None):
        from .native_audio_naming import recognize
        return recognize(self, sound, self.moments.next_id if before is None else before)

    def associate(self, packet, target, contextual=False):
        if type(contextual) is not bool:
            raise ValueError('Invalid cross-modal contextual query mode.')
        return self.links.predict(packet, target, self.working if contextual else None)

    def recall_moments(self, cues, window=None, targets=None, utc_window=None, reactivate=True):
        return self.moments.recall(cues, self.clock, window, targets, utc_window, reactivate)

    def teach_interpretation(self, statement, language=None):
        return self.interpretations.teach(statement, self.moments, self.clock, language)

    def interpret(self, moment, relation, view='current'):
        if type(moment) is not int or (self.moments.get(moment) is None and not any(record['moment'] == moment for record in self.interpretations.records)):
            raise ValueError('Interpretation query refers to an unobserved moment.')
        return self.interpretations.query(moment, relation, view)

    def snapshot(self, moment_snapshot=None):
        if (self.recall_context is None) != (self.recall_preference is None):
            raise ValueError('Contextual memory and its learned policy must share an owner.')
        result = {'format': 10 if self.recall_context is not None else (9 if self.implicit_recall else 8), 'representation': REPRESENTATION, 'names': self.names.copy(), 'moments': self.moments.snapshot() if moment_snapshot is None else moment_snapshot,
                'naming_proofs': copy.deepcopy(self.naming_proofs),
                'interpretations': self.interpretations.snapshot(),
                'dynamics': self.dynamics.snapshot(),
                'attention': self.attention.snapshot(), 'received_observations': self.received_observations,
                'links': self.links.snapshot(),
                'readers': {name: {key: value.clone() for key, value in bank.state_dict().items()} for name, bank in self.readers.items()},
                'writers': {name: {key: value.clone() for key, value in bank.state_dict().items()} for name, bank in self.writers.items()},
                'sources': copy.deepcopy(self.sources), 'last': copy.deepcopy(self.last), 'label_sequence': self.label_sequence.copy(),
                'active': None if self.active is None else {'packets': [{**vars(item), 'latent': item.latent.clone()} for item in self.active['packets']],
                                                          'consumed': self.active['consumed'], 'received_at': self.active['received_at']},
                'working': self.working.clone(), 'clock': self.clock, 'observations': self.observations}
        if self.implicit_recall or self.recall_context is not None:
            result['implicit_recall'] = self.implicit_recall
        if self.recall_context is not None:
            result.update(recall_context=self.recall_context.snapshot(), recall_preference=self.recall_preference.snapshot())
        return result


def restore(payload, now):
    fields = {'format', 'representation', 'names', 'readers', 'writers', 'sources', 'last', 'label_sequence',
              'active', 'working', 'clock', 'observations'}
    if isinstance(payload, dict) and payload.get('format') in (2, 3, 4, 5, 6, 7, 8, 9, 10):
        fields.add('moments')
    if isinstance(payload, dict) and payload.get('format') in (3, 4, 5, 6, 7, 8, 9, 10):
        fields.add('interpretations')
    if isinstance(payload, dict) and payload.get('format') in (4, 5, 6, 7, 8, 9, 10):
        fields.add('dynamics')
    if isinstance(payload, dict) and payload.get('format') in (5, 6, 7, 8, 9, 10):
        fields.update(('attention', 'received_observations'))
    if isinstance(payload, dict) and payload.get('format') in (7, 8, 9, 10):
        fields.add('links')
    if isinstance(payload, dict) and payload.get('format') in (8, 9, 10):
        fields.add('naming_proofs')
    if isinstance(payload, dict) and payload.get('format') in (9, 10):
        fields.add('implicit_recall')
    if isinstance(payload, dict) and payload.get('format') == 10:
        fields.update(('recall_context', 'recall_preference'))
    if not isinstance(payload, dict) or set(payload) != fields or type(payload['format']) is not int or payload['format'] not in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10) or payload['representation'] != REPRESENTATION:
        raise ValueError("Invalid native grounding checkpoint.")
    if payload['format'] == 9 and payload['implicit_recall'] is not True:
        raise ValueError('Invalid enabled implicit recall checkpoint.')
    if payload['format'] == 10 and type(payload['implicit_recall']) is not bool:
        raise ValueError('Invalid contextual implicit recall configuration.')
    result = NativeGrounding(implicit_recall=payload.get('implicit_recall', False))
    names, sources = payload['names'], payload['sources']
    if not isinstance(names, list) or len(names) > CAPACITY or any(symbol(name) != name for name in names) or len(names) != len(set(names)):
        raise ValueError("Invalid learned native names.")
    if not isinstance(sources, list) or len(sources) > 512:
        raise ValueError("Invalid native source budget.")
    scalar(payload['clock'], 0, now)
    for group in ('readers', 'writers'):
        saved = payload[group]
        banks = getattr(result, group)
        if not isinstance(saved, dict) or set(saved) != set(MODALITIES):
            raise ValueError("Invalid native modality banks.")
        for modality, bank in banks.items():
            state, expected = saved[modality], bank.state_dict()
            if not isinstance(state, dict) or set(state) != set(expected) or any(not isinstance(value, torch.Tensor) or value.device.type != 'cpu' or value.dtype != expected[key].dtype or value.shape != expected[key].shape or not torch.isfinite(value).all() for key, value in state.items()):
                raise ValueError("Invalid native learned tensors.")
            bank.load_state_dict(state)
            if not 0 <= int(bank.writes) <= 512 or bank.weights.abs().max() > 10000 or not torch.allclose(bank.precision, bank.precision.T, atol=1e-8, rtol=0) or torch.linalg.cholesky_ex(bank.precision).info.item() != 0:
                raise ValueError("Invalid native covariance/update count.")
    previous, counts = {}, {name: 0 for name in MODALITIES}
    for item in sources:
        expected = {'name', 'origin', 'sequence', 'acquired_at', 'samples'}
        if not isinstance(item, dict) or set(item) != expected or item['name'] not in names or item['origin'] not in ('person', 'environment') or type(item['sequence']) is not int or not 0 <= item['sequence'] <= 1000000:
            raise ValueError("Invalid native teaching provenance.")
        scalar(item['acquired_at'], 0, payload['clock'])
        if item['sequence'] <= previous.get(item['origin'], -1):
            raise ValueError("Nonmonotonic native name sources.")
        previous[item['origin']] = item['sequence']
        samples = item['samples']
        if not isinstance(samples, dict) or not 1 <= len(samples) <= 3 or any(name not in MODALITIES for name in samples):
            raise ValueError("Invalid native teaching samples.")
        for modality, digest in samples.items():
            NativeObservation(modality, F.one_hot(torch.tensor(0), DIMENSION).float(), 0., 0, digest).validate()
            counts[modality] += 1
    if set(names) != {item['name'] for item in sources} or payload['label_sequence'] != previous:
        raise ValueError("Native names/label counters disagree with sources.")
    for modality in MODALITIES:
        if int(result.readers[modality].writes) != counts[modality] or int(result.writers[modality].writes) != counts[modality]:
            raise ValueError("Native bank writes disagree with source counts.")
    last = payload['last']
    if not isinstance(last, dict) or any(key not in {modality + ':' + origin for modality in MODALITIES for origin in ('person', 'environment')} for key in last):
        raise ValueError("Invalid native sensor sequence keys.")
    for item in last.values():
        if not isinstance(item, dict) or set(item) != {'sequence', 'acquired_at'} or type(item['sequence']) is not int or not 0 <= item['sequence'] <= 1000000:
            raise ValueError("Invalid native sensor sequence record.")
        scalar(item['acquired_at'], 0, payload['clock'])
    working = payload['working']
    if not isinstance(working, torch.Tensor) or working.device.type != 'cpu' or working.dtype != torch.float32 or working.shape != (DIMENSION,) or not torch.isfinite(working).all() or working.norm() > 1.00001:
        raise ValueError("Invalid native working state.")
    received = payload.get('received_observations', payload['observations'])
    if type(received) is not int or not len(last) <= received <= 6000006 or type(payload['observations']) is not int or not 0 <= payload['observations'] <= received:
        raise ValueError("Invalid native observation count.")
    active = payload['active']
    if active is not None:
        if not isinstance(active, dict) or set(active) != {'packets', 'consumed', 'received_at'} or type(active['consumed']) is not bool or not isinstance(active['packets'], list) or not 1 <= len(active['packets']) <= 3:
            raise ValueError("Invalid native active frame.")
        if active['received_at'] != payload['clock']:
            raise ValueError("Native active frame is not current.")
        packets = []
        for fields in active['packets']:
            if not isinstance(fields, dict) or set(fields) != {'modality', 'latent', 'acquired_at', 'sequence', 'sample_sha256', 'representation', 'origin'}:
                raise ValueError("Invalid saved native percept fields.")
            packet = NativeObservation(**fields)
            packet.validate()
            record = last.get(packet.modality + ':' + packet.origin)
            if record != {'sequence': packet.sequence, 'acquired_at': packet.acquired_at}:
                raise ValueError("Native active frame lost its sequence source.")
            scalar(packet.acquired_at, 0, payload['clock'])
            packets.append(packet)
        if len({packet.modality for packet in packets}) != len(packets) or max(packet.acquired_at for packet in packets) - min(packet.acquired_at for packet in packets) > .025:
            raise ValueError("Invalid native frame synchronization.")
        active = {**active, 'packets': packets}
    result.names, result.sources = names.copy(), copy.deepcopy(sources)
    result.last, result.label_sequence = copy.deepcopy(last), previous
    result.clock, result.observations = payload['clock'], payload['observations']
    result.received_observations = received
    result.working, result.active = working.clone(), copy.deepcopy(active)
    if payload['format'] in (2, 3, 4, 5, 6, 7, 8, 9, 10):
        from .native_moments import restore as restore_moments
        result.moments.close()
        result.moments = restore_moments(payload['moments'], now)
        observed = result.moments.pre_archive_observations + result.moments.total_observations
        if observed != result.observations or result.moments.clock != result.clock:
            result.moments.close()
            raise ValueError("Native moments and sensory state disagree about time/count.")
    else:
        result.moments.pre_archive_observations = result.observations
        result.moments.clock = result.clock
    if payload['format'] in (3, 4, 5, 6, 7, 8, 9, 10):
        from .native_interpretation import restore as restore_interpretations
        try:
            result.interpretations = restore_interpretations(payload['interpretations'], result.moments, now)
        except BaseException:
            result.moments.close()
            raise
    from .native_dynamics import NativeDynamics, restore as restore_dynamics
    try:
        result.dynamics = (restore_dynamics(payload['dynamics'], result.clock, result.moments.next_id)
                           if payload['format'] in (4, 5, 6, 7, 8, 9, 10) else NativeDynamics(result.clock, result.moments.next_id))
        from .native_attention import restore as restore_attention
        if payload['format'] in (5, 6, 7, 8, 9, 10):
            result.attention = restore_attention(payload['attention'], result.clock)
        validate_attention_bindings(result)
        from .native_links import NativeLinks, restore as restore_links
        result.links = (restore_links(payload['links'], result.clock, result.moments.next_id)
                        if payload['format'] in (7, 8, 9, 10) else NativeLinks(result.clock, result.moments.next_id))
        if payload['format'] in (8, 9, 10):
            result.naming_proofs = restore_naming_proofs(payload['naming_proofs'], result)
        if payload['format'] == 10:
            from .native_recall_context import restore as restore_contexts
            from .native_recall_preference import restore as restore_preference
            result.recall_context = restore_contexts(payload['recall_context'], result.moments)
            result.recall_preference = restore_preference(payload['recall_preference'], result.moments, result.clock)
    except BaseException:
        result.moments.close()
        raise
    return result


def restore_naming_proofs(proofs, native):
    from .native_reference import validate_reference
    from .native_name_language import validate_source
    if not isinstance(proofs, list) or len(proofs) > len(native.sources):
        raise ValueError('Invalid named-perception proof budget.')
    previous = -1
    for proof in proofs:
        if not isinstance(proof, dict) or set(proof) != {'source_index', 'moment_ref', 'issued', 'received_at', 'language'} or type(proof['source_index']) is not int or not previous < proof['source_index'] < len(native.sources):
            raise ValueError('Invalid named-perception source index.')
        previous = proof['source_index']
        reference = validate_reference(proof['moment_ref'], native.clock, native.moments.next_id)
        source = native.sources[previous]
        scalar(proof['received_at'], reference['acquired_at'], native.clock)
        scalar(proof['issued'], proof['received_at'], native.clock)
        validate_source(proof['language'])
        if source['acquired_at'] != proof['issued'] or len(source['samples']) != 1 or any(modality not in reference['sources'] or digest != reference['sources'][modality]['sha256'] for modality, digest in source['samples'].items()):
            raise ValueError('Named-perception source lost its sensory binding.')
        current = native.moments.reference(reference['id'])
        if current is not None and current != reference:
            raise ValueError('Named-perception proof changed its original retained event.')
        if current is not None and native.moments.get(reference['id'])['received_at'] != proof['received_at']:
            raise ValueError('Named-perception proof changed its original receipt time.')
    return copy.deepcopy(proofs)


def validate_attention_bindings(native):
    from .native_reference import validate_reference
    for item in (*native.attention.pending.values(), *native.attention.sources):
        reference = item['moment_ref']
        if reference is None:
            continue
        validate_reference(reference, native.clock, native.moments.next_id)
        current = native.moments.reference(reference['id'])
        if current is not None and current != reference:
            raise ValueError('Attention consequence changed its original sensory event.')
        trace = native.moments.get(reference['id'])
        if trace is not None and 'issued' in item and trace['received_at'] != item['issued']:
            raise ValueError('Pending attention action changed its acquisition time.')
        if trace is not None and 'acquired_at' in item and (trace['impact'] is None or trace['impact']['id'] != item['id']):
            raise ValueError('Retained consequence lost its learned episode impact.')
    sources = {source['id']: source for source in native.attention.sources}
    for trace in native.moments.traces:
        impact = trace['impact']
        if impact is None:
            continue
        source = sources.get(impact['id'])
        if source is None or source['moment_ref'] != native.moments.reference(trace['id']) or any(source[key] != value for key, value in impact.items() if key != 'received_at'):
            raise ValueError('Episode impact lost its attention consequence source.')
