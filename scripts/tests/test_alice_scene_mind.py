"""One temporal/language mind retains parallel localized neural experiences."""
from __future__ import annotations

import copy
import random
import subprocess
import sys
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.alice_memory.checkpoint_io import read_checkpoint
from scripts.alice_memory.consolidating_mind import ConsolidatingMind
from scripts.alice_memory.continuous_mind import ContinuousMind
from scripts.alice_memory.episodic_experiment import create, packets as single_packets
from scripts.alice_memory.episodic_session import EpisodicSession
from scripts.alice_memory.experience_signals import samples
from scripts.alice_memory.grounded_mind import GroundedMind, WrittenName, load, restore, save
from scripts.alice_memory.memory_actor import MemoryActor, RecallPolicy, train as train_policy
from scripts.alice_memory.neural_language import NeuralLanguageCoordinator, load as load_coordinator, save as save_coordinator
from scripts.alice_memory.neural_tasks import TaskModel
from scripts.alice_memory.paged_memory import PagedMemory
from scripts.alice_memory.process_metrics import Budget
from scripts.alice_memory.scene_binding import EventBinding, event_data, event_source, train
from scripts.alice_memory.scene_mind import SceneGroundedMind
from scripts.alice_memory.scene_signals import packets, scene
from scripts.alice_memory.temporal32 import Temporal32
from scripts.alice_memory.temporal_mind import TemporalMind
from scripts.alice_memory.continuous_experiment import load_scheduler
from scripts.alice_memory.runtime_snapshot import capture
from scripts.alice_memory.loop_checkpoint import atomic_write


class SceneMindTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)
        cls.base, _ = create(17, Budget(100000, 120))
        cls.policy = RecallPolicy()
        train_policy(cls.policy, 1017, Budget(100000, 120))
        cls.binding = EventBinding()
        train(cls.binding, event_data(cls.base.perception, 95117, 768), 96117, steps=1800)
        parent = ROOT / 'bin/AliceSceneMindTests'
        parent.mkdir(parents=True, exist_ok=True)
        cls.directory = tempfile.TemporaryDirectory(dir=parent)
        cls.folder = Path(cls.directory.name)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def setUp(self):
        memory = PagedMemory(64, 1)
        self.addCleanup(memory.close)
        base = EpisodicSession(self.base.perception, self.base.boundary, memory)
        continuous = ContinuousMind(MemoryActor(base, self.policy))
        grounded = GroundedMind(ConsolidatingMind(TemporalMind(continuous, Temporal32(), base.perception.state_dict()), forgetting=1.))
        self.agent = SceneGroundedMind(grounded, self.binding, event_source(base.perception))
        self.rng = random.Random(98117)
        self.values = ((0, 0, 3, 0), (2, 1, 3, 0))

    def frame(self, values=None, masks=((True,) * 4, (True,) * 4), elapsed=.1, focus=0):
        image, audio = scene(values or self.values, self.rng, masks)
        agent = self.agent
        inputs = packets(image, audio, agent.clock + elapsed, agent.scene.base.steps * 2)
        return agent.perceive(inputs, elapsed, focus)

    def test_detached_runtime_snapshot_restores_scene_through_scheduler_with_one_owner(self):
        self.frame()
        path = self.folder / "runtime-scene.pt"
        atomic_write(path, capture(self.agent))
        restored, mind, serializer = load_scheduler(path, self.folder / "runtime-workers")
        self.addCleanup(restored.scene.memory.close)
        self.assertIs(mind, restored.mind)
        self.assertIs(restored.scene.memory, restored.mind.actor.session.memory)
        self.assertEqual(restored.scene.memory.count, 2)
        self.assertEqual(self.agent.tick(.1), restored.tick(.1))

    def assert_tree_equal(self, left, right, path='root'):
        if isinstance(left, torch.Tensor):
            self.assertTrue(torch.equal(left, right), path)
            return
        if isinstance(left, dict):
            self.assertEqual(set(left), set(right))
            for name in left:
                self.assert_tree_equal(left[name], right[name], path + '.' + str(name))
            return
        if isinstance(left, (tuple, list)):
            self.assertEqual(len(left), len(right))
            for first, second in zip(left, right):
                self.assert_tree_equal(first, second, path + '[]')
            return
        self.assertEqual(left, right)

    def owned_restore(self, state):
        restored = restore(state)
        self.addCleanup(restored.scene.memory.close)
        return restored

    def test_frame_advances_one_shared_mind_once_and_keeps_background(self):
        result = self.frame()
        self.assertIs(self.agent.scene.base, self.agent.mind.actor.session)
        self.assertEqual(self.agent.scene.base.steps, 1)
        self.assertEqual((self.agent.clock, self.agent.temporal.clock, self.agent.scene.memory.clock), (.1, .1, .1))
        self.assertEqual(self.agent.temporal.observations, 1)
        self.assertEqual(len(result['events']), 2)
        self.assertEqual(self.agent.scene.memory.count, 2)
        self.assertEqual(result['consolidation']['sources'], [])
        self.assertEqual(self.agent.semantic.bank.writes.item(), 0)
        for event in result['events']:
            self.assertEqual(self.agent.scene.memory.traces[event['episode']].observations, 1)
        self.assertLessEqual(len(self.agent.scene.memory.cache), 1)

    def test_focus_switch_updates_present_without_forgetting_parallel_tracks(self):
        self.frame()
        first = self.agent.scene.base.joint.clone()
        result = self.frame(focus=1)
        self.assertFalse(torch.equal(first, self.agent.scene.base.joint))
        attended = self.agent.scene.current_regions[1]
        self.assertTrue(torch.equal(self.agent.scene.base.joint, attended['joint']))
        self.assertTrue(torch.equal(self.agent.scene.base.previous[0], attended['cue'].float()))
        self.assertEqual(result['attention_source'], 'explicit_region')
        self.assertEqual(self.agent.scene.memory.count, 2)
        self.assertEqual(self.agent.temporal.observations, 2)
        self.frame(tuple(reversed(self.values)), focus=0)
        self.assertEqual(self.agent.scene.memory.count, 2)
        self.assertEqual([track['episode'] for track in self.agent.scene.tracks], [0, 1])

    def test_missing_focus_fields_do_not_leak_from_an_earlier_scene(self):
        self.frame()
        result = self.frame(masks=((True, False, False, False), (True,) * 4))
        self.assertEqual(result['known'], [True, False, False, False])
        self.assertIsNone(result['episode'])
        self.assertEqual(len(result['events']), 1)
        self.assertEqual(self.agent.scene.memory.count, 2)
        self.assertEqual(self.agent.scene.base.previous[0, 4:].count_nonzero().item(), 0)
        self.assertIsNotNone(self.agent.context)

    def test_name_learning_attends_one_region_without_assigning_background_meaning(self):
        for index in range(8):
            self.frame(masks=((True, False, False, False), (True,) * 4))
            self.assertTrue(self.agent.teach_name(WrittenName('vimuq', self.agent.clock, index))['learned'])
        meaning = self.agent.words.lookup('vimuq')
        self.assertTrue(meaning['supported'])
        self.assertEqual((meaning['field'], meaning['category']), (0, 0))
        self.assertEqual(self.agent.scene.memory.count, 1)
        self.assertEqual(self.agent.temporal.observations, 8)
        self.assertEqual(self.agent.scene.memory.traces[0].observations, 8)

    def test_stale_absent_and_self_frames_do_not_repeat_temporal_input(self):
        image, audio = scene(self.values, self.rng)
        inputs = packets(image, audio, .1, 0)
        self.agent.perceive(inputs, .1)
        before = self.agent.scene.memory.count
        stale = self.agent.perceive(inputs, .1)
        self.assertEqual(stale['encoded'], 0)
        absent = [replace(item, acquired_at=.3, sequence=item.sequence + 2, present=False) for item in inputs]
        self.agent.perceive(absent, .1)
        own = [replace(item, acquired_at=.4, sequence=item.sequence + 4, origin='self', action_id=1) for item in inputs]
        self.agent.perceive(own, .1)
        self.assertEqual(self.agent.temporal.observations, 1)
        self.assertEqual(self.agent.scene.memory.count, before)
        self.assertAlmostEqual(self.agent.temporal.clock, .4)
        self.assertIsNone(self.agent.context)

    def test_second_page_failure_preserves_temporal_internal_and_lexical_state(self):
        self.frame(masks=((True, False, False, False), (True,) * 4))
        before = copy.deepcopy(self.agent.snapshot())
        internal = asdict(self.agent.mind.internal)
        regions = copy.deepcopy(self.agent.scene.current_regions)
        persist = self.agent.scene.memory.persist
        def fail_second(index):
            if index == 0:
                raise OSError('background page failure')
            return persist(index)
        with patch.object(self.agent.scene.memory, 'persist', side_effect=fail_second):
            with self.assertRaisesRegex(OSError, 'background'):
                self.frame(focus=1)
        self.assert_tree_equal(self.agent.snapshot(), before)
        self.assert_tree_equal(self.agent.scene.current_regions, regions)
        self.assertEqual(asdict(self.agent.mind.internal), internal)
        self.frame(focus=1)
        self.assertEqual(self.agent.scene.memory.count, 2)

    def test_gap_closes_each_track_without_consolidating_simultaneous_neighbor(self):
        self.frame()
        self.frame(elapsed=3.)
        self.assertEqual(self.agent.scene.memory.count, 4)
        self.assertTrue((self.agent.semantic.versions[:2] >= 0).all())
        self.assertTrue((self.agent.semantic.versions[2:4] == -1).all())
        result = self.agent.consolidate_current()
        self.assertEqual(result['sources'], [2, 3])

    def test_consolidation_budget_defers_without_losing_committed_scene(self):
        self.frame()
        self.agent.semantic.bank.writes.fill_(4096)
        before = self.agent.semantic.bank.weights.clone()
        result = self.frame(elapsed=3.)
        self.assertTrue(result['consolidation']['deferred'])
        self.assertEqual(result['consolidation']['reason'], 'semantic_update_budget')
        self.assertTrue(torch.equal(before, self.agent.semantic.bank.weights))
        self.assertEqual(self.agent.scene.memory.count, 4)
        self.assertEqual(self.agent.temporal.observations, 2)

    def test_checkpoint_restores_shared_state_and_continues_identically(self):
        self.frame(focus=1)
        state = self.agent.snapshot()
        restored = self.owned_restore(state)
        self.assertIs(restored.scene.base, restored.mind.actor.session)
        self.assertEqual(restored.focus_region, 1)
        image, audio = scene(tuple(reversed(self.values)), self.rng)
        inputs = packets(image, audio, .2, 2)
        self.assertEqual(restored.perceive(inputs, .1), self.agent.perceive(inputs, .1))
        self.assert_tree_equal(restored.snapshot(), self.agent.snapshot())

    def test_restored_checkpoint_does_not_alias_callers_tracks_or_context(self):
        self.frame(masks=((True, False, False, False), (True,) * 4))
        state = self.agent.snapshot()
        restored = self.owned_restore(state)
        expected = restored.scene.base.previous.clone()
        state['agent']['context']['latent'].zero_()
        state['scene']['tracks'][0]['previous'].zero_()
        self.assertTrue(torch.equal(restored.scene.base.previous, expected))
        self.assertGreater(restored.context['latent'].norm().item(), .99)
        self.assertGreater(restored.scene.tracks[0]['previous'].norm().item(), 0)

    def test_bad_track_or_binding_checkpoint_closes_archive_and_preserves_rng(self):
        self.frame()
        for fault in ('track', 'source', 'legacy_binding'):
            state = copy.deepcopy(self.agent.snapshot())
            if fault == 'track':
                state['scene']['tracks'][0]['episode'] = 999
            elif fault == 'source':
                state['scene']['binding_source'] = {}
            else:
                state['scene']['format'] = 33
            original = set((ROOT / 'bin/AlicePages').glob('*.sqlite'))
            rng = torch.get_rng_state().clone()
            with self.assertRaises(ValueError):
                restore(state)
            self.assertEqual(set((ROOT / 'bin/AlicePages').glob('*.sqlite')), original)
            self.assertTrue(torch.equal(rng, torch.get_rng_state()))

    def test_archive_size_admission_through_language_wrapper_chain(self):
        self.frame()
        path = self.folder / 'scene.pt'
        save(path, self.agent)
        state = read_checkpoint(path, legacy_limit=100)
        self.assertEqual(state['format'], 35)
        restored = load(path)
        self.addCleanup(restored.scene.memory.close)
        self.assertEqual(restored.scene.memory.count, 2)
        torch.save({'format': 31, 'agent': {'format': 30, 'agent': state}}, path)
        self.assertEqual(read_checkpoint(path, legacy_limit=100)['format'], 31)
        torch.save({'format': 35, 'agent': {'format': 29, 'agent': {'format': 23}}}, path)
        with self.assertRaisesRegex(ValueError, 'Legacy'):
            read_checkpoint(path, legacy_limit=100)

    def test_invalid_focus_rejected_before_any_clock_or_memory_change(self):
        before = self.agent.snapshot()
        for focus in (True, -1, 2, '0'):
            with self.assertRaises(ValueError):
                self.frame(focus=focus)
        self.assert_tree_equal(self.agent.snapshot(), before)

    def test_revision_and_idle_preserve_other_parallel_memory_and_current_perception(self):
        self.frame()
        session = self.agent.scene.base
        current = session.previous.clone()
        image, audio = samples(self.values[0], self.rng, (True, False, False, True))
        evidence_image, evidence_audio = samples((0, 2, 3, 0), self.rng, (False, True, False, False))
        revised = self.agent.revise(single_packets(image, audio, .1, 0), single_packets(evidence_image, evidence_audio, .1, 2), 1, 0., (.1, .1))
        self.assertTrue(revised['revised'])
        self.assertTrue(torch.equal(session.previous, current))
        self.assertEqual(session.memory.block(1).revisions.sum().item(), 0)
        observations = self.agent.temporal.observations
        self.agent.tick(.1)
        self.assertEqual(self.agent.temporal.observations, observations)
        self.assertEqual(session.memory.count, 2)
        self.assertEqual(session.clock, self.agent.temporal.clock)

    def test_grounded_question_uses_parallel_memory_without_new_perception(self):
        for field, word in ((0, 'vimuq'), (3, 'torbe')):
            masks = (tuple(index == field for index in range(4)), (True,) * 4)
            for _ in range(8):
                self.frame(masks=masks)
                sequence = self.agent.label_sequence.get('person', -1) + 1
                self.assertTrue(self.agent.teach_name(WrittenName(word, self.agent.clock, sequence))['learned'])
        self.frame(elapsed=3.)
        window = (self.agent.clock, self.agent.clock)
        queried = self.agent.query_names(['vimuq', 'torbe'], window=window)
        self.assertTrue(queried['grounding_supported'])
        self.assertEqual(queried['result']['episode'], self.agent.scene.tracks[-1]['episode'])
        self.assertTrue(self.agent.request_names(['vimuq', 'torbe'], 2, window)['queued'])
        count, observations = self.agent.scene.memory.count, self.agent.temporal.observations
        result = self.agent.tick(.1)
        self.assertEqual(result['action']['signal'], 3)
        self.assertEqual(self.agent.scene.memory.count, count)
        self.assertEqual(self.agent.temporal.observations, observations)

    def test_neural_language_pending_question_does_not_stop_scenes_and_resumes(self):
        class HeldWorker:
            def __init__(self, operation):
                self.closed = False
            def poll(self):
                return None
            def close(self):
                self.closed = True
        folder = self.folder / 'language'
        folder.mkdir(exist_ok=True)
        coordinator = NeuralLanguageCoordinator(self.agent, TaskModel(), 'http://127.0.0.1:11438',
                                                'fixture', folder, HeldWorker)
        self.addCleanup(coordinator.close)
        self.frame()
        identifier = coordinator.submit('Quem estava em "vimuq"?')
        coordinator.poll()
        self.assertIsNotNone(coordinator.worker)
        image, audio = scene(tuple(reversed(self.values)), self.rng)
        coordinator.perceive(packets(image, audio, .2, 2), .1, focus_region=1)
        coordinator.tick(.1)
        self.assertEqual(self.agent.temporal.observations, 2)
        self.assertEqual(self.agent.scene.memory.count, 2)
        path = folder / 'pending.pt'
        save_coordinator(path, coordinator)
        resumed = load_coordinator(path, folder, HeldWorker)
        self.addCleanup(resumed.close)
        self.addCleanup(resumed.agent.scene.memory.close)
        self.assertEqual(resumed.jobs[identifier]['status'], 'waiting_parse')
        self.assertIsInstance(resumed.agent, SceneGroundedMind)
        self.assertEqual(resumed.agent.focus_region, 1)
        self.assertIs(resumed.agent.scene.base, resumed.mind.actor.session)
        self.assert_tree_equal(resumed.agent.snapshot(), self.agent.snapshot())
        self.assert_tree_equal(resumed.tasks.snapshot(), coordinator.tasks.snapshot())
        resumed.tick(.1)
        self.assertEqual(resumed.agent.scene.memory.count, 2)

    def test_bad_language_queue_checkpoint_releases_shared_scene_archive(self):
        from scripts.alice_memory.grounded_mind import checkpoint_payload
        from scripts.alice_memory.language_coordinator import LanguageCoordinator, restore as restore_controller
        self.frame()
        folder = self.folder / 'invalid-language'
        coordinator = LanguageCoordinator(self.agent, 'http://127.0.0.1:11438', 'fixture', folder)
        self.addCleanup(coordinator.close)
        state = {'format': 30, 'agent': checkpoint_payload(self.agent),
                 'language': coordinator.snapshot(), 'torch_rng': torch.get_rng_state()}
        state['language']['source'] = 'invalid'
        original = set((ROOT / 'bin/AlicePages').glob('*.sqlite'))
        rng = torch.get_rng_state().clone()
        with self.assertRaisesRegex(ValueError, 'source'):
            restore_controller(state, folder)
        self.assertEqual(set((ROOT / 'bin/AlicePages').glob('*.sqlite')), original)
        self.assertTrue(torch.equal(rng, torch.get_rng_state()))

    def test_source_storage_failure_defers_whole_semantic_batch(self):
        self.frame()
        before = copy.deepcopy(self.agent.semantic.state_dict())
        consolidate = self.agent.semantic.consolidate
        def fail_second(memory, index, now):
            if index == 1:
                raise OSError('cold page unavailable')
            return consolidate(memory, index, now)
        with patch.object(self.agent.semantic, 'consolidate', side_effect=fail_second):
            result = self.frame(elapsed=3.)
        self.assertTrue(result['consolidation']['deferred'])
        self.assertEqual(result['consolidation']['reason'], 'source_storage_unavailable')
        self.assert_tree_equal(before, self.agent.semantic.state_dict())
        self.assertEqual(self.agent.scene.memory.count, 4)

    def test_neural_scene_batch_rolls_back_sampler_and_ledger_after_second_failure(self):
        from scripts.alice_memory.neural_semantic_memory import NeuralSemanticMemory
        self.agent.agent.semantic = NeuralSemanticMemory(self.agent.scene.memory)
        self.frame()
        before = self.agent.semantic.transaction_state()
        consolidate = self.agent.semantic.consolidate
        def fail_second(memory, episode, now):
            if episode == 1:
                raise OSError('neural cold page unavailable')
            return consolidate(memory, episode, now)
        with patch.object(self.agent.semantic, 'consolidate', side_effect=fail_second):
            result = self.frame(elapsed=3.)
        self.assertEqual(result['consolidation']['reason'], 'source_storage_unavailable')
        self.assert_tree_equal(self.agent.semantic.transaction_state(), before)
        self.assertEqual(self.agent.scene.memory.count, 4)
        self.assertEqual(self.agent.temporal.observations, 2)
        self.assertTrue(self.agent._consolidate([0, 1])['learned'])
        resumed = self.owned_restore(self.agent.snapshot())
        self.assertIs(resumed.semantic._source(), resumed.scene.memory)
        self.assertIs(resumed.scene.base, resumed.mind.actor.session)
        self.assert_tree_equal(resumed.semantic.snapshot(), self.agent.semantic.snapshot())

    def test_projected_backend_in_concurrent_scene_keeps_one_source_and_clock(self):
        from scripts.alice_memory.projected_semantic_memory import ProjectedSemanticMemory
        self.agent.agent.semantic = ProjectedSemanticMemory(self.agent.scene.memory)
        self.frame()
        self.assertTrue(self.agent.consolidate_current()['learned'])
        restored = self.owned_restore(self.agent.snapshot())
        self.assertIsInstance(restored.semantic, ProjectedSemanticMemory)
        self.assertIs(restored.semantic._source(), restored.scene.memory)
        self.assertEqual(restored.clock, restored.temporal.clock)
        self.assert_tree_equal(restored.semantic.snapshot(), self.agent.semantic.snapshot())

    def test_bad_neural_checkpoint_releases_archive_and_preserves_callers_rng(self):
        from scripts.alice_memory.neural_semantic_memory import NeuralSemanticMemory
        self.agent.agent.semantic = NeuralSemanticMemory(self.agent.scene.memory)
        self.frame()
        self.agent.consolidate_current()
        state = self.agent.snapshot()
        state['agent']['agent']['semantic']['ledger']['origins'][0, 0] ^= 1
        original = set((ROOT / 'bin/AlicePages').glob('*.sqlite'))
        rng = torch.get_rng_state().clone()
        with self.assertRaises(ValueError):
            restore(state)
        self.assertEqual(set((ROOT / 'bin/AlicePages').glob('*.sqlite')), original)
        self.assertTrue(torch.equal(rng, torch.get_rng_state()))

    def test_neural_checkpoint_with_pending_revision_resumes_in_fresh_process(self):
        # SGD bitwise continuation requires the same numerical/thread profile.
        torch.set_num_threads(1)
        from scripts.alice_memory.neural_semantic_memory import NeuralSemanticMemory
        self.agent.agent.semantic = NeuralSemanticMemory(self.agent.scene.memory)
        self.frame()
        self.agent.consolidate_current()
        memory = self.agent.scene.memory
        source = memory.blocks[0].addresses[1].flatten().clone()
        memory.revise(source, 2, torch.tensor([0., 1., 0., 0., 0.]), self.agent.clock)
        self.assertEqual(self.agent.semantic.pending_sources(), [0])
        checkpoint = self.folder / 'neural-pending.pt'
        expected = self.folder / 'neural-expected.pt'
        output = self.folder / 'neural-output.pt'
        save(checkpoint, self.agent)
        self.agent.consolidate_current()
        self.agent.tick(.1)
        save(expected, self.agent)
        memory.close()
        code = '''import sys, torch
from pathlib import Path
from scripts.alice_memory.grounded_mind import load, save
torch.set_num_threads(1)
agent = load(Path(sys.argv[1]))
assert agent.semantic.pending_sources() == [0]
assert agent.semantic._source() is agent.scene.memory
assert agent.scene.base is agent.mind.actor.session
agent.consolidate_current()
agent.tick(.1)
save(Path(sys.argv[2]), agent)
agent.scene.memory.close()
'''
        child = subprocess.run([sys.executable, '-c', code, str(checkpoint), str(output)],
                               cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assert_tree_equal(torch.load(output, weights_only=True), torch.load(expected, weights_only=True))

    def test_checkpoint_in_fresh_process_needs_no_original_sqlite(self):
        self.frame()
        checkpoint, stimulus, expected = (self.folder / name for name in ('fresh.pt', 'stimulus.pt', 'expected.pt'))
        save(checkpoint, self.agent)
        image, audio = scene(tuple(reversed(self.values)), self.rng)
        torch.save({'image': image, 'audio': audio}, stimulus)
        self.agent.perceive(packets(image, audio, .2, 2), .1, focus_region=1)
        save(expected, self.agent)
        self.agent.scene.memory.close()
        code = '''import sys, torch
from pathlib import Path
from scripts.alice_memory.grounded_mind import load, checkpoint_payload
from scripts.alice_memory.scene_signals import packets
torch.set_num_threads(1)
agent = load(Path(sys.argv[1]))
inputs = torch.load(sys.argv[2], weights_only=True)
agent.perceive(packets(inputs['image'], inputs['audio'], .2, 2), .1, focus_region=1)
torch.save(checkpoint_payload(agent), sys.argv[3])
agent.scene.memory.close()
'''
        output = self.folder / 'fresh-output.pt'
        child = subprocess.run([sys.executable, '-c', code, str(checkpoint), str(stimulus), str(output)],
                               cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assert_tree_equal(torch.load(output, weights_only=True), torch.load(expected, weights_only=True))


if __name__ == '__main__':
    unittest.main()
