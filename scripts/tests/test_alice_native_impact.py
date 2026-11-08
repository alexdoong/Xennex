"""Experienced consequence values, retention, episode identity and shared affect."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import torch
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alice_memory.conceptual_mind import ConceptualMind
from scripts.alice_memory.importance import Consequence
from scripts.alice_memory.native_grounding import NativeGrounding, restore
from scripts.alice_memory.native_impact import MomentValues
from scripts.alice_memory.native_interpretation import NativeStatement
from scripts.alice_memory.native_moments import NativeMoments
from scripts.alice_memory.native_sensor import NativeObservation
from scripts.alice_memory.online_memory import OnlineMemory
import test_alice_word_grounding as fixtures


def packet(axis, at, sequence):
    return NativeObservation('image', F.one_hot(torch.tensor(axis), 128).float(), at, sequence, 'a' * 64)


class NativeImpactContracts(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        self.native = NativeGrounding()
        self.native.moments.close()
        self.native.moments = NativeMoments(2, 1)
        self.addCleanup(self.native.moments.close)
        self.native.attention.configure('learned')

    def first(self, benefit=.9, social=0., effort=0.):
        result = self.native.observe([packet(0, 1., 0)], 1.)
        number = result['attention']['id']
        outcome = Consequence(number, 1., benefit, social, effort)
        self.assertTrue(self.native.learn_attention(outcome)['memory_impact']['learned'])
        self.native.attention.configure('full')
        self.native.observe([packet(1, 2., 1)], 2.)
        return outcome

    def test_diagonal_consequence_update_matches_dense_one_hot_rls(self):
        sparse = MomentValues(2)
        dense = OnlineMemory(2, 3)
        for index in range(2):
            outcome = Consequence(index + 1, 1., .8 - index, -.4, .1)
            sparse.write(index, outcome)
            dense.write(F.one_hot(torch.tensor(index), 2).double(), torch.tensor([outcome.benefit, outcome.social, outcome.effort], dtype=torch.float64), strength=10.)
        self.assertTrue(torch.allclose(sparse.weights.T, dense.weights, atol=1e-10, rtol=0))
        self.assertTrue(torch.allclose(sparse.precision, dense.precision.diag(), atol=1e-10, rtol=0))

    def test_positive_and_negative_impact_preserve_old_episode_over_recent_neutral_one(self):
        self.first()
        state = self.native.snapshot()
        erased = restore(state, 2.)
        self.addCleanup(erased.moments.close)
        erased.moments.values.weights.zero_()
        for native in (self.native, erased):
            native.advance(1000.)
            native.observe([packet(2, 1001., 2)], 1001.)
        self.assertEqual([item['id'] for item in self.native.moments.traces], [0, 2])
        self.assertEqual([item['id'] for item in erased.moments.traces], [1, 2])
        # Negative consequences also have magnitude; they are not discarded as low positive utility.
        negative = NativeGrounding()
        negative.moments.close()
        negative.moments = NativeMoments(2, 1)
        self.addCleanup(negative.moments.close)
        negative.attention.configure('learned')
        event = negative.observe([packet(0, 1., 0)], 1.)
        negative.learn_attention(Consequence(event['attention']['id'], 1., -.9, 0., 0.))
        negative.attention.configure('full')
        negative.observe([packet(1, 2., 1)], 2.)
        negative.advance(1000.)
        negative.observe([packet(2, 1001., 2)], 1001.)
        self.assertEqual([item['id'] for item in negative.moments.traces], [0, 2])
        self.assertLess(negative.moments.values.read(0)['value'], 0.)

    def test_impact_is_not_freshness_and_does_not_guarantee_permanent_retention(self):
        self.first()
        source = self.native.moments.get(0)['impact'].copy()
        before = self.native.moments.impact(self.native.moments.get(0), 2.)
        self.native.advance(1000000.)
        self.assertLess(self.native.moments.impact(self.native.moments.get(0), 1000000.), before)
        self.assertEqual(self.native.moments.get(0)['impact'], source)
        self.native.observe([packet(2, 1000000., 2)], 1000000.)
        self.native.observe([packet(3, 1000000.1, 3)], 1000000.1)
        self.assertIsNone(self.native.moments.get(0))
        self.assertFalse(self.native.moments.values.updates.count_nonzero())
        self.assertTrue(all(item['impact'] is None for item in self.native.moments.traces))

    def test_duplicate_self_expired_or_wrong_action_feedback_does_not_change_impact(self):
        outcome = self.first()
        before = self.native.moments.values.snapshot()
        self.assertFalse(self.native.learn_attention(outcome)['learned'])
        self.assertFalse(self.native.learn_attention(Consequence(999, 2., 1., 1., 0.))['learned'])
        self.native.attention.configure('learned')
        event = self.native.observe([packet(2, 3., 2)], 3.)
        self.native.advance(100.)
        self.assertFalse(self.native.learn_attention(Consequence(event['attention']['id'], 100., 1., 1., 0.))['learned'])
        with self.assertRaises(ValueError):
            self.native.learn_attention(Consequence(2, 2., 1., 1., 0., 'self'))
        self.assertTrue(torch.equal(before['weights'], self.native.moments.values.weights))
        self.assertEqual(len(self.native.attention.sources), 1)

    def test_importance_does_not_resolve_ambiguous_events_or_promote_a_report_to_truth(self):
        event = self.native.observe([packet(0, 1., 0)], 1.)
        self.native.teach_interpretation(NativeStatement(0, 'autor', 'pai', 'b' * 64, 0, 1.))
        self.native.learn_attention(Consequence(event['attention']['id'], 1., -.9, 0., 0.))
        self.native.attention.configure('full')
        self.native.observe([packet(0, 2., 1)], 2.)
        recalled = self.native.recall_moments([packet(0, 2., 0)])
        self.assertEqual(recalled['reason'], 'ambiguous_moments')
        self.assertGreater(recalled['candidates'][0]['experienced_impact'], 0.)
        interpretation = self.native.interpret(0, 'autor')
        self.assertEqual(interpretation['subject'], 'pai')
        self.assertFalse(interpretation['directly_observed'])

    def test_feedback_for_forgotten_episode_never_credits_reused_slot(self):
        self.native.moments.close()
        self.native.moments = NativeMoments(1, 1)
        self.addCleanup(self.native.moments.close)
        event = self.native.observe([packet(0, 1., 0)], 1.)
        self.native.attention.configure('full')
        self.native.observe([packet(1, 2., 1)], 2.)
        result = self.native.learn_attention(Consequence(event['attention']['id'], 2., .9, .4, 0.))
        self.assertTrue(result['learned'])
        self.assertFalse(result['memory_impact']['learned'])
        self.assertIsNone(self.native.moments.get(0))
        self.assertIsNone(self.native.moments.get(1)['impact'])
        self.assertFalse(self.native.moments.values.updates.count_nonzero())
        resumed = restore(self.native.snapshot(), 2.)
        self.addCleanup(resumed.moments.close)
        self.assertIsNone(resumed.moments.get(1)['impact'])

    def test_quiet_consequence_learns_attention_without_creating_an_episode(self):
        first = self.native.observe([packet(0, 1., 0)], 1.)
        self.native.learn_attention(Consequence(first['attention']['id'], 1., .2, 0., 0.))
        event = self.native.observe([packet(1, 2., 1)], 2.)
        self.assertEqual(event['attention']['action'], 'quiet')
        result = self.native.learn_attention(Consequence(event['attention']['id'], 2., .8, 0., 0.))
        self.assertFalse(result['memory_impact']['learned'])
        self.assertEqual(len(self.native.moments.traces), 1)
        self.assertEqual(self.native.observations, 1)

    def test_pending_event_survives_restart_and_binding_or_tensor_corruption_is_rejected(self):
        event = self.native.observe([packet(0, 1., 0)], 1.)
        payload = self.native.snapshot()
        resumed = restore(payload, 1.)
        self.addCleanup(resumed.moments.close)
        resumed.learn_attention(Consequence(event['attention']['id'], 1., .9, .1, 0.))
        self.assertGreater(resumed.moments.values.read(0)['impact'], .9)
        for damage in ('ref', 'nan', 'hidden', 'source'):
            bad = copy.deepcopy(resumed.snapshot())
            if damage == 'ref':
                bad['attention']['sources'][0]['moment_ref']['sources']['image']['sha256'] = 'b' * 64
            elif damage == 'nan':
                bad['moments']['values']['weights'][0, 0] = float('nan')
            elif damage == 'hidden':
                bad['moments']['values']['updates'][1] = 1
            else:
                bad['moments']['traces'][0]['impact']['sha256'] = 'b' * 64
            with self.assertRaises(ValueError):
                restore(bad, 1.)

    def test_failed_attention_write_leaves_episode_value_uncommitted(self):
        event = self.native.observe([packet(0, 1., 0)], 1.)
        with patch.object(OnlineMemory, 'write', side_effect=ValueError('feedback refused')):
            with self.assertRaises(ValueError):
                self.native.learn_attention(Consequence(event['attention']['id'], 1., .9, 0., 0.))
        self.assertFalse(self.native.moments.values.updates.count_nonzero())
        self.assertIsNone(self.native.moments.get(0)['impact'])
        self.assertFalse(self.native.attention.sources)

    def test_half_committed_feedback_or_retimed_pending_event_is_rejected(self):
        self.first()
        bad = self.native.snapshot()
        bad['moments']['traces'][0]['impact'] = None
        bad['moments']['values']['weights'][0].zero_()
        bad['moments']['values']['precision'][0] = 1000.
        bad['moments']['values']['updates'][0] = 0
        with self.assertRaises(ValueError):
            restore(bad, 2.)
        fresh = NativeGrounding()
        self.addCleanup(fresh.moments.close)
        fresh.attention.configure('learned')
        event = fresh.observe([packet(0, 1., 0)], 1.)
        fresh.advance(2.)
        bad = fresh.snapshot()
        bad['attention']['pending'][event['attention']['id']]['issued'] = 2.
        with self.assertRaises(ValueError):
            restore(bad, 2.)


class ImpactSharedStateContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.WrittenGroundingTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixtures.WrittenGroundingTests.tearDownClass()

    def test_valid_feedback_changes_shared_valence_duplicate_does_not(self):
        fixture = fixtures.WrittenGroundingTests()
        self.addCleanup(fixture.doCleanups)
        core = ConceptualMind(fixture.fixture(False))
        self.addCleanup(core.close)
        core.configure_native_attention('learned')
        at = core.clock + .1
        event = core.perceive_native([packet(0, at, 0)], .1)['native_perception']
        outcome = Consequence(event['attention']['id'], core.clock, -.8, -.5, .1)
        learned = core.learn_native_attention(outcome)
        self.assertTrue(learned['memory_impact']['learned'])
        self.assertLess(core.mind.internal.valence, 0.)
        valence = core.mind.internal.valence
        self.assertFalse(core.learn_native_attention(outcome)['learned'])
        self.assertEqual(core.mind.internal.valence, valence)


if __name__ == '__main__':
    unittest.main()
