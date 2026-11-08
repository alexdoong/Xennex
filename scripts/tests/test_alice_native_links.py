"""Unnamed cross-modal learning, reserved transfer and attention/retention."""
import copy
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import torch
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alice_memory.native_grounding import NativeGrounding, restore as restore_grounding
from scripts.alice_memory.native_links import NativeLinks, restore
from scripts.alice_memory.native_moments import NativeMoments
from scripts.alice_memory.native_sensor import NativeObservation
from scripts.alice_memory.online_memory import OnlineMemory
from scripts.alice_memory.conceptual_mind import ConceptualMind
import test_alice_word_grounding as fixtures


def packet(modality, vector, at, sequence, origin='environment'):
    return NativeObservation(modality, F.normalize(vector.float(), dim=0), at, sequence, 'a' * 64, origin=origin)


class NativeLinkContracts(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)

    def test_reserved_cross_modal_combinations_survive_forgetting_without_names_or_replay(self):
        for seed in (17, 29, 71):
            generator = torch.Generator().manual_seed(seed)
            image = torch.linalg.qr(torch.randn(128, 128, generator=generator)).Q
            audio = torch.linalg.qr(torch.randn(128, 128, generator=generator)).Q
            native = NativeGrounding()
            native.moments.close()
            native.moments = NativeMoments(2, 1)
            try:
                for index in range(4):
                    theta = index * math.pi / 2
                    visual = math.cos(theta) * image[:, 0] + math.sin(theta) * image[:, 1]
                    sound = math.cos(theta) * audio[:, 0] + math.sin(theta) * audio[:, 1]
                    now = float(index + 1)
                    native.observe([packet('image', visual, now, index), packet('audio', sound, now, index)], now)
                state = native.links.snapshot()
                for index in range(8):
                    theta = (index + .5) * math.pi / 4  # None of these cues were taught.
                    visual = math.cos(theta) * image[:, 0] + math.sin(theta) * image[:, 1]
                    sound = math.cos(theta) * audio[:, 0] + math.sin(theta) * audio[:, 1]
                    cue = packet('image', visual, 4., 0, 'self')
                    result = native.associate(cue, 'audio')
                    self.assertTrue(result['supported'])
                    self.assertGreater(float(result['latent'] @ sound), .999)
                    self.assertFalse(result['directly_observed'])
                    self.assertFalse(native.recall_moments([cue])['supported'])
                self.assertFalse(native.names)
                self.assertFalse(native.sources)
                self.assertEqual(len(native.moments.traces), 2)
                self.assertEqual(native.links.frames, 4)
                self.assertTrue(torch.equal(state['banks']['image:audio']['weights'], native.links.banks['image:audio'].weights))
                resumed = restore_grounding(native.snapshot(), 4.)
                try:
                    self.assertTrue(torch.equal(resumed.associate(cue, 'audio')['latent'], result['latent']))
                    resumed.links.banks['image:audio'].weights.zero_()
                    self.assertFalse(resumed.associate(cue, 'audio')['supported'])
                finally:
                    resumed.moments.close()
                original = native.associate(cue, 'audio')['latent'].clone()
                native.links.banks['image:audio'].weights.mul_(-1)
                self.assertLess(float(native.associate(cue, 'audio')['latent'] @ original), -.999)
            finally:
                native.moments.close()

    def test_single_channel_and_idle_do_not_invent_a_correspondence(self):
        links = NativeLinks()
        cue = packet('image', F.one_hot(torch.tensor(0), 128), 1., 0)
        self.assertFalse(links.predict(cue, 'audio')['supported'])
        links.observe([cue], 1.)
        links.advance(1000.)
        self.assertEqual(links.predict(cue, 'audio')['reason'], 'no_observed_correspondence')
        self.assertTrue(all(int(bank.writes) == 0 for bank in links.banks.values()))

    def test_surprise_uses_prediction_before_learning_the_new_target(self):
        links = NativeLinks()
        visual = F.one_hot(torch.tensor(0), 128)
        first = F.one_hot(torch.tensor(3), 128)
        second = F.one_hot(torch.tensor(4), 128)
        links.observe([packet('image', visual, 1., 0), packet('audio', first, 1., 0)], 1.)
        learned = links.observe([packet('image', visual, 2., 1), packet('audio', second, 2., 1)], 2.)
        self.assertAlmostEqual(learned['errors']['image:audio'], 2., places=5)
        self.assertNotIn('audio:image', learned['errors'])  # Uncovered new audio cue.
        self.assertEqual(int(links.banks['image:audio'].writes), 2)

    def test_self_invalid_unsynchronized_and_failed_update_preserve_prior_links(self):
        links = NativeLinks()
        vector = F.one_hot(torch.tensor(0), 128)
        cue = packet('image', vector, 1., 0)
        sound = packet('audio', vector, 1., 0)
        for signals in ([packet('image', vector, 1., 0, 'self'), sound],
                        [cue, packet('audio', vector, 1.1, 0)], [cue, cue]):
            with self.assertRaises(ValueError):
                links.observe(signals, 2.)
        original_write = OnlineMemory.write
        calls = []
        def fail(bank, *args, **kwargs):
            calls.append(bank)
            if len(calls) == 2:
                raise ValueError('second correspondence refused')
            return original_write(bank, *args, **kwargs)
        with patch.object(OnlineMemory, 'write', fail):
            with self.assertRaises(ValueError):
                links.observe([cue, sound], 1.)
        self.assertEqual((links.frames, links.clock), (0, 0.))
        self.assertTrue(all(int(bank.writes) == 0 for bank in links.banks.values()))

    def test_attention_controls_correspondence_acquisition_and_later_exposure_does_not_fill_gap(self):
        native = NativeGrounding()
        try:
            vector = F.one_hot(torch.tensor(0), 128)
            native.attention.configure('quiet')
            native.observe([packet('image', vector, 1., 0), packet('audio', vector, 1., 0)], 1.)
            self.assertEqual(native.links.frames, 0)
            native.attention.configure('full')
            native.observe([packet('image', vector, 2., 1)], 2.)
            self.assertFalse(native.associate(packet('image', vector, 2., 1), 'audio')['supported'])
            native.observe([packet('image', vector, 3., 2), packet('audio', vector, 3., 2)], 3.)
            self.assertEqual(int(native.links.banks['image:audio'].writes), 1)
            self.assertEqual(native.moments.get(0)['known'], [True, False, False])
        finally:
            native.moments.close()

    def test_restart_rejects_nan_bad_covariance_hidden_learning_and_unpaired_counts(self):
        links = NativeLinks()
        vector = F.one_hot(torch.tensor(0), 128)
        links.observe([packet('image', vector, 1., 0), packet('audio', vector, 1., 0)], 1.)
        payload = links.snapshot()
        self.assertEqual(restore(payload, 1., 1).frames, 1)
        for alteration in ('nan', 'untrained', 'covariance', 'counter', 'reciprocal'):
            bad = copy.deepcopy(payload)
            if alteration == 'nan':
                bad['banks']['image:audio']['weights'][0, 0] = float('nan')
            elif alteration == 'untrained':
                bad['banks']['image:text']['weights'][0, 0] = 1.
            elif alteration == 'covariance':
                bad['banks']['image:audio']['precision'].zero_()
            elif alteration == 'counter':
                bad['frames'] += 1
            else:
                bad['banks']['audio:image'] = copy.deepcopy(bad['banks']['image:text'])
            with self.assertRaises(ValueError):
                restore(bad, 1., 1)

    def test_unknown_direction_abstains_and_old_format_does_not_replay_retained_episodes(self):
        native = NativeGrounding()
        vector = F.one_hot(torch.tensor(0), 128)
        try:
            native.observe([packet('image', vector, 1., 0), packet('audio', vector, 1., 0)], 1.)
            novel = packet('image', F.one_hot(torch.tensor(10), 128), 1., 0)
            self.assertFalse(native.associate(novel, 'audio')['supported'])
            old = native.snapshot()
            old['format'] = 6
            old.pop('links')
            old.pop('naming_proofs')
            resumed = restore_grounding(old, 1.)
            try:
                self.assertEqual(resumed.links.historical_frames, 1)
                self.assertEqual(resumed.links.frames, 0)
                self.assertFalse(resumed.associate(packet('image', vector, 1., 0), 'audio')['supported'])
            finally:
                resumed.moments.close()
        finally:
            native.moments.close()


class LinkSharedStateContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.WrittenGroundingTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixtures.WrittenGroundingTests.tearDownClass()

    def test_associative_surprise_reaches_shared_state_without_a_temporal_target(self):
        fixture = fixtures.WrittenGroundingTests()
        self.addCleanup(fixture.doCleanups)
        core = ConceptualMind(fixture.fixture(False))
        self.addCleanup(core.close)
        visual = F.one_hot(torch.tensor(0), 128)
        first = F.one_hot(torch.tensor(3), 128)
        second = F.one_hot(torch.tensor(4), 128)
        at = core.clock + .1
        core.perceive_native([packet('image', visual, at, 0), packet('audio', first, at, 0)], .1)
        at = core.clock + 3.
        event = core.perceive_native([packet('image', visual, at, 1), packet('audio', second, at, 1)], 3.)['native_perception']
        self.assertFalse(event['prediction_learning']['errors'])
        self.assertAlmostEqual(event['association_learning']['errors']['image:audio'], 2., places=5)
        self.assertAlmostEqual(core.mind.internal.novelty, 1., places=5)


if __name__ == '__main__':
    unittest.main()
