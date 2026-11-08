"""New written names ground to raw audiovisual concepts and episodic weights."""
from __future__ import annotations

import copy
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.alice_memory.consolidating_mind import ConsolidatingMind
from scripts.alice_memory.continuous_mind import ContinuousMind
from scripts.alice_memory.episodic_experiment import create, packets
from scripts.alice_memory.episodic_session import EpisodicSession
from scripts.alice_memory.experience_signals import samples
from scripts.alice_memory.grounded_mind import GroundedMind, WrittenName, load, save
from scripts.alice_memory.grounded_language import learned_digest
from scripts.alice_memory.memory_actor import MemoryActor, RecallPolicy, train
from scripts.alice_memory.paged_memory import PagedMemory
from scripts.alice_memory.process_metrics import Budget
from scripts.alice_memory.temporal32 import Temporal32
from scripts.alice_memory.temporal_mind import TemporalMind


class WrittenGroundingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parent = ROOT / "bin" / "AliceWordTests"
        parent.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(dir=parent)
        cls.folder = Path(cls.temporary.name)
        cls.template, _ = create(17, Budget(100000, 120))
        cls.policy = RecallPolicy()
        train(cls.policy, 1017, Budget(100000, 120))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def fixture(self, names=True):
        memory = PagedMemory(32, 2)
        self.addCleanup(memory.close)
        session = EpisodicSession(self.template.perception, self.template.boundary, memory)
        base = ContinuousMind(MemoryActor(session, self.policy))
        agent = GroundedMind(ConsolidatingMind(TemporalMind(base, Temporal32(), session.perception.state_dict()), forgetting=1.))
        if names:
            self.teach(agent, "vimuq", 0, 0)
            self.teach(agent, "torbe", 3, 1)
        return agent

    def perceive(self, agent, truth=(0, 0, 2, 1), visible=(True, True, True, True), elapsed=3.):
        session = agent.mind.actor.session
        image, sound = samples(truth, random.Random(session.steps + 500), visible)
        return agent.perceive(packets(image, sound, agent.clock + elapsed, session.steps * 2), elapsed)

    def teach(self, agent, name, field, category):
        values = [0, 0, 0, 0]
        values[field] = category
        mask = tuple(index == field for index in range(4))
        for index in range(8):
            self.perceive(agent, tuple(values), mask, 3. if index == 0 else .2)
            sequence = agent.label_sequence.get("person", -1) + 1
            self.assertTrue(agent.teach_name(WrittenName(name, agent.clock, sequence))["learned"])

    def test_names_have_no_meaning_before_external_pairing(self):
        agent = self.fixture(False)
        self.assertFalse(agent.words.lookup("vimuq")["supported"])
        self.teach(agent, "vimuq", 0, 0)
        learned = agent.words.lookup("vimuq")
        self.assertTrue(learned["supported"])
        self.assertEqual((learned["field"], learned["category"]), (0, 0))
        self.assertFalse(agent.words.lookup("unknown")["supported"])

    def test_later_names_preserve_the_first_without_replay(self):
        agent = self.fixture()
        first = agent.words.lookup("vimuq")
        self.assertEqual((first["field"], first["category"]), (0, 0))
        self.assertEqual((agent.words.lookup("torbe")["field"], agent.words.lookup("torbe")["category"]), (3, 1))
        self.assertEqual(agent.words.updates[:2].tolist(), [8, 8])

    def test_composed_word_cue_recalls_hidden_author_from_episode(self):
        agent = self.fixture()
        self.perceive(agent)
        window = (agent.clock, agent.clock)
        recalled = agent.query_names(["vimuq", "torbe"], window=window)
        self.assertTrue(recalled["grounding_supported"])
        self.assertEqual(recalled["result"]["recall"]["autor"], "colega")
        current, observations, episodes = agent.mind.actor.session.previous.clone(), agent.temporal.observations, len(agent.mind.actor.session.memory.blocks)
        self.assertTrue(agent.request_names(["vimuq", "torbe"], 2, window)["queued"])
        result = agent.tick(.1)
        self.assertEqual(result["action"]["signal"], 2)
        self.assertTrue(torch.equal(current, agent.mind.actor.session.previous))
        self.assertEqual(agent.temporal.observations, observations)
        self.assertEqual(len(agent.mind.actor.session.memory.blocks), episodes)

    def test_surface_index_does_not_supply_meanings_when_neural_weights_are_zero(self):
        agent = self.fixture()
        names = list(agent.words.names)
        agent.words.bank.weights.zero_()
        self.assertEqual(agent.words.names, names)
        self.assertFalse(agent.words.cue(["vimuq", "torbe"])["supported"])
        self.assertFalse(agent.request_names(["vimuq", "torbe"], 2)["queued"])
        self.assertIsNone(agent.mind.task)

    def test_lexical_weights_cannot_replace_an_erased_episodic_author(self):
        agent = self.fixture()
        self.perceive(agent)
        window = (agent.clock, agent.clock)
        agent.mind.actor.session.memory.blocks[-1].banks[6].weights.zero_()
        result = agent.query_names(["vimuq", "torbe"], window=window)["result"]
        self.assertNotIn("autor", result["recall"])
        agent.request_names(["vimuq", "torbe"], 2, window)
        self.assertEqual(agent.tick(.1)["action"]["kind"], "wait")

    def test_conflicting_and_unknown_symbols_do_not_queue_a_task(self):
        agent = self.fixture()
        self.teach(agent, "zarpel", 0, 1)
        self.assertEqual(agent.words.cue(["vimuq", "zarpel"])["reason"], "conflicting_meanings")
        self.assertFalse(agent.request_names(["vimuq", "unknown"], 2)["queued"])
        self.assertIsNone(agent.mind.task)

    def test_self_stale_and_unsynchronized_labels_do_not_teach(self):
        agent = self.fixture(False)
        self.perceive(agent, visible=(True, False, False, False))
        before = copy.deepcopy(agent.words.state_dict())
        self.assertFalse(agent.teach_name(WrittenName("vimuq", agent.clock, 0, "self", 1))["learned"])
        self.assertFalse(agent.teach_name(WrittenName("vimuq", agent.clock - .1, 0))["learned"])
        self.assertTrue(all(torch.equal(value, agent.words.state_dict()[name]) for name, value in before.items()))
        self.assertTrue(agent.teach_name(WrittenName("vimuq", agent.clock, 0))["learned"])
        self.assertFalse(agent.teach_name(WrittenName("torbe", agent.clock, 1))["learned"])
        agent.tick(.1)
        self.assertFalse(agent.teach_name(WrittenName("torbe", agent.clock, 1))["learned"])

    def test_correction_remains_initial_and_current_through_written_cues(self):
        agent = self.fixture()
        self.perceive(agent, truth=(0, 0, 0, 1))
        window = (agent.clock, agent.clock)
        cue_image, cue_sound = samples((0, 0, 0, 1), random.Random(19), (True, True, False, True))
        evidence_image, evidence_sound = samples((0, 0, 1, 1), random.Random(20), (False, False, True, False))
        agent.revise(packets(cue_image, cue_sound, agent.clock + .1, 0),
                     packets(evidence_image, evidence_sound, agent.clock + .1, 2), 2, .1, window)
        self.assertEqual(agent.query_names(["vimuq", "torbe"], "initial", window)["result"]["recall"]["autor"], "pai")
        self.assertEqual(agent.query_names(["vimuq", "torbe"], "current", window)["result"]["recall"]["autor"], "mae")

    def test_checkpoint_retains_pending_word_task_and_next_tick(self):
        agent = self.fixture()
        self.perceive(agent)
        agent.request_names(["vimuq", "torbe"], 2, (agent.clock, agent.clock))
        path = self.folder / "resume.pt"
        save(path, agent)
        restored = load(path)
        self.addCleanup(restored.mind.actor.session.memory.close)
        self.assertEqual(agent.tick(.1), restored.tick(.1))
        self.assertTrue(torch.equal(agent.temporal.hidden, restored.temporal.hidden))
        self.assertTrue(torch.equal(agent.words.bank.weights, restored.words.bank.weights))

    def test_new_process_queries_only_checkpoint_and_written_names(self):
        agent = self.fixture()
        self.perceive(agent)
        path = self.folder / "child.pt"
        window = (agent.clock, agent.clock)
        save(path, agent)
        agent.mind.actor.session.memory.close()
        script = ("import json,sys,torch;from pathlib import Path;"
                  "from scripts.alice_memory.grounded_mind import load;"
                  "torch.set_num_threads(1);a=load(Path(sys.argv[1]));"
                  "r=a.query_names(['vimuq','torbe'],window=tuple(json.loads(sys.argv[2])));"
                  "print(json.dumps(r));a.mind.actor.session.memory.close()")
        result = subprocess.run([sys.executable, "-c", script, str(path), json.dumps(window)],
                                cwd=ROOT, check=True, capture_output=True, text=True, timeout=30)
        self.assertEqual(json.loads(result.stdout)["result"]["recall"]["autor"], "colega")

    def test_invalid_lexical_checkpoint_preserves_rng(self):
        agent = self.fixture()
        path = self.folder / "bad.pt"
        save(path, agent)
        payload = torch.load(path, weights_only=True)
        payload["words"]["source_digest"] = "0" * 64
        torch.save(payload, path)
        before = torch.get_rng_state().clone()
        with self.assertRaises(ValueError):
            load(path)
        self.assertTrue(torch.equal(before, torch.get_rng_state()))

    def test_invalid_time_does_not_discard_attended_teaching_context(self):
        agent = self.fixture(False)
        self.perceive(agent, visible=(True, False, False, False))
        before = agent.context["latent"].clone()
        with self.assertRaises(ValueError):
            agent.tick(-1.)
        self.assertTrue(torch.equal(before, agent.context["latent"]))
        self.assertTrue(agent.teach_name(WrittenName("vimuq", agent.clock, 0))["learned"])

    def test_language_audit_reads_paged_banks_and_detects_actual_weight_changes(self):
        agent = self.fixture()
        self.perceive(agent)
        before = learned_digest(agent)
        agent.query_names(["vimuq", "torbe"], window=(agent.clock, agent.clock))
        agent.tick(.1)
        self.assertEqual(before, learned_digest(agent))
        agent.mind.actor.session.memory.blocks[-1].banks[6].weights.zero_()
        self.assertNotEqual(before, learned_digest(agent))


if __name__ == "__main__":
    torch.set_num_threads(2)
    unittest.main(verbosity=2)
