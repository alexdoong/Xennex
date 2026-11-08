"""Experience changes nonverbal working state without names or language calls."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alice_memory.native_grounding import NativeGrounding, restore
from scripts.alice_memory.native_moments import NativeMoments
from test_alice_native_moments import packet


class RelatedMemoryContracts(unittest.TestCase):
    def memory(self):
        value = NativeMoments(16, 2)
        self.addCleanup(value.close)
        value.capture([packet('image', 0, 1., 0), packet('audio', 3, 1., 0)], 1.)
        value.capture([packet('image', 0, 2., 1), packet('audio', 4, 2., 1)], 2.)
        return value

    def test_related_read_preserves_distinct_sounds_and_strict_query_ambiguity(self):
        memory = self.memory()
        cues = [packet('image', 0, 3., 2)]
        self.assertEqual(memory.recall(cues, 3., reactivate=False)['reason'], 'ambiguous_moments')
        related = memory.related(cues, 3.)
        self.assertEqual({x['candidate']['id'] for x in related['entries']}, {0, 1})
        for entry in related['entries']:
            index = entry['candidate']['id']
            self.assertGreater(float(entry['representations']['audio'][3 + index]), .999)
        self.assertTrue(all(trace['recalls'] == 0 for trace in memory.traces))

    def test_erased_factors_cannot_be_reconstructed_from_matching_routes(self):
        memory = self.memory()
        for number in (0, 1): memory.bank(number).outputs.zero_()
        result = memory.related([packet('image', 0, 3., 2)], 3.)
        self.assertEqual(result['candidate_count'], 2)
        self.assertFalse(result['entries'])
        self.assertEqual({x['reason'] for x in result['skipped']}, {'unlearned_weights'})

    def test_bounded_read_excludes_present_and_warms_only_recalled_sources(self):
        memory = self.memory()
        memory.capture([packet('image', 0, 3., 2)], 3.)
        with patch.object(memory, 'bank', wraps=memory.bank) as reads:
            result = memory.related([packet('image', 0, 3., 2)], 3., exclude=2,
                                    limit=1, read_limit=1, reactivate=True)
        self.assertEqual(reads.call_count, 1)
        chosen = result['entries'][0]['candidate']['id']
        self.assertNotEqual(chosen, 2)
        self.assertEqual([x['recalls'] for x in memory.traces], [int(chosen == 0), int(chosen == 1), 0])

    def test_reactivation_counter_saturates_without_freezing_recency(self):
        memory = self.memory()
        trace = memory.get(0)
        trace.update(recalls=1000000, last_recalled_at=2.)
        memory.related([packet('image', 0, 3., 2)], 3., reactivate=True)
        self.assertEqual(trace['recalls'], 1000000)
        self.assertEqual(trace['last_recalled_at'], 3.)
        from scripts.alice_memory.native_moments import restore as restore_moments
        fresh = restore_moments(memory.snapshot(), 3.)
        self.addCleanup(fresh.close)
        self.assertEqual(fresh.get(0)['recalls'], 1000000)


class ImplicitActivationContracts(unittest.TestCase):
    def native(self, enabled=True):
        native = NativeGrounding(implicit_recall=enabled)
        self.addCleanup(native.moments.close)
        native.observe([packet('image', 0, 1., 0), packet('audio', 3, 1., 0)], 1.)
        native.observe([packet('image', 0, 2., 1), packet('audio', 4, 2., 1)], 2.)
        return native

    def test_unlabelled_experience_automatically_reactivates_without_invented_percepts(self):
        active, baseline = self.native(), self.native(False)
        stimulus = [packet('image', 0, 3., 2)]
        result = active.observe(stimulus, 3.)
        baseline.observe(stimulus, 3.)
        self.assertEqual(set(result['implicit_reactivation']['moments']), {0, 1})
        self.assertEqual(active.observations, 5)
        self.assertEqual(active.moments.next_id, 3)
        self.assertEqual(active.names, [])
        self.assertEqual(active.sources, [])
        self.assertFalse(torch.equal(active.working, baseline.working))
        self.assertEqual(active.moments.get(2)['known'], [True, False, False])
        unheard = active.moments.recall(stimulus, 3., window=(3., 3.), targets=['audio'])
        self.assertEqual(unheard['reason'], 'unobserved_target')
        # Current targets are learned before the new activation enters working state.
        for key in active.dynamics.banks:
            self.assertTrue(torch.equal(active.dynamics.banks[key].weights, baseline.dynamics.banks[key].weights))
        self.assertTrue(torch.equal(active.dynamics.last['values'], baseline.dynamics.last['values']))
        self.assertFalse(torch.equal(active.dynamics.last['context'], baseline.dynamics.last['context']))
        for key in active.links.contextual_banks:
            self.assertTrue(torch.equal(active.links.contextual_banks[key].weights, baseline.links.contextual_banks[key].weights))
        active.attention.configure('learned')
        baseline.attention.configure('learned')
        active.observe([packet('image', 0, 4., 3)], 4.)
        baseline.observe([packet('image', 0, 4., 3)], 4.)
        left = next(iter(active.attention.pending.values()))['key']
        right = next(iter(baseline.attention.pending.values()))['key']
        self.assertFalse(torch.equal(left, right))

    def test_idle_quiet_and_self_output_do_not_run_recollection(self):
        native = self.native()
        before = [x['recalls'] for x in native.moments.traces]
        with patch.object(native.moments, 'related', side_effect=AssertionError('unexpected activation')):
            native.advance(3.)
            native.attention.configure('quiet')
            self.assertEqual(native.observe([packet('image', 0, 4., 2)], 4.)['encoded'], 0)
            self.assertEqual(native.observe([packet('image', 0, 5., 3, 'self')], 5.)['encoded'], 0)
        self.assertEqual([x['recalls'] for x in native.moments.traces], before)

    def test_enabled_checkpoint_restores_state_and_legacy_mode_stays_unchanged(self):
        native = self.native()
        native.observe([packet('image', 0, 3., 2)], 3.)
        state = native.snapshot()
        self.assertEqual(state['format'], 10)
        fresh = restore(state, native.clock)
        self.addCleanup(fresh.moments.close)
        self.assertTrue(fresh.implicit_recall)
        self.assertTrue(torch.equal(native.working, fresh.working))
        stimulus = [packet('image', 0, 4., 3)]
        self.assertEqual(native.observe(stimulus, 4.), fresh.observe(stimulus, 4.))
        self.assertTrue(torch.equal(native.working, fresh.working))
        legacy = self.native(False).snapshot()
        self.assertEqual(legacy['format'], 8)
        older = restore(legacy, 2.)
        self.addCleanup(older.moments.close)
        self.assertFalse(older.implicit_recall)
        for value in (None, 1):
            bad = copy.deepcopy(state)
            bad['implicit_recall'] = value
            with self.assertRaises(ValueError): restore(bad, 3.)

    def test_recall_failure_does_not_reject_an_already_acquired_stimulus(self):
        native = self.native()
        with patch.object(native.moments, 'related', side_effect=ValueError('unreadable source page')):
            result = native.observe([packet('image', 0, 3., 2)], 3.)
        self.assertEqual(result['encoded'], 1)
        self.assertEqual(native.observations, 5)
        self.assertEqual(result['implicit_reactivation']['reason'], 'recall_read_error')

    def test_cross_modal_learning_precedes_two_written_names_for_the_same_experience(self):
        from scripts.alice_memory.grounded_mind import WrittenName
        native = NativeGrounding(implicit_recall=True)
        self.addCleanup(native.moments.close)
        cue = packet('image', 0, 1., 0)
        self.assertFalse(native.associate(cue, 'audio')['supported'])
        for index in range(6):
            axis = index % 2
            native.observe([packet('image', axis, index + 1., index),
                            packet('audio', 3 + axis, index + 1., index)], index + 1.)
        learned = native.associate(cue, 'audio')
        self.assertTrue(learned['supported'], learned)
        self.assertGreater(float(learned['latent'][3]), .99)
        from scripts.alice_memory.native_sensor import NativeObservation
        variation = NativeObservation('image', torch.nn.functional.normalize(
            cue.latent + .02 * torch.nn.functional.one_hot(torch.tensor(127), 128).float(), dim=0),
            6., 0, '0'*64, origin='self')
        generalized = native.associate(variation, 'audio')
        self.assertTrue(generalized['supported'])
        self.assertGreater(float(generalized['latent'][3]), .99)
        self.assertEqual(native.names, [])
        for index, name in ((6, 'nabu'), (7, 'daro')):
            at = float(index + 1)
            native.observe([packet('image', 0, at, index), packet('audio', 3, at, index)], at)
            observations = native.observations
            self.assertTrue(native.teach(WrittenName(name, at, index, origin='person'), at)['learned'])
            self.assertEqual(native.observations, observations)
            self.assertGreater(float(native.evoke(name, 'audio')['latent'][3]), .99)
        self.assertTrue(torch.allclose(native.evoke('nabu', 'audio')['latent'],
                                       native.evoke('daro', 'audio')['latent'], atol=.001))


if __name__ == '__main__':
    torch.set_num_threads(1)
    unittest.main()
