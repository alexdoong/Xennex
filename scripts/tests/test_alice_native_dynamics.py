"""Unlabeled temporal experience changes predictions; idle time does not train."""
import copy
import sys
import unittest
from pathlib import Path

import torch
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alice_memory.native_dynamics import NativeDynamics, restore
from scripts.alice_memory.native_grounding import NativeGrounding, restore as restore_native
from scripts.alice_memory.native_sensor import NativeObservation
from scripts.alice_memory.conceptual_mind import ConceptualMind
import test_alice_word_grounding as fixtures


def packet(axis, at, sequence, modality='image', origin='environment'):
    return NativeObservation(modality, F.one_hot(torch.tensor(axis), 128).float(), at, sequence, 'a' * 64, origin=origin)


class NativePredictionContracts(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)

    def train(self, sequence, steps=100):
        model = NativeDynamics()
        for i in range(steps):
            at = (i + 1) * .1
            model.observe([packet(sequence[i % len(sequence)], at, i)], at)
        return model

    def test_different_experiences_change_next_prediction_for_same_current_percept(self):
        left = self.train([0, 1])
        right = self.train([0, 2])
        for model in (left, right):
            at = model.clock + .1
            model.observe([packet(0, at, 100)], at)
        self.assertEqual(left.last['values'][0].argmax(), right.last['values'][0].argmax())
        a, b = left.predict(), right.predict()
        self.assertTrue(a['supported'])
        self.assertTrue(b['supported'])
        self.assertEqual(a['modalities']['image'].argmax(), 1)
        self.assertEqual(b['modalities']['image'].argmax(), 2)
        self.assertFalse(left.predict()['autobiographical_write'])

    def test_previous_context_disambiguates_identical_current_input(self):
        model = self.train([0, 1, 2, 3, 1, 4], 180)
        for axis in (0, 1):
            at = model.clock + .1
            model.observe([packet(axis, at, int(at * 10))], at)
        first = model.predict()['modalities']['image']
        for axis in (3, 1):
            at = model.clock + .1
            model.observe([packet(axis, at, int(at * 10))], at)
        second = model.predict()['modalities']['image']
        self.assertEqual(first.argmax(), 2)
        self.assertEqual(second.argmax(), 4)

    def test_reserved_rotation_is_predicted_before_seeing_its_target(self):
        import math
        for seed in (17, 29, 71):
            generator = torch.Generator().manual_seed(seed)
            basis = torch.linalg.qr(torch.randn(128, 2, generator=generator)).Q
            model = NativeDynamics()
            at, sequence = 0., 0

            def present(angle, gap):
                nonlocal at, sequence
                at += gap
                latent = F.normalize(math.cos(angle) * basis[:, 0] + math.sin(angle) * basis[:, 1], dim=0)
                model.observe([NativeObservation('image', latent, at, sequence, 'a' * 64)], at)
                sequence += 1
                return latent

            for _ in range(10):
                for angle in (0., math.pi / 2, math.pi, 3 * math.pi / 2):
                    present(angle, 3.)
                    present(angle + math.pi / 2, .1)
            writes = int(model.banks['image'].writes)
            # The 45-degree context was never used in training; the gap starts
            # a new context and does not train against the previous trial.
            observed = present(math.pi / 4, 3.)
            expected = F.normalize(-basis[:, 0] + basis[:, 1], dim=0)
            prediction = model.predict()
            self.assertEqual(int(model.banks['image'].writes), writes)
            self.assertTrue(prediction['supported'])
            self.assertGreater(float(prediction['modalities']['image'] @ expected), .99)
            self.assertLess(float(prediction['modalities']['image'].sub(expected).square().sum()), .01)
            self.assertGreater(float(observed.sub(expected).square().sum()), 1.9)
            model.banks['image'].weights.zero_()
            self.assertFalse(model.predict()['supported'])

    def test_idle_missing_modalities_and_gaps_do_not_create_training_targets(self):
        model = self.train([0, 1], 20)
        before = copy.deepcopy(model.snapshot())
        model.advance(model.clock + 60)
        self.assertEqual(model.frames, before['frames'])
        self.assertEqual(model.pairs, before['pairs'])
        self.assertEqual(model.predict()['reason'], 'old_native_context')
        for name, bank in model.banks.items():
            self.assertTrue(all(torch.equal(v, before['banks'][name][k]) for k, v in bank.state_dict().items()))
        self.assertEqual(int(model.banks['audio'].writes), 0)
        at = model.clock + .1
        model.observe([packet(2, at, 21)], at)
        self.assertEqual(model.pairs, before['pairs'])
        self.assertEqual(model.discontinuous, 1)

    def test_delayed_delivery_uses_acquisition_order_not_processing_interval(self):
        model = NativeDynamics()
        model.observe([packet(0, .1, 0)], 10.)
        model.observe([packet(1, .2, 1)], 20.)
        self.assertEqual(model.pairs, 1)
        self.assertEqual(model.predict()['reason'], 'old_native_context')
        model.observe([packet(2, .15, 2)], 21.)
        self.assertEqual(model.pairs, 1)
        self.assertEqual(model.late, 1)
        self.assertEqual(model.last['acquired_at'], .2)

    def test_restart_retains_learned_forecast_and_rejects_corruption(self):
        model = self.train([0, 1], 30)
        payload = model.snapshot()
        resumed = restore(payload, model.clock, model.frames)
        self.assertTrue(torch.equal(model.predict()['modalities']['image'], resumed.predict()['modalities']['image']))
        for key in ('frames', 'pairs', 'historical_frames'):
            damaged = copy.deepcopy(payload)
            damaged[key] += 1
            with self.assertRaises(ValueError):
                restore(damaged, model.clock, model.frames)
        damaged = copy.deepcopy(payload)
        damaged['banks']['audio']['weights'][0, 0] = 1.
        with self.assertRaises(ValueError):
            restore(damaged, model.clock, model.frames)

    def test_self_and_invalid_input_do_not_change_state(self):
        model = NativeDynamics()
        with self.assertRaises(ValueError):
            model.observe([packet(0, 1., 0, origin='self')], 1.)
        self.assertEqual(model.frames, 0)
        self.assertEqual(model.clock, 0.)


class NativePredictionIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.WrittenGroundingTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixtures.WrittenGroundingTests.tearDownClass()

    def test_shared_owner_receives_unlabeled_native_experience_and_can_remain_idle(self):
        fixture = fixtures.WrittenGroundingTests()
        self.addCleanup(fixture.doCleanups)
        core = ConceptualMind(fixture.fixture(False))
        self.addCleanup(core.close)
        for i in range(16):
            at = core.clock + .1
            core.perceive_native([packet(i % 2, at, i)], .1)
        self.assertEqual(core.native.dynamics.frames, 16)
        self.assertEqual(core.native.dynamics.pairs, 15)
        self.assertFalse(core.native.names)
        previous_novelty = core.mind.internal.novelty
        at = core.clock + .1
        core.perceive_native([packet(5, at, 16)], .1)
        self.assertGreater(core.mind.internal.novelty, previous_novelty + .4)
        before = core.native.dynamics.snapshot()
        core.tick(5.)
        self.assertEqual(core.native.dynamics.frames, 17)
        self.assertEqual(core.native.dynamics.pairs, 16)
        self.assertTrue(torch.equal(before['banks']['image']['weights'], core.native.dynamics.banks['image'].weights))

    def test_old_memory_migration_does_not_replay_history_as_new_experience(self):
        native = NativeGrounding()
        self.addCleanup(native.moments.close)
        native.observe([packet(0, 1., 0)], 1.)
        old = native.snapshot()
        old['format'] = 3
        old.pop('dynamics')
        old.pop('attention')
        old.pop('received_observations')
        old.pop('links')
        old.pop('naming_proofs')
        resumed = restore_native(old, 1.)
        self.addCleanup(resumed.moments.close)
        self.assertEqual(resumed.dynamics.frames, 0)
        self.assertEqual(resumed.dynamics.historical_frames, 1)
        self.assertEqual(resumed.dynamics.predict()['reason'], 'no_native_context')


if __name__ == '__main__':
    unittest.main()
