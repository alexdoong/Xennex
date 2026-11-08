"""Lossless pages and exact one-hot value learning; no sensors or LLM needed."""
from __future__ import annotations

import copy
import json
import random
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.alice_memory.paged_memory import PagedMemory
from scripts.alice_memory.episodic_memory import EpisodicMemory
from scripts.alice_memory.diagonal_importance import DiagonalImportance
from scripts.alice_memory.importance import Importance, Consequence
from scripts.alice_memory.episodic_experiment import create, packets
from scripts.alice_memory.episodic_session import EpisodicSession
from scripts.alice_memory.experience_signals import samples
from scripts.alice_memory.memory_actor import MemoryActor, RecallPolicy, train
from scripts.alice_memory.continuous_mind import ContinuousMind
from scripts.alice_memory.temporal32 import Temporal32
from scripts.alice_memory.temporal_mind import TemporalMind
from scripts.alice_memory.consolidating_mind import ConsolidatingMind, save, load
from scripts.alice_memory.process_metrics import Budget


def cue(values=(0, 0, 1, 0)):
    return torch.nn.functional.one_hot(torch.tensor(values), 4).flatten().double()


class PageContracts(unittest.TestCase):
    def memory(self, capacity=8, hot=2):
        value = PagedMemory(capacity, hot)
        self.addCleanup(value.close)
        return value

    def test_cold_pages_equal_resident_fast_weights_and_bounded_cache(self):
        paged, resident = self.memory(8, 1), EpisodicMemory(8)
        for index in range(8):
            value = cue((index % 4, index // 4, (index + 1) % 4, index % 4))
            paged.observe(value, float(index + 1), True)
            resident.observe(value, float(index + 1), True)
        for index in range(8):
            value = resident.blocks[index].addresses[1].flatten().clone()
            value.reshape(4, 4)[2] = 0
            window = (float(index + 1), float(index + 1))
            self.assertEqual(paged.read(value, 8., window=window), resident.read(value, 8., window=window))
            self.assertEqual(len(paged.cache), 1)
            self.assertTrue(all(torch.equal(tensor, paged.block(index).state_dict()[name]) for name, tensor in resident.blocks[index].state_dict().items()))
        self.assertGreater(paged.loads, 0)

    def test_ambiguous_address_abstains_without_loading_a_page(self):
        memory = self.memory()
        for now in (1., 2.):
            memory.observe(cue(), now, True)
        before = memory.loads
        self.assertTrue(memory.read(cue(), 2.)["ambiguous"])
        self.assertEqual(memory.loads, before)

    def test_direct_observation_of_cold_nonlast_episode_survives_eviction(self):
        memory = self.memory(4, 1)
        memory.observe(cue(), 1., True)
        writes = memory.block(0).banks[5].writes.item()
        memory.observe(cue((1, 1, 0, 1)), 2., True)
        untouched = copy.deepcopy(memory.block(1).state_dict())
        memory.observe_at(cue(), 3., 0)
        memory.block(1)
        self.assertEqual(memory.traces[0].observations, 2)
        self.assertEqual(memory.traces[0].ended, 3.)
        self.assertEqual(memory.read(cue(), 3., 'initial')['recall']['impressao'], 'agradavel')
        partial = cue(); partial.reshape(4, 4)[1] = 0
        self.assertEqual(memory.read(partial, 3.)['recall']['impressao'], 'agradavel')
        self.assertEqual(memory.block(0).banks[5].writes.item(), writes * 2)
        self.assertTrue(all(torch.equal(value, memory.block(1).state_dict()[name]) for name, value in untouched.items()))

    def test_batch_rollback_restores_cold_updates_new_pages_and_unsaved_hot_weights(self):
        memory = self.memory(8, 1)
        for index in range(3):
            memory.observe(cue((index, 0, 1, 0)), float(index + 1), True)
        memory.block(2).banks[6].weights.zero_()  # Deliberately not persisted yet.
        before = copy.deepcopy(memory.block(2).state_dict())
        rows = memory.connection.execute('SELECT * FROM episodes ORDER BY id').fetchall()
        metadata = copy.deepcopy(memory.metadata())
        with self.assertRaisesRegex(OSError, 'frame failure'):
            with memory.atomic_observations([0]):
                memory.observe_at(cue((0, 2, 1, 0)), 4., 0)
                memory.observe_at(cue((3, 0, 1, 0)), 4.)
                raise OSError('frame failure')
        self.assertEqual(memory.metadata(), metadata)
        self.assertEqual(memory.connection.execute('SELECT * FROM episodes ORDER BY id').fetchall(), rows)
        self.assertTrue(all(torch.equal(value, memory.block(2).state_dict()[name]) for name, value in before.items()))
        self.assertEqual(memory.read(cue(), 3.)['recall']['impressao'], 'agradavel')

    def test_invalid_direct_address_is_rejected_without_cache_or_clock_changes(self):
        memory = self.memory(4, 1)
        memory.observe(cue(), 1., True)
        before = memory.state_dict()['archive'].clone()
        for address in (True, -1, 1, 0., '0'):
            with self.assertRaises(ValueError):
                memory.observe_at(cue(), 2., address)
        self.assertEqual(memory.clock, 1.)
        self.assertTrue(torch.equal(before, memory.state_dict()['archive']))

    def test_frame_rejects_unreserved_episodes_nested_transactions_and_boolean_addresses(self):
        for memory in (self.memory(), EpisodicMemory(8)):
            memory.observe(cue(), 1., True)
            before = memory.metadata()
            with self.assertRaises(ValueError):
                with memory.atomic_observations([0, True]):
                    pass
            with self.assertRaisesRegex(ValueError, 'reserved'):
                with memory.atomic_observations([]):
                    memory.observe_at(cue(), 2., 0)
            with self.assertRaises(ValueError):
                with memory.atomic_observations([0]):
                    memory.observe_at(cue(), 2., 0)
                    with memory.atomic_observations([0]):
                        pass
            self.assertEqual(memory.metadata(), before)
            self.assertEqual(memory.read(cue(), 1.)['recall']['impressao'], 'agradavel')

    def test_route_cannot_supply_facts_when_neural_weights_are_zero(self):
        memory = self.memory(4, 1)
        memory.observe(cue(), 1., True)
        memory.block(0).banks[6].weights.zero_()
        memory.observe(cue((1, 1, 0, 1)), 2., True)
        partial = cue(); partial.reshape(4, 4)[2] = 0
        result = memory.read(partial, 2., window=(1., 1.))
        self.assertFalse(result["known"][2])
        self.assertNotIn("autor", result["recall"])

    def test_cold_revision_preserves_initial_interpretation_and_dates(self):
        memory = self.memory(4, 1)
        memory.observe(cue(), 1., True)
        memory.observe(cue((1, 1, 0, 1)), 2., True)
        partial = cue(); partial.reshape(4, 4)[2] = 0
        changed = memory.revise(partial, 2, torch.tensor([0., 0., 1., 0., 0.]), 3., (1., 1.))
        self.assertTrue(changed["revised"])
        self.assertEqual(memory.read(partial, 3., "initial", (1., 1.))["recall"]["autor"], "mae")
        self.assertEqual(memory.read(partial, 3., "current", (1., 1.))["recall"]["autor"], "colega")
        self.assertEqual((memory.traces[0].started, memory.traces[0].ended), (1., 1.))

    def test_storage_failure_rolls_back_new_episode(self):
        memory = self.memory()
        memory.observe(cue(), 1., True)
        with patch.object(memory, "persist", side_effect=OSError("injected disk failure")):
            with self.assertRaises(OSError):
                memory.observe(cue((1, 1, 0, 1)), 2., True)
        self.assertEqual(memory.count, 1)
        self.assertEqual(memory.clock, 1.)
        self.assertEqual(memory.connection.execute("SELECT count(*) FROM episodes").fetchone()[0], 1)
        self.assertEqual(memory.read(cue(), 1.)["recall"]["autor"], "mae")

    def test_storage_failure_rolls_back_existing_episode_weights(self):
        memory = self.memory()
        memory.observe(cue(), 1., True)
        before = copy.deepcopy(memory.block(0).state_dict())
        with patch.object(memory, "persist", side_effect=OSError("injected disk failure")):
            with self.assertRaises(OSError):
                memory.observe(cue((1, 1, 0, 1)), 2., False)
        self.assertEqual(memory.clock, 1.)
        self.assertTrue(all(torch.equal(value, memory.block(0).state_dict()[name]) for name, value in before.items()))

    def test_sqlite_budget_failure_rolls_back_the_persisted_transaction(self):
        memory = self.memory(4, 2)
        memory.observe(cue(), 1., True)
        with patch("scripts.alice_memory.paged_memory.MAX_ARCHIVE", 1):
            with self.assertRaisesRegex(ValueError, "storage budget"):
                memory.observe(cue((1, 1, 0, 1)), 2., True)
        self.assertEqual(memory.count, 1)
        self.assertEqual(memory.clock, 1.)
        self.assertEqual(memory.connection.execute("SELECT count(*) FROM episodes").fetchone()[0], 1)
        memory.cache.clear()
        self.assertEqual(memory.read(cue(), 1.)["recall"]["autor"], "mae")

    def test_storage_failure_rolls_back_revision_and_provenance(self):
        memory = self.memory()
        memory.observe(cue(), 1., True)
        with patch.object(memory, "persist", side_effect=OSError("injected disk failure")):
            with self.assertRaises(OSError):
                memory.revise(cue(), 2, torch.tensor([0., 0., 1., 0., 0.]), 2.)
        self.assertEqual(memory.clock, 1.)
        self.assertEqual(memory.revision_log, [])
        self.assertEqual(memory.read(cue(), 1.)["recall"]["autor"], "mae")

    def test_corrupt_cold_page_is_rejected_without_index_fallback(self):
        memory = self.memory(4, 1)
        memory.observe(cue(), 1., True)
        memory.observe(cue((1, 1, 0, 1)), 2., True)
        memory.connection.execute("UPDATE episodes SET page=? WHERE id=0", (b"corrupt",))
        memory.connection.commit()
        with self.assertRaisesRegex(ValueError, "corrupt"):
            memory.read(cue(), 2., window=(1., 1.))

    def test_capacity_stop_preserves_old_experiences(self):
        memory = self.memory(2, 1)
        memory.observe(cue(), 1., True)
        memory.observe(cue(), 2., True)
        with self.assertRaisesRegex(ValueError, "capacity"):
            memory.observe(cue(), 3., True)
        self.assertEqual(memory.clock, 2.)
        self.assertEqual(memory.read(cue(), 2., window=(1., 1.))["episode"], 0)

    def test_clean_eviction_avoids_writes_but_direct_weight_edits_persist(self):
        memory = self.memory(4, 1)
        memory.observe(cue(), 1., True)
        memory.observe(cue((1, 1, 0, 1)), 2., True)
        changes = memory.connection.total_changes
        memory.read(cue(), 2., window=(1., 1.))
        memory.read(cue((1, 1, 0, 1)), 2., window=(2., 2.))
        self.assertEqual(memory.connection.total_changes, changes)
        memory.block(1).banks[6].weights.zero_()
        memory.block(0)
        self.assertEqual(memory.connection.total_changes, changes + 1)
        self.assertNotIn("autor", memory.read(cue((1, 1, 0, 1)), 2., window=(2., 2.))["recall"])

    def test_idle_at_capacity_advances_time_without_loading_neural_pages(self):
        memory = self.memory(2, 1)
        memory.observe(cue(), 1., True)
        memory.observe(cue((1, 1, 0, 1)), 2., True)
        memory.block(0)  # The current episode is deliberately cold.
        loads = memory.loads
        self.assertIsNone(memory.observe(torch.zeros(16, dtype=torch.float64), 3., True))
        self.assertEqual(memory.count, 2)
        self.assertEqual(memory.clock, 3.)
        self.assertEqual(memory.loads, loads)

    def test_diagonal_value_updates_equal_original_dense_rls(self):
        dense, diagonal = Importance(8), DiagonalImportance(8)
        rng = random.Random(17)
        for sequence in range(100):
            episode, field = rng.randrange(8), rng.randrange(4)
            outcome = Consequence(sequence + 1, float(sequence), rng.uniform(-1, 1), rng.uniform(-1, 1), rng.random())
            dense.learn(episode, field, outcome)
            diagonal.learn(episode, field, outcome)
        self.assertTrue(torch.allclose(dense.values.weights, diagonal.values.weights, atol=1e-12, rtol=1e-12))
        self.assertTrue(torch.allclose(dense.values.precision.diag(), diagonal.values.precision, atol=1e-12, rtol=1e-12))
        self.assertEqual(dense.values.writes, diagonal.values.writes)

    def test_old_valuable_page_wins_heat_without_residency_requirement(self):
        memory = self.memory(8, 1)
        importance = DiagonalImportance(8)
        for now in range(1, 9):
            memory.observe(cue(), float(now), True)
        importance.learn(0, 2, Consequence(1, 8., 1., 1., 0.))
        before = memory.loads
        self.assertEqual(importance.rank(memory, cue(), 2, 8.)[0]["episode"], 0)
        self.assertEqual(memory.loads, before)
        self.assertTrue(memory.read(cue(), 8.)["ambiguous"])


class PagedMindContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parent = ROOT / "bin" / "AlicePagedTests"
        parent.mkdir(parents=True, exist_ok=True)
        cls.directory = tempfile.TemporaryDirectory(dir=parent)
        cls.folder = Path(cls.directory.name)
        cls.template, _ = create(17, Budget(100000, 120))
        cls.policy = RecallPolicy()
        train(cls.policy, 1017, Budget(100000, 120))

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def fixture(self):
        memory = PagedMemory(256, 2)
        self.addCleanup(memory.close)
        session = EpisodicSession(self.template.perception, self.template.boundary, memory)
        agent = ConsolidatingMind(TemporalMind(ContinuousMind(MemoryActor(session, self.policy)), Temporal32(), session.perception.state_dict()), forgetting=1.)
        for index in range(5):
            image, sound = samples((index % 4, 0, 1, index % 4), random.Random(index))
            agent.perceive(packets(image, sound, agent.clock + 3., session.steps * 2), 3.)
        agent.consolidate_current()
        return agent

    def test_checkpoint_restores_all_components_after_original_db_is_removed(self):
        agent = self.fixture()
        path = self.folder / "resume.pt"
        save(path, agent)
        resumed = load(path)
        self.addCleanup(resumed.mind.actor.session.memory.close)
        self.assertEqual(agent.tick(.1), resumed.tick(.1))
        self.assertTrue(torch.equal(agent.temporal.hidden, resumed.temporal.hidden))
        self.assertTrue(torch.equal(agent.semantic.bank.weights, resumed.semantic.bank.weights))
        agent.mind.actor.session.memory.close()
        image, sound = samples((0, 0, 1, 0), random.Random(17), (True, True, False, True))
        result = resumed.mind.actor.session.query(packets(image, sound, resumed.clock, 0), window=(3., 3.))
        self.assertEqual(result["recall"]["autor"], "mae")

    def test_fresh_process_needs_only_integrated_checkpoint(self):
        agent = self.fixture()
        path = self.folder / "child.pt"
        save(path, agent)
        agent.mind.actor.session.memory.close()
        child = subprocess.run([sys.executable, "-c",
            "import json,sys,torch;from pathlib import Path;from scripts.alice_memory.consolidating_mind import load;"
            "torch.set_num_threads(2);a=load(Path(sys.argv[1]));a.tick(.1);"
            "print(json.dumps({'clock':a.clock,'episodes':len(a.mind.actor.session.memory.blocks),"
            "'hot':len(a.mind.actor.session.memory.cache),'writes':int(a.semantic.bank.writes)}))", str(path)],
            cwd=ROOT, check=True, capture_output=True, text=True, timeout=30)
        result = json.loads(child.stdout)
        self.assertEqual(result["episodes"], 5)
        self.assertLessEqual(result["hot"], 2)
        self.assertEqual(result["writes"], 15)

    def test_invalid_archive_preserves_callers_rng(self):
        agent = self.fixture()
        path = self.folder / "invalid.pt"
        save(path, agent)
        value = torch.load(path, weights_only=True)
        archive = value["agent"]["mind"]["actor"]["session"]["memory"]["archive"]
        archive[:16].zero_()
        torch.save(value, path)
        before = torch.get_rng_state().clone()
        with self.assertRaises((ValueError, sqlite3.DatabaseError)):
            load(path)
        self.assertTrue(torch.equal(before, torch.get_rng_state()))


if __name__ == "__main__":
    torch.set_num_threads(2)
    unittest.main(verbosity=2)
