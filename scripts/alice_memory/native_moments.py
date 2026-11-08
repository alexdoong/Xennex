"""Anonymous sensory moments in fast weights, paged to an owned SQLite archive.

One accepted frame is one moment in this first contract. Segmentation and
importance rules are supplied policies, not learned human event understanding.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import math
from dataclasses import asdict
import sqlite3
from collections import OrderedDict
from pathlib import Path
from uuid import uuid4

import torch
from torch.nn import functional as F

from .concept_memory import scalar
from .native_fast_weights import NativeFastWeights, restore as restore_weights
from .native_reference import MAX_MOMENT_ID, validate_reference
from .native_regions import MIN_GAP, MIN_SIMILARITY, match, validate_regions
from .native_sensor import DIMENSION, MODALITIES, NativeObservation, REPRESENTATION

CAPACITY = 2048
MAX_ARCHIVE = 64_000_000
PAGED_FORMATS = (2, 4, 6, 8, 10)
VALUE_FORMATS = (5, 6, 7, 8, 9, 10)
PRONUNCIATION_FORMATS = (9, 10)
REGION_FORMATS = (7, 8, *PRONUNCIATION_FORMATS)


def cue_key(packet):
    packet.validate()
    slot = F.one_hot(torch.tensor(MODALITIES.index(packet.modality)), 3).double()
    return torch.cat((packet.latent.double(), slot, torch.ones(1, dtype=torch.float64)))


def pack(bank):
    stream = io.BytesIO()
    torch.save(bank.snapshot(), stream)
    return stream.getvalue()


class NativeMoments:
    def __init__(self, capacity=CAPACITY, hot_limit=4):
        if type(capacity) is not int or not 1 <= capacity <= CAPACITY or type(hot_limit) is not int or not 1 <= hot_limit <= min(capacity, 16):
            raise ValueError("Invalid native archive capacity/cache.")
        self.capacity, self.hot_limit = capacity, hot_limit
        self.routes = torch.zeros(capacity, 3, DIMENSION, dtype=torch.float64)
        self.traces = []
        self.regions = {}
        self.pronunciations = {}
        self.cache = OrderedDict()
        self.clock = 0.
        self.pre_archive_observations = 0
        self.next_id = 0
        self.total_observations = 0
        from .native_impact import MomentValues
        self.values = MomentValues(capacity)
        self.loads = self.hits = self.evictions = 0
        self.folder = Path.cwd() / 'bin' / 'AliceNativeMoments'
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / (uuid4().hex + '.sqlite')
        self.connection = sqlite3.connect(self.path)
        self.connection.execute('CREATE TABLE moments (id INTEGER PRIMARY KEY, bank BLOB NOT NULL, digest TEXT NOT NULL)')
        self.connection.commit()
        self.closed = False

    def advance(self, now):
        scalar(now, self.clock, 1e12)
        self.clock = now

    def slot(self, moment):
        if type(moment) is not int or not 0 <= moment < self.next_id:
            return None
        return next((index for index, trace in enumerate(self.traces) if trace['id'] == moment), None)

    def get(self, moment):
        index = self.slot(moment)
        return None if index is None else self.traces[index]

    def reference(self, moment):
        trace = self.get(moment)
        if trace is None:
            return None
        return copy.deepcopy({key: trace[key] for key in ('id', 'acquired_at', 'known', 'sources', 'source_context')})

    def impact(self, trace, now, slot=None):
        if trace['impact'] is None:
            return 0.
        slot = self.slot(trace['id']) if slot is None else slot
        magnitude = self.values.read(slot)['impact']
        return magnitude * math.exp(-max(0., now - trace['impact']['received_at']) / 86400.)

    def prepare_impact(self, reference, outcome, now):
        scalar(now, self.clock, 1e12)
        validate_reference(reference, now, self.next_id)
        slot = self.slot(reference['id'])
        if slot is None:
            return None
        if self.reference(reference['id']) != reference or self.traces[slot]['impact'] is not None:
            raise ValueError('Consequence changed its sensory event or credited it twice.')
        scalar(outcome.acquired_at, self.traces[slot]['received_at'], now)
        candidate = copy.deepcopy(self.values)
        candidate.write(slot, outcome)
        digest = hashlib.sha256(json.dumps(asdict(outcome), sort_keys=True).encode()).hexdigest()
        return slot, candidate, digest

    def commit_impact(self, prepared, source, now):
        slot, candidate, digest = prepared
        if source['sha256'] != digest or self.reference(self.traces[slot]['id']) != source['moment_ref']:
            raise ValueError('Consequence commit lost its event/source binding.')
        self.values = candidate
        self.traces[slot]['impact'] = {key: source[key] for key in ('id', 'action', 'origin', 'acquired_at', 'sha256')}
        self.traces[slot]['impact']['received_at'] = now
        return {'learned': True, 'moment': self.traces[slot]['id'], 'autobiographical_write': False}

    def retention(self, trace, now, slot=None):
        fresh = math.exp(-max(0., now - trace['acquired_at']) / 300.)
        heat = 0. if trace['last_recalled_at'] is None else math.exp(-(now - trace['last_recalled_at']) / 120.)
        return fresh * (.5 + .5 * trace['importance']) + .5 * heat + .5 * self.impact(trace, now, slot)

    def capture(self, packets, now, source_context=None, *, regions=None):
        scalar(now, self.clock, 1e12)
        if not isinstance(packets, (list, tuple)) or not 1 <= len(packets) <= 3 or any(not isinstance(item, NativeObservation) for item in packets):
            raise ValueError("Native moment requires one external synchronized frame.")
        for packet in packets:
            packet.validate()
            scalar(packet.acquired_at, 0, now)
            if packet.origin == 'self':
                raise ValueError("Self-generated signal is not an external sensory moment.")
        if len({item.modality for item in packets}) != len(packets) or max(item.acquired_at for item in packets) - min(item.acquired_at for item in packets) > .025:
            raise ValueError("Native moment repeats or desynchronizes modalities.")
        if self.next_id >= MAX_MOMENT_ID or self.total_observations + len(packets) > 6000006:
            raise ValueError('Native lifetime counter budget reached.')
        validate_context(source_context)
        if regions is not None:
            image = next((item for item in packets if item.modality == 'image'), None)
            if image is None:
                raise ValueError('Cannot retain visual details without their image.')
            validate_regions(regions, image.sample_sha256)
            regions = copy.deepcopy(regions)
        index = self.next_id
        value = torch.zeros(3, DIMENSION, dtype=torch.float64)
        known = [False] * 3
        route = torch.zeros(3, DIMENSION, dtype=torch.float64)
        familiarity = []
        for packet in packets:
            slot = MODALITIES.index(packet.modality)
            value[slot] = packet.latent.double()
            known[slot] = True
            # One-hot-address RLS from a zero bank and P=1000 I. This is the
            # learned route weight, not a separately stored raw vector.
            route[slot] = packet.latent.double() * (1000. / 1000.1)
            if self.traces:
                prior = F.normalize(self.routes[:len(self.traces), slot], dim=-1)
                familiarity.append(float((prior @ packet.latent.double()).max()))
        bank = NativeFastWeights()
        for packet in packets:
            bank.write(cue_key(packet), value.flatten())
        raw = pack(bank)
        digest = hashlib.sha256(raw).hexdigest()
        victim = None if len(self.traces) < self.capacity else min(range(len(self.traces)),
            key=lambda slot: (self.retention(self.traces[slot], now, slot), self.traces[slot]['id']))
        with self.connection:
            if victim is not None:
                self.connection.execute('DELETE FROM moments WHERE id=?', (self.traces[victim]['id'],))
            self.connection.execute('INSERT INTO moments VALUES (?,?,?)', (index, raw, digest))
            size = self.connection.execute('PRAGMA page_count').fetchone()[0] * self.connection.execute('PRAGMA page_size').fetchone()[0]
            if size > MAX_ARCHIVE:
                raise ValueError("Native moment disk budget reached; earlier moments preserved.")
        if victim is not None:
            self.values.retire(victim, len(self.traces))
            forgotten = self.traces.pop(victim)
            self.cache.pop(forgotten['id'], None)
            self.regions.pop(forgotten['id'], None)
            self.pronunciations.pop(forgotten['id'], None)
            if victim < len(self.traces):
                self.routes[victim:len(self.traces)].copy_(self.routes[victim+1:len(self.traces)+1].clone())
            self.routes[len(self.traces)].zero_()
        importance = max(0., min(1., 1. - (sum(familiarity) / len(familiarity) if familiarity else 0.)))
        self.routes[len(self.traces)] = route
        self.traces.append({'id': index, 'acquired_at': min(item.acquired_at for item in packets),
                            'received_at': now, 'known': known, 'importance': importance,
                            'last_recalled_at': None, 'recalls': 0, 'impact': None,
                            'source_context': copy.deepcopy(source_context),
                            'sources': {item.modality: {'origin': item.origin, 'sequence': item.sequence,
                                                      'sha256': item.sample_sha256} for item in packets}})
        if regions is not None:
            self.regions[index] = regions
        self.clock = now
        self.next_id += 1
        self.total_observations += len(packets)
        self.cache[index] = bank
        self.cache.move_to_end(index)
        if len(self.cache) > self.hot_limit:
            self.cache.popitem(last=False)
            self.evictions += 1
        return index

    def bank(self, index):
        if index in self.cache:
            self.hits += 1
            self.cache.move_to_end(index)
            return self.cache[index]
        row = self.connection.execute('SELECT bank,digest FROM moments WHERE id=?', (index,)).fetchone()
        if row is None or len(row[0]) > 50000 or hashlib.sha256(row[0]).hexdigest() != row[1]:
            raise ValueError("Native moment page is missing or corrupt.")
        bank = restore_weights(torch.load(io.BytesIO(row[0]), weights_only=True, map_location='cpu'))
        self.cache[index] = bank
        self.loads += 1
        if len(self.cache) > self.hot_limit:
            self.cache.popitem(last=False)
            self.evictions += 1
        return bank

    def recall(self, cues, now, window=None, targets=None, utc_window=None, reactivate=True, *, candidates_only=False):
        scalar(now, self.clock, 1e12)
        if type(reactivate) is not bool or type(candidates_only) is not bool:
            raise ValueError('Invalid native recall reactivation policy.')
        if not isinstance(cues, (list, tuple)) or not 1 <= len(cues) <= 3 or any(not isinstance(item, NativeObservation) for item in cues):
            raise ValueError("Native recall requires one to three perceptual cues.")
        for cue in cues:
            cue.validate()
        if len({item.modality for item in cues}) != len(cues):
            raise ValueError("Native recall repeats a modality.")
        if window is not None:
            if not isinstance(window, (list, tuple)) or len(window) != 2:
                raise ValueError("Invalid native temporal recall window.")
            scalar(window[0], 0, now)
            scalar(window[1], window[0], now)
        if utc_window is not None:
            if not isinstance(utc_window, (list, tuple)) or len(utc_window) != 2:
                raise ValueError("Invalid native UTC recall window.")
            scalar(utc_window[0], 0, 1e12)
            scalar(utc_window[1], utc_window[0], 1e12)
        if targets is not None and (not isinstance(targets, list) or not 1 <= len(targets) <= 3 or len(set(targets)) != len(targets) or any(item not in MODALITIES for item in targets)):
            raise ValueError("Invalid native recall targets.")
        candidates = []
        for route_slot, trace in enumerate(self.traces):
            if utc_window is not None and (trace['source_context'] is None or not utc_window[0] <= trace['source_context']['captured_wall'] <= utc_window[1]):
                continue
            if window is not None and not window[0] <= trace['acquired_at'] <= window[1]:
                continue
            scores = []
            for cue in cues:
                slot = MODALITIES.index(cue.modality)
                if not trace['known'][slot]:
                    break
                route = self.routes[route_slot, slot]
                scores.append(float(F.normalize(route, dim=0) @ cue.latent.double()))
            if len(scores) != len(cues) or min(scores) < .9:
                continue
            score = sum(scores) / len(scores)
            candidates.append(self.candidate(route_slot, score, now))
        candidates.sort(key=lambda item: (-item['priority'], item['id']))
        result = {'supported': False, 'kind': 'sensory_recollection', 'candidates': candidates,
                  'representations': None, 'confidence_is_calibrated': False, 'autobiographical_write': False}
        if not candidates:
            return {**result, 'reason': 'no_supported_moment'}
        if candidates_only:
            return {**result, 'reason': 'matching_candidates'}
        if len(candidates) > 1:
            return {**result, 'reason': 'ambiguous_moments'}
        recalled = self.read_candidate(candidates[0]['id'], cues, targets)
        if not recalled['supported']:
            return {**result, 'reason': recalled['reason']}
        if reactivate:
            self.warm(candidates[0]['id'], now)
            recalled['moment'] = copy.deepcopy(self.get(candidates[0]['id']))
        return {**result, **recalled}

    def candidate(self, slot, score, now):
        trace = self.traces[slot]
        fresh = math.exp(-max(0., now - trace['acquired_at']) / 300.)
        heat = 0. if trace['last_recalled_at'] is None else math.exp(-(now - trace['last_recalled_at']) / 120.)
        impact = self.impact(trace, now, slot)
        return {'id': trace['id'], 'score': score, 'freshness': fresh,
                'importance': trace['importance'], 'reactivation': heat, 'experienced_impact': impact,
                'priority': score + .08 * (fresh + trace['importance'] + heat + impact),
                'acquired_at': trace['acquired_at'], 'known': trace['known'].copy()}

    def recall_regions(self, cue, regions, now, *, exclude=None):
        scalar(now, self.clock, 1e12)
        if not isinstance(cue, NativeObservation) or cue.modality != 'image':
            raise ValueError('Visual recall requires an image cue.')
        cue.validate()
        validate_regions(regions, cue.sample_sha256)
        ranked = match(self.regions, regions, exclude)
        count = sum(score >= MIN_SIMILARITY for _, score in ranked)
        if not count:
            return {'entries': [], 'candidate_count': 0, 'reason': 'no_supported_region'}
        if len(ranked) > 1 and ranked[0][1] - ranked[1][1] < MIN_GAP:
            return {'entries': [], 'candidate_count': count, 'reason': 'ambiguous_regions'}
        index, score = ranked[0]
        slot = self.slot(index)
        trace = self.traces[slot]
        source = trace['sources']['image']
        # A crop selects a moment. The original learned scene key reads the
        # episode bank, where the image is bound to the other attended senses.
        scene = F.normalize(self.routes[slot, MODALITIES.index('image')].float(), dim=0)
        key = NativeObservation('image', scene, trace['acquired_at'], source['sequence'],
                                source['sha256'], origin=source['origin'])
        recalled = self.read_candidate(index, [key])
        entries = [{'candidate': self.candidate(slot, score, now), **recalled}] if recalled['supported'] else []
        return {'entries': entries, 'candidate_count': count, 'reason': recalled['reason']}

    def warm(self, index, now):
        scalar(now, self.clock, 1e12)
        trace = self.get(index)
        if trace is None:
            raise ValueError('Cannot reactivate a retired native moment.')
        trace['last_recalled_at'], trace['recalls'] = now, min(1000000, trace['recalls'] + 1)
        self.clock = now

    def read_candidate(self, index, cues, targets=None):
        # Routing scores are addresses. The recalled content still comes from
        # the episode's learned factors, including when several addresses match.
        trace = self.get(index)
        result = {'supported': False, 'representations': None}
        if trace is None:
            return {**result, 'reason': 'retired_moment'}
        targets = [name for slot, name in enumerate(MODALITIES) if trace['known'][slot]] if targets is None else targets
        if any(not trace['known'][MODALITIES.index(target)] for target in targets):
            return {**result, 'reason': 'unobserved_target'}
        bank = self.bank(index)
        if any(bank.variance(cue_key(cue)) > 25. for cue in cues):
            return {**result, 'reason': 'outside_associative_coverage'}
        values = torch.stack([bank.read(cue_key(cue)) for cue in cues]).mean(0).reshape(3, DIMENSION)
        if any(values[MODALITIES.index(target)].norm() < .1 for target in targets):
            return {**result, 'reason': 'unlearned_weights'}
        outputs = {target: F.normalize(values[MODALITIES.index(target)].float(), dim=0) for target in targets}
        return {**result, 'supported': True, 'reason': 'supported', 'representations': outputs,
                'moment': copy.deepcopy(trace)}

    def related(self, cues, now, *, limit=2, read_limit=4, exclude=None, reactivate=False,
                preference=None, contexts=None, context=None):
        if type(limit) is not int or not 1 <= limit <= 4 or type(read_limit) is not int or not limit <= read_limit <= 8 or type(reactivate) is not bool:
            raise ValueError('Invalid bounded native reactivation budget.')
        if exclude is not None and (type(exclude) is not int or not 0 <= exclude < self.next_id):
            raise ValueError('Invalid excluded native moment.')
        matched = self.recall(cues, now, reactivate=False, candidates_only=True)['candidates']
        candidates = [item for item in matched if item['id'] != exclude]
        if preference is not None:
            from .native_recall_preference import RecallPreference
            from .native_recall_context import RecallContexts
            if not isinstance(preference, RecallPreference) or not isinstance(contexts, RecallContexts):
                raise ValueError('Contextual recall requires its learned policy and context memory.')
            candidates = preference.rank(candidates, contexts, context)
        entries, skipped = [], []
        for candidate in candidates[:read_limit]:
            recalled = self.read_candidate(candidate['id'], cues)
            if not recalled['supported']:
                skipped.append({'id': candidate['id'], 'reason': recalled['reason']})
                continue
            entries.append({'candidate': copy.deepcopy(candidate), **recalled})
            if len(entries) == limit:
                break
        if reactivate:
            for entry in entries:
                self.warm(entry['candidate']['id'], now)
        return {'kind': 'related_sensory_recollections', 'entries': entries, 'skipped': skipped,
                'candidate_count': len(candidates), 'read_limit': read_limit,
                'confidence_is_calibrated': False, 'autobiographical_write': False}

    def snapshot(self, pages=None):
        state = {'format': 5 if pages is None else 6, 'representation': REPRESENTATION, 'capacity': self.capacity, 'hot_limit': self.hot_limit,
                'clock': self.clock, 'pre_archive_observations': self.pre_archive_observations,
                'next_id': self.next_id, 'total_observations': self.total_observations,
                'values': self.values.snapshot(),
                'routes': self.routes.clone(), 'traces': copy.deepcopy(self.traces)}
        if self.regions:
            state.update(format=7 if pages is None else 8, regions=copy.deepcopy(self.regions))
        if self.pronunciations:
            state.update(format=9 if pages is None else 10, regions=copy.deepcopy(self.regions),
                         pronunciations=copy.deepcopy(self.pronunciations))
        if pages is not None:
            from .native_page_store import validate_references
            validate_references(pages)
            return {**state, 'pages': copy.deepcopy(pages)}
        raw = self.connection.serialize()
        if len(raw) > MAX_ARCHIVE:
            raise ValueError("Native archive checkpoint exceeds its budget.")
        return {**state, 'archive': torch.frombuffer(bytearray(raw), dtype=torch.uint8).clone()}

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.connection.close()
        if self.path.resolve().parent != self.folder.resolve():
            raise ValueError("Native archive path changed its owner.")
        self.path.unlink(missing_ok=True)

    def __del__(self):
        if not getattr(self, 'closed', True):
            try:
                self.close()
            except (OSError, sqlite3.Error, ValueError):
                pass


def restore(payload, now):
    fields = {'format', 'representation', 'capacity', 'hot_limit', 'clock', 'pre_archive_observations', 'routes', 'traces'}
    version = payload.get('format') if isinstance(payload, dict) else None
    fields.update(('pages', 'page_source') if version in PAGED_FORMATS else ('archive',))
    if version in (3, 4, *VALUE_FORMATS):
        fields.update(('next_id', 'total_observations'))
    if version in VALUE_FORMATS:
        fields.add('values')
    if version in REGION_FORMATS:
        fields.add('regions')
    if version in PRONUNCIATION_FORMATS:
        fields.add('pronunciations')
    if not isinstance(payload, dict) or set(payload) != fields or type(version) is not int or version not in range(1, 11) or payload['representation'] != REPRESENTATION:
        raise ValueError("Invalid native moment checkpoint.")
    result = NativeMoments(payload['capacity'], payload['hot_limit'])
    try:
        scalar(payload['clock'], 0, now)
        if type(payload['pre_archive_observations']) is not int or not 0 <= payload['pre_archive_observations'] <= 6000006:
            raise ValueError("Invalid native legacy observation count.")
        routes = payload['routes']
        if not isinstance(routes, torch.Tensor) or routes.device.type != 'cpu' or routes.dtype != torch.float64 or routes.shape != result.routes.shape or not torch.isfinite(routes).all():
            raise ValueError("Invalid native routing weights.")
        traces = copy.deepcopy(payload['traces'])
        if not isinstance(traces, list) or len(traces) > result.capacity:
            raise ValueError("Invalid native moment trace count.")
        next_id = payload.get('next_id', len(traces))
        total = payload.get('total_observations')
        if type(next_id) is not int or not len(traces) <= next_id <= MAX_MOMENT_ID or (next_id and len(traces) != min(next_id, result.capacity)):
            raise ValueError('Invalid native lifetime counts.')
        previous = {}
        previous_id = -1
        for index, trace in enumerate(traces):
            expected = {'id', 'acquired_at', 'received_at', 'known', 'importance', 'last_recalled_at', 'recalls', 'sources', 'source_context'}
            if version in VALUE_FORMATS:
                expected.add('impact')
            if not isinstance(trace, dict) or set(trace) != expected or type(trace['id']) is not int or not previous_id < trace['id'] < next_id or (payload['format'] in (1, 2) and trace['id'] != index) or not isinstance(trace['known'], list) or len(trace['known']) != 3 or any(type(item) is not bool for item in trace['known']) or not any(trace['known']):
                raise ValueError("Invalid native moment trace identity/mask.")
            previous_id = trace['id']
            if payload['format'] in (1, 2, 3, 4):
                trace['impact'] = None
            validate_context(trace['source_context'])
            scalar(trace['acquired_at'], 0, payload['clock'])
            scalar(trace['received_at'], trace['acquired_at'], payload['clock'])
            scalar(trace['importance'], 0, 1.)
            if type(trace['recalls']) is not int or not 0 <= trace['recalls'] <= 1000000 or (trace['last_recalled_at'] is None) != (trace['recalls'] == 0):
                raise ValueError("Invalid native reactivation count.")
            if trace['last_recalled_at'] is not None:
                scalar(trace['last_recalled_at'], trace['received_at'], payload['clock'])
            impact = trace['impact']
            if impact is not None:
                from .native_attention import ACTIONS
                import re
                if not isinstance(impact, dict) or set(impact) != {'id', 'action', 'origin', 'acquired_at', 'sha256', 'received_at'} or type(impact['id']) is not int or not 1 <= impact['id'] < 1000000 or impact['action'] not in ACTIONS or impact['action'] == 'quiet' or impact['origin'] not in ('person', 'environment') or not isinstance(impact['sha256'], str) or re.fullmatch(r'[0-9a-f]{64}', impact['sha256']) is None:
                    raise ValueError('Invalid episode consequence source.')
                scalar(impact['received_at'], trace['received_at'], payload['clock'])
                scalar(impact['acquired_at'], trace['received_at'], impact['received_at'])
                scalar(impact['received_at'], impact['acquired_at'], payload['clock'])
            sources = trace['sources']
            known = {name for slot, name in enumerate(MODALITIES) if trace['known'][slot]}
            if not isinstance(sources, dict) or set(sources) != known:
                raise ValueError("Native sources disagree with observation mask.")
            for slot, name in enumerate(MODALITIES):
                weight = routes[index, slot]
                if not trace['known'][slot]:
                    if weight.count_nonzero():
                        raise ValueError("Unobserved native modality has a route.")
                    continue
                if abs(float(weight.norm()) - 1000. / 1000.1) > 1e-5:
                    raise ValueError("Invalid learned native address weight.")
                source = sources[name]
                if not isinstance(source, dict) or set(source) != {'origin', 'sequence', 'sha256'} or source['origin'] not in ('person', 'environment'):
                    raise ValueError("Invalid native moment source.")
                prototype = F.normalize(weight.float(), dim=0)
                NativeObservation(name, prototype, trace['acquired_at'], source['sequence'], source['sha256'], origin=source['origin']).validate()
                key = name + ':' + source['origin']
                if source['sequence'] <= previous.get(key, -1):
                    raise ValueError("Native moment repeats an old sensory sequence.")
                previous[key] = source['sequence']
        if routes[len(traces):].count_nonzero():
            raise ValueError("Unused native routing slots contain hidden state.")
        retained_observations = sum(sum(trace['known']) for trace in traces)
        total = retained_observations if payload['format'] in (1, 2) else total
        if type(total) is not int or not next_id <= total <= 3 * next_id or total < retained_observations:
            raise ValueError('Native lifetime count lost retained observations.')
        if version in REGION_FORMATS:
            saved = payload['regions']
            minimum = 0 if version in PRONUNCIATION_FORMATS else 1
            if not isinstance(saved, dict) or not minimum <= len(saved) <= len(traces):
                raise ValueError('Invalid visual region archive size.')
            images = {trace['id']: trace['sources']['image']['sha256'] for trace in traces if 'image' in trace['sources']}
            for index, record in saved.items():
                if type(index) is not int or index not in images:
                    raise ValueError('A retained visual region lost its episode.')
                validate_regions(record, images[index])
            result.regions = copy.deepcopy(saved)
        if version in PRONUNCIATION_FORMATS:
            from .native_pronunciation import restore_examples
            result.pronunciations = restore_examples(payload['pronunciations'], traces)
        if version in VALUE_FORMATS:
            from .native_impact import restore as restore_values
            result.values = restore_values(payload['values'], result.capacity, traces)
        if version in PAGED_FORMATS:
            from .native_page_store import NativePageSource
            source = payload['page_source']
            if not isinstance(source, NativePageSource):
                raise ValueError('External native checkpoint requires a verified page reader.')
            if not isinstance(payload['pages'], list) or len(payload['pages']) != len(traces):
                raise ValueError('Native page references lost their moments.')
            with result.connection:
                for index, raw, digest in source.rows(payload['pages']):
                    result.connection.execute('INSERT INTO moments VALUES (?,?,?)', (traces[index]['id'], raw, digest))
                if result.connection.execute('PRAGMA page_count').fetchone()[0] * result.connection.execute('PRAGMA page_size').fetchone()[0] > MAX_ARCHIVE:
                    raise ValueError('Restored native pages exceed the SQLite archive budget.')
        else:
            value = payload['archive']
            if not isinstance(value, torch.Tensor) or value.device.type != 'cpu' or value.dtype != torch.uint8 or value.ndim != 1 or not 1 <= value.numel() <= MAX_ARCHIVE:
                raise ValueError("Invalid native archive bytes.")
            result.connection.close()
            result.path.write_bytes(value.numpy().tobytes())
            result.connection = sqlite3.connect(result.path)
        objects = result.connection.execute("SELECT name,type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
        if objects != [('moments', 'table')] or result.connection.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError("Invalid native archive schema/integrity.")
        rows = result.connection.execute('SELECT id,bank,digest FROM moments ORDER BY id')
        count = 0
        for moment, raw, digest in rows:
            if count >= len(traces) or moment != traces[count]['id'] or len(raw) > 50000 or hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError("Invalid native archive page identity/digest.")
            bank = restore_weights(torch.load(io.BytesIO(raw), weights_only=True, map_location='cpu'))
            index = count
            trace = traces[index]
            if bank.writes != sum(trace['known']):
                raise ValueError("Native page writes disagree with observed modalities.")
            for slot, name in enumerate(MODALITIES):
                if not trace['known'][slot]:
                    continue
                prototype = F.normalize(routes[index, slot].float(), dim=0)
                cue = NativeObservation(name, prototype, trace['acquired_at'], 0, '0' * 64)
                recalled = bank.read(cue_key(cue)).reshape(3, DIMENSION)
                if bank.variance(cue_key(cue)) > .2:
                    raise ValueError("Native page lost its learned input coverage.")
                for target, present in enumerate(trace['known']):
                    if not present:
                        if recalled[target].abs().max() > 1e-8:
                            raise ValueError("Native page asserts an unobserved modality.")
                    elif recalled[target].norm() < .9 or float(F.normalize(recalled[target], dim=0) @ F.normalize(routes[index, target], dim=0)) < .999:
                        raise ValueError("Native page disagrees with its learned address.")
            count += 1
        if count != len(traces):
            raise ValueError("Native archive row count changed.")
        result.routes = routes.clone()
        result.traces = copy.deepcopy(traces)
        result.clock = payload['clock']
        result.pre_archive_observations = payload['pre_archive_observations']
        result.next_id, result.total_observations = next_id, total
        return result
    except BaseException:
        if 'rows' in locals():
            rows.close()
        result.close()
        raise


def validate_context(value):
    if value is None:
        return
    import re
    expected = {'stream_id', 'source_sequence', 'captured_wall', 'received_wall'}
    if not isinstance(value, dict) or set(value) != expected or not isinstance(value['stream_id'], str) or re.fullmatch(r'[0-9a-f]{32}', value['stream_id']) is None or type(value['source_sequence']) is not int or not 0 <= value['source_sequence'] < 1000000:
        raise ValueError("Invalid native moment external source context.")
    scalar(value['captured_wall'], 0, 1e12)
    scalar(value['received_wall'], value['captured_wall'], value['captured_wall'] + 3600.)


