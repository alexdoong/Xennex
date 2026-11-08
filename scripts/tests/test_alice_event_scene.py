"""Same participant with several neural event associations; no supplied event IDs."""
from __future__ import annotations
import copy
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.alice_memory.episodic_experiment import create as create_perception, packets as single_packets
from scripts.alice_memory.experience_signals import samples
from scripts.alice_memory.process_metrics import Budget
from scripts.alice_memory.scene_binding import EventBinding, event_data, event_source, evaluate, train
from scripts.alice_memory.scene_experiment import drive, query
from scripts.alice_memory.event_scene_experiment import create
from scripts.alice_memory.scene_memory import ConcurrentEventSession, load, restore, save
from scripts.alice_memory.paged_memory import PagedMemory
from scripts.alice_memory.scene_signals import packets, scene


class SameParticipantEvents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base, _ = create_perception(17, Budget(100000, 120))
        torch.set_num_threads(1)
        cls.binding = EventBinding()
        train(cls.binding, event_data(cls.base.perception, 95117, 768), 96117, steps=1800)
        folder = ROOT / 'bin/AliceEventSceneTests'
        folder.mkdir(parents=True, exist_ok=True)
        cls.directory = tempfile.TemporaryDirectory(dir=folder)
        cls.folder = Path(cls.directory.name)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def setUp(self):
        self.agent = create(self.base.perception, self.base.boundary, self.binding)
        self.rng = random.Random(97117)
        self.values = ((0, 0, 3, 0), (2, 1, 3, 0))

    def frame(self, values=None, masks=((True,) * 4, (True,) * 4)):
        return drive(self.agent, values or self.values, self.rng, masks)

    def paged(self, hot=1):
        memory = PagedMemory(64, hot)
        self.addCleanup(memory.close)
        self.agent.base.memory = memory
        self.agent = ConcurrentEventSession(self.agent.base, self.binding, event_source(self.base.perception))
        return memory

    def test_simultaneous_events_continue_from_cold_pages_and_match_resident_weights(self):
        resident = create(self.base.perception, self.base.boundary, self.binding)
        memory = self.paged()
        image, audio = scene(self.values, self.rng)
        for sequence in range(6):
            observations = packets(image, audio, (sequence + 1) * .1, sequence * 2)
            self.assertEqual(self.agent.step(observations, .1), resident.step(observations, .1))
            self.assertLessEqual(len(memory.cache), 1)
        self.assertEqual(memory.count, 2)
        for index in range(2):
            self.assertEqual(memory.traces[index], resident.memory.traces[index])
            self.assertTrue(all(torch.equal(value, memory.block(index).state_dict()[name])
                                for name, value in resident.memory.blocks[index].state_dict().items()))
        self.assertGreater(memory.loads, 0)

    def test_second_event_storage_failure_rolls_back_the_whole_frame_and_retry(self):
        for first_frame in (True, False):
            self.agent = create(self.base.perception, self.base.boundary, self.binding)
            memory = self.paged()
            if not first_frame:
                self.frame()
            before = copy.deepcopy(self.agent.snapshot())
            rows = memory.connection.execute('SELECT * FROM episodes ORDER BY id').fetchall()
            persist = memory.persist
            target = 1  # First event 0 may have already committed to the savepoint.
            def fail_second(index):
                if index == target:
                    raise OSError('second event failure')
                return persist(index)
            with patch.object(memory, 'persist', side_effect=fail_second):
                with self.assertRaisesRegex(OSError, 'second event'):
                    self.frame()
            self.assertEqual(self.agent.clock, before['base']['session']['clock'])
            self.assertEqual(self.agent.base.snapshot()['last_sequence'], before['base']['session']['last_sequence'])
            self.assertEqual(memory.metadata(), before['base']['metadata'])
            self.assertEqual(memory.connection.execute('SELECT * FROM episodes ORDER BY id').fetchall(), rows)
            self.assertEqual(len(self.agent.tracks), len(before['tracks']))
            for track, expected in zip(self.agent.tracks, before['tracks']):
                self.assertEqual((track['last_seen'], track['episode']), (expected['last_seen'], expected['episode']))
                self.assertTrue(torch.equal(track['previous'], expected['previous']))
            self.frame()
            self.assertEqual(memory.count, 2)

    def test_cold_scene_revision_preserves_initial_other_event_and_past_activity(self):
        self.paged()
        self.test_appraisal_revision_of_one_activity_preserves_initial_and_other_activity()

    def test_resident_second_event_failure_also_restores_first_event(self):
        self.frame()
        before = copy.deepcopy(self.agent.snapshot())
        observe = self.agent.memory.observe_at
        def fail_second(value, now, episode):
            if episode == 1:
                raise OSError('second event failure')
            return observe(value, now, episode)
        with patch.object(self.agent.memory, 'observe_at', side_effect=fail_second):
            with self.assertRaises(OSError):
                self.frame()
        after = self.agent.snapshot()
        self.assertEqual(after['base']['metadata'], before['base']['metadata'])
        self.assertTrue(all(torch.equal(value, after['base']['memory'][name]) for name, value in before['base']['memory'].items()))
        self.assertEqual(self.agent.clock, .1)

    def test_invalid_paged_track_checkpoint_closes_new_archive_and_preserves_rng(self):
        self.paged()
        self.frame()
        state = self.agent.snapshot()
        state['tracks'][0]['previous'][:4].zero_()
        original = set((ROOT / 'bin/AlicePages').glob('*.sqlite'))
        rng = torch.get_rng_state().clone()
        with self.assertRaisesRegex(ValueError, 'anchors'):
            restore(state)
        self.assertEqual(set((ROOT / 'bin/AlicePages').glob('*.sqlite')), original)
        self.assertTrue(torch.equal(rng, torch.get_rng_state()))

    def test_paged_wrapper_retains_archive_size_admission_and_resident_limit(self):
        from scripts.alice_memory.checkpoint_io import read_checkpoint
        path = self.folder / 'bounded.pt'
        save(path, self.agent)
        with self.assertRaisesRegex(ValueError, 'Legacy'):
            read_checkpoint(path, legacy_limit=100)
        self.paged()
        self.frame()
        save(path, self.agent)
        state = read_checkpoint(path, legacy_limit=100)
        self.assertEqual(state['base']['format'], 24)

    def test_paged_checkpoint_resumes_without_original_database_in_new_process(self):
        memory = self.paged()
        self.frame()
        folder = self.folder / 'paged-fresh'
        folder.mkdir()
        save(folder / 'state.pt', self.agent)
        image, audio = scene(tuple(reversed(self.values)), self.rng)
        torch.save({'image': image, 'audio': audio}, folder / 'next.pt')
        expected = self.agent.step(packets(image, audio, .2, 2), .1)
        expected_weights = [copy.deepcopy(memory.block(index).state_dict()) for index in range(2)]
        memory.close()
        self.assertFalse(memory.path.exists())
        script = """import json,sys,torch
from pathlib import Path
from scripts.alice_memory.scene_memory import load
from scripts.alice_memory.scene_signals import packets
torch.set_num_threads(1)
p=Path(sys.argv[1]);a=load(p/'state.pt');raw=torch.load(p/'next.pt',weights_only=True)
r=a.step(packets(raw['image'],raw['audio'],a.clock+.1,a.base.steps*2),.1)
torch.save([a.memory.block(i).state_dict() for i in range(2)],p/'weights.pt')
a.memory.close();print(json.dumps(r))
"""
        result = subprocess.run([sys.executable, '-c', script, str(folder)], cwd=ROOT,
                                capture_output=True, text=True, timeout=20,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), expected)
        saved = torch.load(folder / 'weights.pt', weights_only=True)
        for actual, reference in zip(saved, expected_weights):
            self.assertTrue(all(torch.equal(value, actual[name]) for name, value in reference.items()))

    def test_same_person_different_activities_keep_two_episodes_when_positions_swap(self):
        self.frame()
        for _ in range(4):
            result = self.frame(tuple(reversed(self.values)))
            self.assertEqual({item['region']: item['track'] for item in result['events']}, {1: 0, 0: 1})
            self.assertEqual(len(self.agent.memory.blocks), 2)
        for value, appraisal in zip(self.values, ('agradavel', 'neutra')):
            answer = query(self.agent, value, self.rng, (.1, self.agent.clock))
            self.assertEqual(answer['recall']['autor'], 'usuario')
            self.assertEqual(answer['recall']['impressao'], appraisal)

    def test_same_person_same_activity_in_different_contexts_remains_distinct(self):
        self.values = ((0, 0, 3, 0), (0, 1, 3, 1))
        for _ in range(3):
            self.frame()
        self.assertEqual(len(self.agent.memory.blocks), 2)
        for value, appraisal in zip(self.values, ('agradavel', 'neutra')):
            answer = query(self.agent, value, self.rng, (.1, self.agent.clock))
            self.assertEqual(answer['recall']['impressao'], appraisal)

    def test_different_people_same_activity_context_need_participant_cue_for_recall(self):
        self.values = ((0, 0, 0, 0), (0, 1, 1, 0))
        self.frame()
        self.frame(tuple(reversed(self.values)))
        self.assertEqual(len(self.agent.memory.blocks), 2)
        self.assertTrue(query(self.agent, self.values[0], self.rng, (.1, self.agent.clock))['ambiguous'])
        for value, appraisal in zip(self.values, ('agradavel', 'neutra')):
            image, audio = samples(value, self.rng, (True, False, True, True))
            answer = self.agent.base.query(single_packets(image, audio, self.agent.clock, 0), window=(.1, self.agent.clock))
            self.assertEqual(answer['recall']['impressao'], appraisal)

    def test_appraisal_revision_of_one_activity_preserves_initial_and_other_activity(self):
        for _ in range(3):
            self.frame()
        window = (.1, self.agent.clock)
        image, audio = samples(self.values[0], self.rng, (True, False, False, True))
        evidence_image, evidence_audio = samples((0, 2, 3, 0), self.rng, (False, True, False, False))
        result = self.agent.base.revise(single_packets(image, audio, self.agent.clock, 0),
                                       single_packets(evidence_image, evidence_audio, self.agent.clock, 2), 1, 0., window)
        self.assertTrue(result['revised'])
        self.assertEqual(query(self.agent, self.values[0], self.rng, window)['recall']['impressao'], 'barulhenta')
        self.assertEqual(query(self.agent, self.values[0], self.rng, window, 'initial')['recall']['impressao'], 'agradavel')
        self.assertEqual(query(self.agent, self.values[1], self.rng, window)['recall']['impressao'], 'neutra')
        self.frame(((1, 0, 3, 0), self.values[1]))
        self.assertEqual(len(self.agent.memory.blocks), 3)
        self.assertEqual(query(self.agent, self.values[0], self.rng, window)['recall']['impressao'], 'barulhenta')

    def test_missing_event_anchor_and_identical_events_abstain(self):
        self.frame()
        counts = [trace.observations for trace in self.agent.memory.traces]
        result = self.frame(masks=((False, True, True, True), (True,) * 4))
        self.assertEqual(result['unassigned_regions'], [0])
        self.assertEqual(self.agent.memory.traces[0].observations, counts[0])
        result = self.frame((self.values[0], self.values[0]))
        self.assertEqual(result['events'], [])
        self.assertEqual(result['ambiguous_regions'], [0, 1])
        self.assertEqual(len(self.agent.memory.blocks), 2)

    def test_activity_conflict_between_modalities_is_not_an_external_event(self):
        self.frame()
        state = {name: value.clone() for name, value in self.agent.memory.state_dict().items()}
        image, audio = scene(self.values, self.rng)
        result = self.agent.step(packets(image, audio.flip(0), .2, 2), .1)
        self.assertEqual(result['events'], [])
        for name, value in state.items():
            self.assertTrue(torch.equal(value, self.agent.memory.state_dict()[name]))

    def test_neural_weights_cause_correspondence_and_factual_recall(self):
        score = evaluate(self.binding, event_data(self.base.perception, 98117, 256, evaluation=True))
        self.assertGreaterEqual(score['match_recall'], .98)
        self.assertLessEqual(score['false_match_rate'], .02)
        zero = copy.deepcopy(self.binding)
        with torch.no_grad():
            for weight in zero.parameters():
                weight.zero_()
        ablated = create(self.base.perception, self.base.boundary, zero)
        drive(ablated, self.values, self.rng)
        drive(ablated, tuple(reversed(self.values)), self.rng)
        self.assertEqual(len(ablated.memory.blocks), 4)
        self.frame()
        with torch.no_grad():
            for block in self.agent.memory.blocks:
                for bank in block.banks:
                    bank.weights.zero_()
        self.assertIsNone(query(self.agent, self.values[0], self.rng, (.1, self.agent.clock))['recall'])

    def test_overflow_rejects_both_events_before_writes_or_clock_change(self):
        self.agent = create(self.base.perception, self.base.boundary, self.binding, capacity=2)
        self.frame()
        state = copy.deepcopy(self.agent.snapshot())
        with self.assertRaisesRegex(ValueError, 'capacity'):
            self.frame(((1, 0, 3, 0), (3, 1, 3, 0)))
        after = self.agent.snapshot()
        self.assertEqual(state['base']['session']['clock'], after['base']['session']['clock'])
        self.assertEqual(state['base']['metadata'], after['base']['metadata'])
        self.assertEqual(state['base']['session']['last_sequence'], after['base']['session']['last_sequence'])
        for name, value in state['base']['memory'].items():
            self.assertTrue(torch.equal(value, after['base']['memory'][name]))

    def test_checkpoint_format_source_and_anchor_validation_preserve_rng_on_failure(self):
        self.frame()
        state = self.agent.snapshot()
        self.assertEqual(state['format'], 34)
        failures = []
        value = copy.deepcopy(state); value['representation'] = 'simultaneous-localized-events-v1'; failures.append(value)
        value = copy.deepcopy(state); value['binding_source'] = {**event_source(self.base.perception), 'representation': 'localized-two-source-concepts-v1'}; failures.append(value)
        value = copy.deepcopy(state); value['tracks'][0]['previous'][:4].zero_(); failures.append(value)
        value = copy.deepcopy(state); value['binding']['layers.0.weight'] = value['binding']['layers.0.weight'].double(); failures.append(value)
        rng = torch.get_rng_state().clone()
        for value in failures:
            with self.assertRaises((ValueError, RuntimeError)):
                restore(value)
            self.assertTrue(torch.equal(rng, torch.get_rng_state()))
        restored = restore(state)
        state['tracks'][0]['previous'].zero_()
        self.assertGreater(float(restored.tracks[0]['previous'].sum()), 0)

    def test_fresh_process_restores_same_person_events_without_examples(self):
        self.frame()
        folder = self.folder / 'fresh'
        folder.mkdir()
        save(folder / 'state.pt', self.agent)
        image, audio = scene(tuple(reversed(self.values)), self.rng)
        torch.save({'image': image, 'audio': audio}, folder / 'next.pt')
        script = """import json,sys,torch
from pathlib import Path
from scripts.alice_memory.scene_memory import load,save
from scripts.alice_memory.scene_signals import packets
torch.set_num_threads(1)
p=Path(sys.argv[1]);a=load(p/'state.pt');raw=torch.load(p/'next.pt',weights_only=True)
r=a.step(packets(raw['image'],raw['audio'],a.clock+.1,a.base.steps*2),.1)
save(p/'after.pt',a);print(json.dumps(r))
"""
        result = subprocess.run([sys.executable, '-c', script, str(folder)], cwd=ROOT,
                                capture_output=True, text=True, timeout=20,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = self.agent.step(packets(image, audio, self.agent.clock + .1, self.agent.base.steps * 2), .1)
        self.assertEqual(json.loads(result.stdout), expected)
        saved = torch.load(folder / 'after.pt', weights_only=True)
        for name, value in saved['base']['memory'].items():
            self.assertTrue(torch.equal(value, self.agent.memory.state_dict()[name]))


if __name__ == '__main__':
    unittest.main()

