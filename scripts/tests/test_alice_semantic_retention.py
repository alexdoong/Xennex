"""Retention of learned correspondences, partial detail and warm reacquisition."""
import copy
import math
import sys
import unittest
from pathlib import Path

import torch
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.alice_memory.native_links import NativeLinks, restore
from scripts.alice_memory.native_grounding import NativeGrounding, restore as restore_grounding
from scripts.alice_memory.native_moments import NativeMoments
from scripts.alice_memory.native_sensor import NativeObservation
from scripts.alice_memory.semantic_retention import relaxed_information


def bases(seed):
    generator = torch.Generator().manual_seed(seed)
    return tuple(torch.linalg.qr(torch.randn(128, 128, generator=generator)).Q for _ in range(2))


def packet(modality, basis, detail, at, sequence, origin='environment'):
    return NativeObservation(modality, F.normalize(basis[:, 0] + detail * basis[:, 1], dim=0),
                             at, sequence, 'a' * 64, origin=origin)


def curriculum(links, image, audio):
    for index, detail in enumerate([.3, -.3] + [0.] * 32):
        now = 1. + index * .001
        links.observe([packet('image', image, detail, now, index),
                       packet('audio', audio, detail, now, index)], now)


class SemanticRetentionContracts(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)

    def test_information_flow_is_monotone_partition_invariant_and_reinforcement_sensitive(self):
        mass = torch.tensor([0., .02, 1.6, 200.], dtype=torch.float64)
        once = relaxed_information(mass, 300., 10.)
        split = relaxed_information(relaxed_information(mass, 100., 10.), 200., 10.)
        self.assertTrue(torch.allclose(once, split, atol=1e-12, rtol=1e-12))
        self.assertTrue(torch.all(once <= mass))
        self.assertGreater(float(once[3] / mass[3]), float(once[2] / mass[2]))
        self.assertEqual(float(once[0]), 0.)
        self.assertTrue(torch.equal(relaxed_information(mass, 0., 10.), mass))
        self.assertEqual(int(relaxed_information(mass, 1e12, 10.).count_nonzero()), 0)

    def test_reserved_detail_fades_while_reinforced_component_and_familiarity_remain(self):
        for seed in (17, 29, 71):
            image, audio = bases(seed)
            links = NativeLinks(retention_seconds=10.)
            control = NativeLinks(retention_seconds=1e12)
            curriculum(links, image, audio)
            curriculum(control, image, audio)
            cue = packet('image', image, .1, links.clock, 0, 'self')
            before = links.predict(cue, 'audio')
            self.assertTrue(before['supported'])
            self.assertGreater(float(before['latent'] @ audio[:, 1]), .09)
            snapshot = links.snapshot()
            links.advance(301.033)
            control.advance(301.033)
            partial = links.predict(cue, 'audio')
            self.assertTrue(partial['supported'])
            self.assertGreater(float(partial['latent'] @ audio[:, 0]), .999)
            self.assertLess(abs(float(partial['latent'] @ audio[:, 1])), .001)
            self.assertGreater(float(control.predict(cue, 'audio')['latent'] @ audio[:, 1]), .09)
            inaccessible = links.predict(packet('image', image, .3, links.clock, 0, 'self'), 'audio')
            self.assertFalse(inaccessible['supported'])
            self.assertGreater(inaccessible['familiarity'], .9)
            self.assertFalse(inaccessible['autobiographical_write'])
            # Aging is a lazy view of sufficient statistics, not new training.
            for name in ('weights', 'precision', 'writes'):
                self.assertTrue(torch.equal(snapshot['banks']['image:audio'][name], links.banks['image:audio'].state_dict()[name]))
            links.advance(10001.)
            self.assertFalse(links.predict(cue, 'audio')['supported'])

    def test_reexposure_transfers_to_reserved_opposite_detail_better_than_cold_learning(self):
        for seed in (17, 29, 71):
            image, audio = bases(seed)
            warm = NativeLinks(retention_seconds=10.)
            curriculum(warm, image, audio)
            warm.advance(301.033)
            cold = NativeLinks(retention_seconds=10.)
            lesson = [packet('image', image, .3, 302., 34), packet('audio', audio, .3, 302., 34)]
            warm.observe(lesson, 302.)
            cold.observe(lesson, 302.)
            cue = packet('image', image, -.2, 302., 0, 'self')  # Never taught, even before fading.
            result = warm.predict(cue, 'audio')
            self.assertTrue(result['supported'])
            target = packet('audio', audio, -.2, 302., 0).latent
            self.assertGreater(float(result['latent'] @ target), .999)
            self.assertFalse(cold.predict(cue, 'audio')['supported'])

    def test_core_learning_survives_episode_retirement_without_replaying_episodes(self):
        image, audio = bases(17)
        native = NativeGrounding()
        native.moments.close()
        native.moments = NativeMoments(2, 1)
        native.links.retention_seconds = 10.
        try:
            for index, detail in enumerate([.3, -.3] + [0.] * 32):
                now = 1. + index * .001
                native.observe([packet('image', image, detail, now, index), packet('audio', audio, detail, now, index)], now)
            # Space novel, single-channel exposures so the original important
            # episode is actually retired by the existing retention policy.
            for index, at in enumerate((301.033, 601.033), 34):
                vector = image[:, index - 24]
                native.observe([NativeObservation('image', vector, at, index, 'b' * 64)], at)
            self.assertEqual([trace['id'] for trace in native.moments.traces], [34, 35])
            result = native.associate(packet('image', image, .3, native.clock, 0, 'self'), 'audio')
            self.assertFalse(result['supported'])
            self.assertGreater(result['familiarity'], .9)
            self.assertEqual(native.observations, 70)
            self.assertEqual(native.links.frames, 36)
            self.assertFalse(native.names)
            resumed = restore_grounding(native.snapshot(), native.clock)
            try:
                self.assertEqual(resumed.associate(packet('image', image, .3, native.clock, 0, 'self'), 'audio'), result)
                self.assertEqual(resumed.links.frames, 36)
                self.assertEqual(len(resumed.moments.traces), 2)
            finally:
                resumed.moments.close()
        finally:
            native.moments.close()

    def test_query_idle_partition_and_restart_do_not_reheat_or_learn(self):
        image, audio = bases(29)
        links = NativeLinks(retention_seconds=10.)
        curriculum(links, image, audio)
        split = restore(links.snapshot(), links.clock, links.frames)
        for now in (2., 10., 100., 301.033):
            split.advance(now)
        links.advance(301.033)
        cue = packet('image', image, .1, links.clock, 0, 'self')
        result = links.predict(cue, 'audio')
        restarted = restore(links.snapshot(), links.clock, links.frames)
        for candidate in (split, restarted):
            self.assertTrue(torch.equal(candidate.predict(cue, 'audio')['latent'], result['latent']))
            self.assertEqual(candidate.predict(cue, 'audio')['variance'], result['variance'])
            self.assertEqual(candidate.updated_at, links.updated_at)
            self.assertEqual(candidate.frames, 34)

    def test_legacy_starts_aging_at_checkpoint_without_historical_replay(self):
        image, audio = bases(71)
        original = NativeLinks()
        curriculum(original, image, audio)
        old = original.snapshot()
        old['format'] = 2
        for field in ('retention_rule', 'retention_seconds', 'updated_at'):
            old.pop(field)
        migrated = restore(old, original.clock, original.frames)
        self.assertEqual(migrated.updated_at['general']['image:audio'], original.clock)
        self.assertIsNone(migrated.updated_at['general']['text:image'])
        self.assertTrue(torch.equal(migrated.banks['image:audio'].weights, original.banks['image:audio'].weights))
        cue = packet('image', image, .1, original.clock, 0, 'self')
        self.assertTrue(torch.equal(migrated.predict(cue, 'audio')['latent'], original.predict(cue, 'audio')['latent']))

    def test_invalid_policy_future_missing_and_nonreciprocal_anchors_are_rejected(self):
        image, audio = bases(17)
        original = NativeLinks()
        curriculum(original, image, audio)
        for field, value in (('retention_rule', 'invented'), ('retention_seconds', float('nan')), ('retention_seconds', True)):
            damaged = copy.deepcopy(original.snapshot())
            damaged[field] = value
            with self.assertRaises(ValueError):
                restore(damaged, original.clock, original.frames)
        for stamp in (None, original.clock + 1., original.clock - .001):
            damaged = copy.deepcopy(original.snapshot())
            damaged['updated_at']['general']['image:audio'] = stamp
            with self.assertRaises(ValueError):
                restore(damaged, original.clock, original.frames)


if __name__ == '__main__':
    unittest.main()
