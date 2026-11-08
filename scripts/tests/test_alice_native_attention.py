"""Attention choices change actual acquisition, not only later retrieval."""
import copy
import sys
import unittest
from pathlib import Path

import torch
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alice_memory.native_attention import NativeAttention, restore
from scripts.alice_memory.native_grounding import NativeGrounding, restore as restore_native
from scripts.alice_memory.native_sensor import NativeObservation
from scripts.alice_memory.grounded_mind import WrittenName
from scripts.alice_memory.importance import Consequence
import test_alice_native_stream as stream_tests
from scripts.alice_memory.conceptual_mind import restore as restore_core


def context(axis=None):
    return torch.zeros(128) if axis is None else F.one_hot(torch.tensor(axis), 128).float()


def packets(at, sequence):
    return [NativeObservation(name, context(axis), at, sequence, 'a' * 64)
            for name, axis in (('image', 0), ('audio', 3))]


class AttentionLearningContracts(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)

    def trained(self, preferred):
        policy = NativeAttention()
        policy.configure('learned')
        for i in range(12):
            choice = policy.choose(context(), ['image', 'audio'], float(i))
            value = .8 if choice['action'] == preferred else .2
            result = policy.learn(Consequence(choice['id'], float(i), value, 0., .1), float(i))
            self.assertTrue(result['learned'])
        return policy

    def test_different_consequences_produce_different_choices_for_same_available_input(self):
        first, second = self.trained('image'), self.trained('audio')
        self.assertEqual(first.choose(context(), ['image', 'audio'], 12.)['action'], 'image')
        self.assertEqual(second.choose(context(), ['image', 'audio'], 12.)['action'], 'audio')
        first.banks['image'].weights.zero_()
        self.assertNotEqual(first.choose(context(), ['image', 'audio'], 13.)['action'], 'image')

    def test_quiet_can_be_learned_as_a_positive_choice(self):
        policy = self.trained('quiet')
        choice = policy.choose(context(), ['image', 'audio'], 12.)
        self.assertEqual(choice['action'], 'quiet')
        self.assertEqual(choice['modalities'], [])
        self.assertEqual(choice['reason'], 'learned_consequence_value')

    def test_values_depend_on_previous_context_and_unseen_context_remains_exploration(self):
        policy = NativeAttention()
        policy.configure('learned')
        at = 0.
        for axis, preferred in ((0, 'image'), (1, 'audio')):
            for _ in range(12):
                choice = policy.choose(context(axis), ['image', 'audio'], at)
                policy.learn(Consequence(choice['id'], at, .8 if choice['action'] == preferred else -.5, 0., .1), at)
                at += 1.
        self.assertEqual(policy.choose(context(0), ['image', 'audio'], at)['action'], 'image')
        self.assertEqual(policy.choose(context(1), ['image', 'audio'], at)['action'], 'audio')
        self.assertEqual(policy.choose(context(100), ['image', 'audio'], at)['reason'], 'explore_unlearned_consequence')

    def test_duplicate_expired_self_and_missing_feedback_do_not_teach(self):
        policy = NativeAttention()
        policy.configure('learned')
        choice = policy.choose(context(), ['image', 'audio'], 0.)
        result = Consequence(choice['id'], .1, .5, 0., .1)
        self.assertTrue(policy.learn(result, .1)['learned'])
        self.assertFalse(policy.learn(result, .1)['learned'])
        with self.assertRaises(ValueError):
            policy.learn(Consequence(choice['id'], .1, .5, 0., .1, 'self'), .1)
        expired = policy.choose(context(), ['image', 'audio'], 1.)
        self.assertFalse(policy.learn(Consequence(expired['id'], 62., .5, 0., .1), 62.)['learned'])
        self.assertEqual(sum(int(bank.writes) for bank in policy.banks.values()), 1)

    def test_restart_preserves_values_pending_decisions_and_rejects_corruption(self):
        policy = self.trained('audio')
        pending = policy.choose(context(), ['image', 'audio'], 12.)
        payload = policy.snapshot()
        resumed = restore(payload, 12.)
        self.assertTrue(resumed.learn(Consequence(pending['id'], 12., .8, 0., .1), 12.)['learned'])
        self.assertEqual(resumed.choose(context(), ['image', 'audio'], 13.)['action'], 'audio')
        damaged = copy.deepcopy(payload)
        damaged['pending'][pending['id']]['key'][-1] = 0
        with self.assertRaises(ValueError):
            restore(damaged, 12.)
        damaged = copy.deepcopy(payload)
        damaged['banks']['text']['weights'][0, 0] = 1.
        with self.assertRaises(ValueError):
            restore(damaged, 12.)

    def test_feedback_budget_does_not_force_more_acquisition(self):
        policy = NativeAttention()
        policy.configure('learned')
        for i in range(16):
            self.assertIsNotNone(policy.choose(context(), ['image'], float(i))['id'])
        overflow = policy.choose(context(), ['image'], 16.)
        self.assertEqual(overflow['action'], 'quiet')
        self.assertIsNone(overflow['id'])
        self.assertFalse(policy.sources)


