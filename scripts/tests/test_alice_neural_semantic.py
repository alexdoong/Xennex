"""Shared-owner deep hypotheses, evidence revisions, abstention and rollback."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.alice_memory.episodic_memory import EpisodicMemory
from scripts.alice_memory.neural_semantic_memory import NeuralSemanticMemory, restore
from scripts.alice_memory.reactivation_index import restore as restore_index


def cue(values):
    return torch.nn.functional.one_hot(torch.tensor(values), num_classes=4).flatten().double()


class NeuralSemanticContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def source(self, count=1):
        memory = EpisodicMemory(32)
        model = NeuralSemanticMemory(memory)
        for episode in range(count):
            memory.observe(cue((0, 0, 1, 0)), float(episode + 1), True)
            self.assertTrue(model.consolidate(memory, episode, memory.clock)["learned"])
        return memory, model

    def assert_state(self, model, state):
        self.assertTrue(all(torch.equal(value, model.state_dict()[name]) for name, value in state[0].items()))
        self.assertTrue(torch.equal(model.index.generator.get_state(), state[1]))

    def revise(self, memory, field=2, episode=0):
        evidence = torch.tensor([0., 0., 0., 1., 0.])
        trace = memory.traces[episode]
        result = memory.revise(cue((0, 0, 1, 0)), field, evidence, memory.clock + 1., (trace.started, trace.ended))
        self.assertTrue(result["revised"])

    def test_learning_and_reads_use_weights_with_an_explicit_support_gate(self):
        memory, model = self.source(16)
        result = model.predict(cue((0, 0, 0, 0)))
        self.assertTrue(result["supported"])
        self.assertEqual(result["value"], "mae")
        self.assertTrue(result["hypothesis"])
        self.assertFalse(result["confidence_is_calibrated"])
        self.assertEqual(model.index.metrics()["cached_target_values"], 0)
        with torch.no_grad():
            for parameter in model.bank.network.parameters():
                parameter.zero_()
        self.assertFalse(model.predict(cue((0, 0, 0, 0)))["supported"])
        self.assertEqual(model.predict(cue((0, 0, 0, 0)))["distribution"], [0.] * 4)

    def test_duplicate_calls_do_not_retrain_but_new_observations_do(self):
        memory, model = self.source()
        state = model.transaction_state()
        self.assertEqual(model.consolidate(memory, 0, memory.clock)["reason"], "already consolidated")
        self.assert_state(model, state)
        memory.observe(cue((0, 0, 1, 0)), 2., False)
        self.assertEqual(model.pending_sources(), [0])
        self.assertTrue(model.consolidate(memory, 0, 2.)["learned"])
        self.assertGreater(int(model.bank.writes), int(state[0]["bank.writes"]))

    def test_untrained_partial_ambiguous_and_unobserved_cues_abstain(self):
        memory = EpisodicMemory(32)
        model = NeuralSemanticMemory(memory)
        self.assertFalse(model.predict(cue((0, 0, 0, 0)))["supported"])
        memory, model = self.source(16)
        partial = cue((0, 0, 0, 0))
        partial[:4] = 0
        self.assertEqual(model.predict(partial)["reason"], "incomplete cue")
        ambiguous = cue((0, 0, 0, 0))
        ambiguous[:4] = .25
        self.assertEqual(model.predict(ambiguous)["reason"], "ambiguous cue")
        self.assertEqual(model.predict(cue((0, 1, 0, 0)))["reason"], "unobserved cue combination")

    def test_target_in_a_query_cannot_supply_an_answer_or_mutate_input(self):
        memory, model = self.source(16)
        first, second = cue((0, 0, 0, 0)), cue((0, 0, 3, 0))
        saved, state = second.clone(), model.transaction_state()
        self.assertEqual(model.predict(first), model.predict(second))
        self.assertTrue(torch.equal(second, saved))
        self.assert_state(model, state)

    def test_incomplete_or_erased_source_is_deferred_without_false_ledger(self):
        memory = EpisodicMemory(32)
        model = NeuralSemanticMemory(memory)
        partial = cue((0, 0, 1, 0))
        partial[4:8] = 0
        memory.observe(partial, 1., True)
        state = model.transaction_state()
        self.assertFalse(model.consolidate(memory, 0, 1.)["learned"])
        self.assert_state(model, state)
        memory.observe(cue((0, 0, 1, 0)), 2., False)
        memory.blocks[0].banks[6].weights.zero_()
        self.assertEqual(model.consolidate(memory, 0, 2.)["reason"], "unsupported source weights")
        self.assert_state(model, state)

    def test_revision_suspends_hypotheses_and_preserves_initial_interpretation(self):
        memory, model = self.source()
        initial = copy.deepcopy(memory.blocks[0].banks[2].state_dict())
        self.revise(memory)
        self.assertEqual(model.predict(cue((0, 0, 0, 0)))["reason"], "source updates pending")
        self.assertEqual(model.pending_sources(), [0])
        self.assertTrue(model.consolidate(memory, 0, memory.clock)["learned"])
        self.assertEqual(model.pending_sources(), [])
        self.assertEqual(int(model.versions[0]), 1)
        self.assertTrue(all(torch.equal(value, memory.blocks[0].banks[2].state_dict()[name]) for name, value in initial.items()))

    def test_revised_cue_removes_obsolete_support(self):
        memory, model = self.source()
        self.revise(memory, field=3)
        model.consolidate(memory, 0, memory.clock)
        self.assertEqual(model.predict(cue((0, 0, 0, 0)))["reason"], "unobserved cue combination")
        self.assertNotEqual(model.predict(cue((0, 0, 0, 3)))["reason"], "unobserved cue combination")
        restore(model.snapshot(), memory)

    def test_erased_support_or_storage_failure_cannot_return_old_confident_answer(self):
        memory, model = self.source(16)
        with patch("scripts.alice_memory.neural_semantic_memory.source_digest", side_effect=OSError("injected")):
            self.assertEqual(model.predict(cue((0, 0, 0, 0)))["reason"], "source storage unavailable")
        memory.blocks[15].banks[6].weights.zero_()
        self.assertEqual(model.predict(cue((0, 0, 0, 0)))["reason"], "source weights changed")

    def test_source_owner_must_be_the_same_object(self):
        memory, model = self.source()
        other = EpisodicMemory(32)
        other.observe(cue((0, 0, 1, 0)), 1., True)
        state = model.transaction_state()
        with self.assertRaises(ValueError):
            model.consolidate(other, 0, 1.)
        self.assert_state(model, state)

    def test_late_gradient_failure_rolls_back_kernel_routes_sampler_and_ledger(self):
        memory, model = self.source()
        memory.observe(cue((1, 0, 2, 0)), 2., True)
        state = model.transaction_state()
        actual, calls = model.bank.write, []
        def fail(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError("injected")
            return actual(*args, **kwargs)
        with patch.object(model.bank, "write", side_effect=fail), self.assertRaises(RuntimeError):
            model.consolidate(memory, 1, 2.)
        self.assert_state(model, state)

    def test_checkpoint_owns_tensors_and_reproduces_next_write_and_sampler(self):
        memory, model = self.source(4)
        payload = model.snapshot()
        rng = torch.get_rng_state().clone()
        resumed = restore(payload, memory)
        self.assertTrue(torch.equal(rng, torch.get_rng_state()))
        memory.observe(cue((1, 1, 2, 0)), 5., True)
        model.consolidate(memory, 4, 5.)
        resumed.consolidate(memory, 4, 5.)
        self.assert_state(resumed, model.transaction_state())
        resumed.origins.zero_()
        self.assertTrue(payload["ledger"]["origins"].count_nonzero())

    def test_checkpoint_with_deferred_revision_resumes_without_discarding_stale_routes(self):
        memory, model = self.source(4)
        self.revise(memory, episode=3)
        payload = model.snapshot()
        with self.assertRaises(ValueError):
            restore_index(payload["index"], memory)
        resumed = restore(payload, memory)
        self.assertEqual(resumed.pending_sources(), model.pending_sources())
        self.assertFalse(resumed.predict(cue((0, 0, 0, 0)))["supported"])
        episode = model.pending_sources()[0]
        model.consolidate(memory, episode, memory.clock)
        resumed.consolidate(memory, episode, memory.clock)
        self.assert_state(resumed, model.transaction_state())

    def test_checkpoint_rejects_different_source_history_and_future_ledger(self):
        memory, model = self.source()
        other = EpisodicMemory(32)
        other.observe(cue((0, 0, 3, 0)), 1., True)
        rng = torch.get_rng_state().clone()
        with self.assertRaises(ValueError):
            restore(model.snapshot(), other)
        self.assertTrue(torch.equal(rng, torch.get_rng_state()))
        payload = model.snapshot()
        payload["ledger"]["versions"][0] = 1
        with self.assertRaises(ValueError):
            restore(payload, memory)

    def test_same_timestamp_observation_changes_are_pending_and_checkpointable(self):
        memory, model = self.source()
        memory.observe(cue((0, 0, 1, 0)), memory.clock, False)
        self.assertEqual(model.pending_sources(), [0])
        resumed = restore(model.snapshot(), memory)
        self.assertEqual(resumed.pending_sources(), [0])
        model.consolidate(memory, 0, memory.clock)
        resumed.consolidate(memory, 0, memory.clock)
        self.assertEqual(resumed.pending_sources(), [])
        self.assert_state(resumed, model.transaction_state())

    def test_superseded_representative_is_still_a_dependency_after_revision(self):
        memory, model = self.source(16)
        self.assertEqual(int(model.index.episodes[0]), 15)
        self.revise(memory, episode=0)
        self.assertEqual(model.pending_sources(), [0])
        self.assertEqual(model.predict(cue((0, 0, 0, 0)))["reason"], "source updates pending")
        resumed = restore(model.snapshot(), memory)
        self.assertEqual(resumed.pending_sources(), [0])
        resumed.consolidate(memory, 0, memory.clock)
        self.assertEqual(resumed.pending_sources(), [])

    def test_write_budget_failure_preserves_sources_and_uncommitted_ledger(self):
        memory, model = self.source()
        memory.observe(cue((1, 0, 2, 0)), 2., True)
        model.bank.writes.fill_(100000)
        state = model.transaction_state()
        source = copy.deepcopy(memory.blocks[1].state_dict())
        with self.assertRaises(ValueError):
            model.consolidate(memory, 1, memory.clock)
        self.assert_state(model, state)
        self.assertTrue(all(torch.equal(value, memory.blocks[1].state_dict()[name]) for name, value in source.items()))

    def test_new_complete_experience_suspends_hypotheses_until_consolidated(self):
        memory, model = self.source(16)
        self.assertTrue(model.predict(cue((0, 0, 0, 0)))["supported"])
        memory.observe(cue((0, 0, 3, 0)), 17., True)
        self.assertEqual(model.pending_sources(), [16])
        self.assertEqual(model.predict(cue((0, 0, 0, 0)))["reason"], "source updates pending")
        resumed = restore(model.snapshot(), memory)
        self.assertEqual(resumed.pending_sources(), [16])
        model.consolidate(memory, 16, 17.)
        self.assertEqual(model.pending_sources(), [])

    def test_new_incomplete_source_does_not_invent_a_contradictory_target(self):
        memory, model = self.source(16)
        partial = cue((0, 0, 0, 0))
        partial[8:12] = 0
        memory.observe(partial, 17., True)
        self.assertFalse(model.consolidate(memory, 16, 17.)["learned"])
        self.assertEqual(int(model.versions[16]), -1)
        self.assertEqual(model.pending_sources(), [])
        self.assertTrue(model.predict(partial)["supported"])

    def test_bad_route_or_kernel_dimensions_cannot_cross_the_backend_contract(self):
        memory, model = self.source()
        payload = model.snapshot()
        payload["index"]["target"] = 1
        with self.assertRaises(ValueError):
            restore(payload, memory)
        payload = model.snapshot()
        payload["ledger"]["digests"][0, 0] ^= 1
        with self.assertRaises(ValueError):
            restore(payload, memory)


if __name__ == "__main__":
    unittest.main()
