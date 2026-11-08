"""Bounded live capacity growth preserves learned sources and resumes learning."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.alice_memory.episodic_memory import EpisodeTrace, EpisodicMemory
from scripts.alice_memory.diagonal_importance import DiagonalImportance
from scripts.alice_memory.memory_capacity import LEDGER_FIELDS, expand_capacity
from scripts.alice_memory.paged_memory import PagedMemory, restore_archive as restore_pages
from scripts.alice_memory.projected_semantic_memory import ProjectedSemanticMemory, restore as restore_projected
from scripts.alice_memory.reactivation_index import source_digest


def cue(values):
    return torch.nn.functional.one_hot(torch.tensor(values), num_classes=4).flatten().double()


class CapacityContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def fixture(self):
        memory = PagedMemory(2, 1)
        self.addCleanup(memory.close)
        model = ProjectedSemanticMemory(memory)
        for episode in range(2):
            memory.observe(cue((episode, 0, 2, 0)), float(episode + 1), True)
            model.consolidate(memory, episode, memory.clock)
        return memory, model

    def test_full_archive_grows_without_changing_banks_prediction_or_index_and_can_learn(self):
        memory, model = self.fixture()
        old = [source_digest(block) for block in memory.blocks]
        previous = copy.deepcopy(model.snapshot())
        prediction = model.predict(cue((0, 0, 0, 0)))
        cache = list(memory.cache.items())
        result = expand_capacity(memory, model, 8)
        self.assertTrue(result["expanded"])
        self.assertGreater(result["added_tensor_bytes"], 0)
        self.assertEqual((memory.capacity, model.capacity, model.index.source_capacity), (8, 8, 8))
        self.assertEqual(model.predict(cue((0, 0, 0, 0))), prediction)
        self.assertEqual(list(memory.cache.items()), cache)
        for name in LEDGER_FIELDS:
            self.assertTrue(torch.equal(getattr(model, name)[:2], previous["ledger"][name]))
        self.assertEqual(model.versions[2:].tolist(), [-1] * 6)
        for name in LEDGER_FIELDS[1:]:
            self.assertEqual(getattr(model, name)[2:].count_nonzero().item(), 0)
        writes = int(model.bank.writes)
        memory.observe(cue((2, 0, 3, 0)), 3., True)
        self.assertIn(2, model.pending_sources())
        self.assertFalse(model.predict(cue((0, 0, 0, 0)))["supported"])
        self.assertTrue(model.consolidate(memory, 2, memory.clock)["learned"])
        self.assertGreater(int(model.bank.writes), writes)
        self.assertEqual(model.pending_sources(), [])
        self.assertTrue(all(torch.equal(value, source_digest(memory.blocks[i])) for i, value in enumerate(old)))
        self.assertLessEqual(len(memory.cache), memory.hot_limit)

    def test_allocation_failure_leaves_both_owners_and_live_page_views_unchanged(self):
        memory, model = self.fixture()
        old_pool, old_state, rng = memory.pool, copy.deepcopy(model.state_dict()), torch.get_rng_state()
        from scripts.alice_memory.memory_capacity import expanded
        count = 0

        def fail_in_ledger(*args, **kwargs):
            nonlocal count
            count += 1
            if count == len(memory.pool) + 2:
                raise MemoryError("Injected ledger allocation failure")
            return expanded(*args, **kwargs)

        with patch("scripts.alice_memory.memory_capacity.expanded", side_effect=fail_in_ledger):
            with self.assertRaises(MemoryError):
                expand_capacity(memory, model, 8)
        self.assertIs(memory.pool, old_pool)
        self.assertEqual((memory.capacity, model.capacity, model.index.source_capacity), (2, 2, 2))
        self.assertTrue(all(torch.equal(value, model.state_dict()[name]) for name, value in old_state.items()))
        self.assertTrue(torch.equal(rng, torch.get_rng_state()))

    def test_growth_checkpoint_restores_same_owner_and_accepts_another_source(self):
        memory, model = self.fixture()
        expand_capacity(memory, model, 8)
        snapshot = {"metadata": memory.metadata(), "memory": memory.state_dict()}
        resumed = restore_pages(snapshot["memory"], snapshot["metadata"])
        self.addCleanup(resumed.close)
        resumed.traces = [EpisodeTrace(**value) for value in snapshot["metadata"]["traces"]]
        rebuilt = restore_projected(model.snapshot(), resumed)
        self.assertIs(rebuilt._source(), resumed)
        self.assertEqual(rebuilt.capacity, 8)
        resumed.observe(cue((3, 0, 1, 0)), 3., True)
        self.assertTrue(rebuilt.consolidate(resumed, 2, resumed.clock)["learned"])
        self.assertTrue(all(torch.equal(source_digest(a), source_digest(b)) for a, b in zip(memory.blocks, resumed.blocks)))

    def test_invalid_growth_owner_and_open_transaction_refuse_without_mutation(self):
        memory, model = self.fixture()
        for capacity in (1, 4097, True, 3.5):
            with self.assertRaises(ValueError):
                expand_capacity(memory, model, capacity)
        other = PagedMemory(2, 1)
        self.addCleanup(other.close)
        with self.assertRaises(ValueError):
            expand_capacity(other, model, 4)
        with self.assertRaises(ValueError):
            expand_capacity(EpisodicMemory(2), model, 4)
        with memory.atomic_observations((0,)):
            with self.assertRaises(ValueError):
                expand_capacity(memory, model, 4)
        self.assertFalse(expand_capacity(memory, model, 2)["expanded"])
        self.assertEqual(memory.capacity, 2)

    def test_importance_grows_with_source_without_forgetting_value_or_assigning_new_value(self):
        memory, model = self.fixture()
        importance = DiagonalImportance(2)
        importance.values.weights[:, 0] = torch.tensor([.7, .3, .1])
        importance.values.precision[0] = .5
        importance.updates[0, 0] = 1
        importance.last_access[0] = 1.
        durable = importance.durable(0, 0)
        expand_capacity(memory, model, 8, importance)
        self.assertEqual(importance.capacity, 8)
        self.assertEqual(importance.durable(0, 0), durable)
        self.assertEqual(importance.values.precision[0].item(), .5)
        self.assertEqual(importance.values.precision[8:].tolist(), [1000.] * 24)
        self.assertEqual(importance.values.weights[:, 8:].count_nonzero().item(), 0)
        self.assertEqual(importance.last_access[2:].tolist(), [-1.] * 6)
        self.assertEqual(importance.durable(7, 0), 0.)
        importance.rank(memory, cue((0, 0, 0, 0)), 2, memory.clock)

    def test_failure_allocating_importance_does_not_publish_partial_growth(self):
        memory, model = self.fixture()
        importance = DiagonalImportance(2)
        old_pool, old_weights = memory.pool, importance.values.weights
        from scripts.alice_memory.memory_capacity import expanded
        calls = 0

        def fail_in_importance(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == len(memory.pool) + len(LEDGER_FIELDS) + 2:
                raise MemoryError("Injected importance allocation failure")
            return expanded(*args, **kwargs)

        with patch("scripts.alice_memory.memory_capacity.expanded", side_effect=fail_in_importance):
            with self.assertRaises(MemoryError):
                expand_capacity(memory, model, 8, importance)
        self.assertIs(memory.pool, old_pool)
        self.assertIs(importance.values.weights, old_weights)
        self.assertEqual((memory.capacity, model.capacity, importance.capacity), (2, 2, 2))
        with self.assertRaises(ValueError):
            expand_capacity(memory, model, 8, DiagonalImportance(3))


if __name__ == "__main__":
    unittest.main(verbosity=2)