class AttentionAcquisitionContracts(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        self.native = NativeGrounding()
        self.addCleanup(self.native.moments.close)

    def test_attention_to_image_does_not_store_or_learn_the_available_audio(self):
        self.native.attention.configure('learned')
        result = self.native.observe(packets(1., 0), 1.)
        self.assertEqual(result['attention']['action'], 'image')
        self.assertEqual(result['received'], 2)
        self.assertEqual(result['encoded'], 1)
        self.assertEqual(self.native.moments.traces[0]['known'], [True, False, False])
        lesson = self.native.teach(WrittenName('maruvi', 1., 0), 1.)
        self.assertEqual(lesson['modalities'], ['image'])
        self.assertFalse(self.native.evoke('maruvi', 'audio')['supported'])
        self.assertEqual(int(self.native.dynamics.banks['audio'].writes), 0)
        recalled = self.native.recall_moments([packets(1., 0)[0]], targets=['audio'])
        self.assertEqual(recalled['reason'], 'unobserved_target')

    def test_quiet_receives_without_learning_and_old_unattended_input_cannot_be_replayed(self):
        self.native.attention.configure('quiet')
        result = self.native.observe(packets(1., 0), 1.)
        self.assertEqual(result['encoded'], 0)
        self.assertEqual(self.native.received_observations, 2)
        self.assertEqual(self.native.observations, 0)
        self.assertEqual(self.native.dynamics.frames, 0)
        self.assertFalse(self.native.moments.traces)
        self.native.attention.configure('full')
        self.assertEqual(self.native.observe(packets(1., 0), 2.)['reason'], 'self_or_stale')
        self.assertEqual(self.native.received_observations, 2)
        self.native.observe(packets(2.1, 1), 2.1)
        self.assertEqual(self.native.observations, 2)
        self.assertEqual(self.native.received_observations, 4)

    def test_receiving_again_can_complete_new_memory_but_cannot_fill_the_old_gap(self):
        self.native.attention.configure('learned')
        self.native.observe(packets(1., 0), 1.)
        self.native.teach(WrittenName('maruvi', 1., 0), 1.)
        self.native.attention.configure('full')
        self.native.observe(packets(1.1, 1), 1.1)
        self.native.teach(WrittenName('maruvi', 1.1, 1), 1.1)
        old = self.native.recall_moments([packets(1., 0)[0]], window=(.99, 1.01), targets=['audio'])
        self.assertEqual(old['reason'], 'unobserved_target')
        new = self.native.recall_moments([packets(1.1, 1)[0]], window=(1.09, 1.1), targets=['audio'])
        self.assertTrue(new['supported'])

    def test_restart_and_legacy_migration_preserve_received_and_attended_counts(self):
        self.native.attention.configure('quiet')
        self.native.observe(packets(1., 0), 1.)
        saved = self.native.snapshot()
        resumed = restore_native(saved, 1.)
        self.addCleanup(resumed.moments.close)
        self.assertEqual(resumed.received_observations, 2)
        self.assertEqual(resumed.observations, 0)
        self.assertEqual(resumed.attention.mode, 'quiet')
        damaged = copy.deepcopy(saved)
        damaged['received_observations'] = 0
        with self.assertRaises(ValueError):
            restore_native(damaged, 1.)
        legacy = NativeGrounding()
        self.addCleanup(legacy.moments.close)
        legacy.observe(packets(1., 0), 1.)
        old = legacy.snapshot()
        old['format'] = 4
        old.pop('attention')
        old.pop('received_observations')
        old.pop('links')
        old.pop('naming_proofs')
        migrated = restore_native(old, 1.)
        self.addCleanup(migrated.moments.close)
        self.assertEqual(migrated.received_observations, migrated.observations)
        self.assertEqual(migrated.attention.mode, 'full')


class AttentionStreamContracts(unittest.TestCase):
    setUp = stream_tests.StreamContracts.setUp
    core = stream_tests.StreamContracts.core
    factory = stream_tests.StreamContracts.factory
    until = stream_tests.StreamContracts.until
    setUpClass = classmethod(stream_tests.StreamContracts.setUpClass.__func__)
    tearDownClass = classmethod(stream_tests.StreamContracts.tearDownClass.__func__)

    def test_external_feedback_is_linked_to_completed_allocation_once(self):
        core = self.core()
        core.configure_native_attention('learned')
        seen = []
        def feedback(result, now):
            seen.append(result)
            return Consequence(result['attention']['id'], now, .8, 0., .1)
        core.native_stream.configure(self.inbox, self.factory, feedback)
        frame = self.inbox.publish({'image': self.signal})
        manifest = self.inbox.read(frame)
        core.native_stream.ingest(frame, manifest, manifest['captured_wall'])
        self.until(core, lambda: core.native_stream.jobs[0]['status'] in ('completed', 'ignored', 'failed'))
        self.assertEqual(core.native_stream.jobs[0]['status'], 'completed')
        self.assertEqual(len(seen), 1)
        self.assertEqual(len(core.native.attention.sources), 1)
        self.assertEqual(int(core.native.attention.banks['image'].writes), 1)
        core.tick(.1)
        self.assertEqual(len(seen), 1)
        self.assertEqual(len(core.native.attention.sources), 1)

    def test_invalid_feedback_preserves_perception_and_cannot_train_attention(self):
        core = self.core()
        core.configure_native_attention('learned')
        core.native_stream.configure(self.inbox, self.factory,
            lambda result, now: Consequence(result['attention']['id'], now, .8, 0., .1, 'self'))
        frame = self.inbox.publish({'image': self.signal})
        manifest = self.inbox.read(frame)
        core.native_stream.ingest(frame, manifest, manifest['captured_wall'])
        self.until(core, lambda: core.native_stream.jobs[0]['status'] in ('completed', 'ignored', 'failed'))
        self.assertEqual(core.native_stream.jobs[0]['status'], 'completed')
        self.assertEqual(core.native.observations, 1)
        self.assertFalse(core.native.attention.sources)

    def test_partial_stream_teaches_only_attended_modality_and_rejects_forged_completion(self):
        import wave
        audio = self.folder / 'signal.wav'
        with wave.open(str(audio), 'wb') as output:
            output.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
            output.writeframes(b'\0\0' * 2400)
        core = self.core()
        core.configure_native_attention('learned')
        frame = self.inbox.publish({'image': self.signal, 'audio': audio}, 'maruvi')
        manifest = self.inbox.read(frame)
        core.native_stream.ingest(frame, manifest, manifest['captured_wall'])
        self.until(core, lambda: core.native_stream.jobs[0]['status'] in ('completed', 'ignored', 'failed'))
        result = core.native_stream.jobs[0]['result']
        self.assertEqual(core.native_stream.jobs[0]['status'], 'completed', result)
        self.assertEqual(result['received'], 2)
        self.assertEqual(result['encoded'], 1)
        self.assertEqual(result['learning']['modalities'], ['image'])
        self.assertEqual([item['modality'] for item in result['recognized']], ['image'])
        saved = core.snapshot()
        resumed = restore_core(saved, self.folder / 'partial', self.factory)
        self.addCleanup(resumed.close)
        self.assertFalse(resumed.native.evoke('maruvi', 'audio')['supported'])
        damaged = copy.deepcopy(saved)
        content = damaged['native_stream']['jobs'][0]['result']
        content['encoded'] = 2
        content['attention']['modalities'].append('audio')
        content['recognized'].append({'modality': 'audio', 'supported': False, 'reason': 'no_learned_names'})
        with self.assertRaises(ValueError):
            restore_core(damaged, self.folder / 'forged', self.factory)

    def test_quiet_stream_commit_and_restart_do_not_invent_recognition(self):
        core = self.core()
        core.configure_native_attention('quiet')
        frame = self.inbox.publish({'image': self.signal}, 'maruvi')
        manifest = self.inbox.read(frame)
        core.native_stream.ingest(frame, manifest, manifest['captured_wall'])
        self.until(core, lambda: core.native_stream.jobs[0]['status'] in ('completed', 'ignored', 'failed'))
        job = core.native_stream.jobs[0]
        self.assertEqual(job['status'], 'ignored', job)
        self.assertEqual(job['result']['recognized'], [])
        self.assertEqual(core.native.received_observations, 1)
        self.assertEqual(core.native.observations, 0)
        self.assertFalse(core.native.names)
        saved = core.snapshot()
        resumed = restore_core(saved, self.folder / 'restart', self.factory)
        self.addCleanup(resumed.close)
        self.assertEqual(resumed.native_stream.jobs[0]['status'], 'ignored')
        self.assertEqual(resumed.native.attention.mode, 'quiet')


if __name__ == '__main__':
    unittest.main()
