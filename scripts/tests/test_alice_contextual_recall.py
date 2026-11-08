"""Sourced online relevance feedback and episode-bound neural context state."""
import copy
import hashlib
import sys
import unittest
from pathlib import Path

import torch
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.alice_memory.importance import Consequence
from scripts.alice_memory.native_grounding import NativeGrounding, restore
from scripts.alice_memory.native_moments import NativeMoments
from scripts.alice_memory.native_reactivation import activate
from scripts.alice_memory.native_sensor import NativeObservation


def packet(modality, axis, at, sequence):
    return NativeObservation(modality, F.one_hot(torch.tensor(axis), 128).float(), at, sequence,
                             hashlib.sha256(str((modality, axis)).encode()).hexdigest())


class ContextualRecallContracts(unittest.TestCase):
    def native(self, capacity=16):
        native = NativeGrounding(implicit_recall=True)
        native.moments.close()
        native.moments = NativeMoments(capacity, min(4, capacity))
        self.addCleanup(native.moments.close)
        native.observe([packet('image', 1, 1., 0), packet('audio', 2, 1., 0)], 1.)
        before = native.working.clone()
        native.observe([packet('image', 0, 1.1, 1), packet('audio', 3, 1.1, 1)], 1.1)
        self.assertTrue(torch.allclose(native.recall_context.read(1).float(), before, atol=1e-6))
        return native

    def activate(self, native):
        return activate(native, [packet('image', 0, native.clock, 0)], native.clock, None)

    def test_feedback_uses_actual_evocation_once_without_rewriting_facts(self):
        native = self.native()
        result = self.activate(native)
        number = result['recall_choice']
        self.assertIsNotNone(number)
        state = native.moments.bank(1).outputs.clone()
        counts = native.observations, native.moments.next_id
        outcome = Consequence(number, native.clock, 1., 0., 0., origin='person')
        self.assertTrue(native.learn_recall_preference(outcome)['learned'])
        self.assertFalse(native.learn_recall_preference(outcome)['learned'])
        self.assertEqual(int(native.recall_preference.bank.writes), 1)
        self.assertTrue(torch.equal(state, native.moments.bank(1).outputs))
        self.assertEqual(counts, (native.observations, native.moments.next_id))
        self.assertEqual(native.names, [])

    def test_unknown_expired_and_self_feedback_cannot_train_relevance(self):
        native = self.native()
        token = self.activate(native)['recall_choice']
        with self.assertRaises(ValueError):
            native.learn_recall_preference(Consequence(token, native.clock, 1., 0., 0., origin='self'))
        self.assertFalse(native.learn_recall_preference(Consequence(token + 50, native.clock, 1., 0., 0.))['learned'])
        native.advance(native.clock + 61.)
        self.assertFalse(native.learn_recall_preference(Consequence(token, native.clock, 1., 0., 0.))['learned'])
        self.assertEqual(int(native.recall_preference.bank.writes), 0)

    def test_pending_feedback_survives_restore_and_remains_single_use(self):
        native = self.native()
        token = self.activate(native)['recall_choice']
        state = native.snapshot()
        self.assertEqual(state['format'], 10)
        fresh = restore(state, native.clock)
        self.addCleanup(fresh.moments.close)
        feedback = Consequence(token, native.clock, -1., 0., 0.)
        self.assertTrue(fresh.learn_recall_preference(feedback)['learned'])
        again = restore(fresh.snapshot(), fresh.clock)
        self.addCleanup(again.moments.close)
        self.assertFalse(again.learn_recall_preference(feedback)['learned'])
        self.assertTrue(torch.equal(fresh.recall_preference.bank.weights, again.recall_preference.bank.weights))

    def test_unanswered_recollections_do_not_starve_recent_feedback(self):
        native = self.native()
        tokens = [self.activate(native)['recall_choice'] for _ in range(40)]
        self.assertTrue(all(type(token) is int for token in tokens))
        self.assertEqual(len(native.recall_preference.pending), 16)
        self.assertEqual(int(native.recall_preference.bank.writes), 0)
        fresh = restore(native.snapshot(), native.clock)
        self.addCleanup(fresh.moments.close)
        self.assertFalse(fresh.learn_recall_preference(Consequence(tokens[0], fresh.clock, 1., 0., 0.))['learned'])
        self.assertTrue(fresh.learn_recall_preference(Consequence(tokens[-1], fresh.clock, 1., 0., 0.))['learned'])
        self.assertEqual(int(fresh.recall_preference.bank.writes), 1)

    def test_old_policy_read_rule_is_preserved_and_new_rule_is_versioned(self):
        native = self.native()
        state = native.snapshot()
        self.assertEqual(state['recall_preference']['format'], 3)
        self.assertEqual(state['recall_preference']['read_rule'], 'variance-damped-v2')
        old = copy.deepcopy(state)
        old['recall_preference']['format'] = 1
        del old['recall_preference']['read_rule']
        fresh = restore(old, native.clock)
        self.addCleanup(fresh.moments.close)
        self.assertEqual(fresh.recall_preference.read_rule, 'covered-linear-v1')
        self.assertEqual(fresh.snapshot()['recall_preference']['read_rule'], 'covered-linear-v1')
        state['recall_preference']['read_rule'] = 'unknown'
        with self.assertRaises(ValueError): restore(state, native.clock)

    def test_held_conversation_credit_survives_passive_burst_without_extending_its_expiry(self):
        native = self.native()
        token = self.activate(native)['recall_choice']
        native.recall_preference.hold(token)
        for _ in range(40): self.activate(native)
        self.assertEqual(len(native.recall_preference.pending), 16)
        fresh = restore(native.snapshot(), native.clock)
        self.addCleanup(fresh.moments.close)
        self.assertTrue(fresh.recall_preference.pending[token]['held'])
        self.assertTrue(fresh.learn_recall_preference(Consequence(token, fresh.clock, 1., 0., 0.))['learned'])
        native.advance(native.clock + 61.)
        self.assertFalse(native.learn_recall_preference(Consequence(token, native.clock, 1., 0., 0.))['learned'])

    def test_retirement_and_disabled_activation_preserve_context_addresses(self):
        native = self.native(3)
        old = native.recall_context.read(1).clone()
        native.configure_implicit_recall(False)
        for at, sequence in ((2., 2), (3., 3), (4., 4)):
            native.observe([packet('image', 10 + sequence, at, sequence)], at)
        self.assertEqual(native.recall_context.ids, [x['id'] for x in native.moments.traces])
        if native.moments.get(1) is not None:
            self.assertTrue(torch.equal(native.recall_context.read(1), old))
        fresh = restore(native.snapshot(), native.clock)
        self.addCleanup(fresh.moments.close)
        self.assertFalse(fresh.implicit_recall)
        self.assertTrue(torch.equal(native.recall_context.weights, fresh.recall_context.weights))

    def test_missing_old_context_is_not_filled_by_current_situation(self):
        native = NativeGrounding()
        self.addCleanup(native.moments.close)
        native.observe([packet('image', 0, 1., 0)], 1.)
        native.configure_implicit_recall(True)
        old = restore(native.snapshot(), native.clock)
        self.addCleanup(old.moments.close)
        self.assertIsNone(old.recall_context)
        old.observe([packet('image', 1, 2., 1)], 2.)
        self.assertIsNone(old.recall_context.read(0))
        with self.assertRaises(ValueError): old.recall_context.capture(old.moments, 0, old.working)

    def test_corrupt_context_policy_and_captured_credit_are_rejected(self):
        native = self.native()
        token = self.activate(native)['recall_choice']
        state = native.snapshot()
        for mutate in (lambda x: x['recall_context']['weights'][0].fill_(1.),
                       lambda x: x['recall_context']['ids'].reverse(),
                       lambda x: x['recall_preference']['bank']['precision'].zero_(),
                       lambda x: x['recall_preference']['pending'][token]['key'].zero_(),
                       lambda x: x['recall_preference']['pending'][token]['moment_ref'].update(id=0)):
            damaged = copy.deepcopy(state)
            mutate(damaged)
            with self.assertRaises(ValueError): restore(damaged, native.clock)


if __name__ == '__main__':
    torch.set_num_threads(1)
    unittest.main()
