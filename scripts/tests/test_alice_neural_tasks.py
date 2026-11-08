"""A learned working representation, rather than task text, drives factual recall."""
import copy
import hashlib
import json
import random
import sqlite3
import subprocess
import sys
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import torch
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_alice_word_grounding as word_fixtures
from scripts.alice_memory.continuous_experiment import load_scheduler
from scripts.alice_memory.episodic_experiment import packets
from scripts.alice_memory.experience_signals import samples
from scripts.alice_memory.grounded_language import learned_digest
from scripts.alice_memory.language_input import QuestionPlan, references
from scripts.alice_memory.neural_language import NeuralLanguageCoordinator, load, restore, save
from scripts.alice_memory.neural_task_experiment import decoder_data
from scripts.alice_memory.neural_tasks import TaskModel


class ImmediateParser:
    """Explicit parser test double; no pretrained language-quality claim."""
    def __init__(self, operation):
        self.operation = operation
        self.closed = False

    def poll(self):
        operation = self.operation
        if operation["stage"] != "parse":
            return None
        plan = QuestionPlan("autor", tuple(references(operation["question"])), False, operation["model"], "fixture",
                            hashlib.sha256(operation["question"].encode()).hexdigest(), "1" * 64, 0.)
        value = asdict(plan)
        value["names"] = list(value["names"])
        return {"status": "ready", "value": value}

    def close(self):
        self.closed = True

    def cancel(self):
        self.close()


class NeuralTaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)
        word_fixtures.WrittenGroundingTests.setUpClass()
        torch.manual_seed(61)
        cls.model = TaskModel()
        cue, field, targets = decoder_data(78, 4096, False)
        optimizer = torch.optim.Adam(cls.model.parameters(), lr=.004)
        generator = torch.Generator().manual_seed(91)
        for _ in range(1200):
            index = torch.randint(len(cue), (128,), generator=generator)
            predicted = cls.model.decode(cls.model.encode(cue[index], field[index])).flatten(0, 1)
            loss = F.cross_entropy(predicted, targets[index].flatten())
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
        cls.model.eval().requires_grad_(False)

    @classmethod
    def tearDownClass(cls):
        word_fixtures.WrittenGroundingTests.tearDownClass()

    def setUp(self):
        self.fixture = word_fixtures.WrittenGroundingTests()
        self.addCleanup(self.fixture.doCleanups)
        agent = self.fixture.fixture()
        self.fixture.perceive(agent)
        self.window = (agent.clock, agent.clock)
        self.folder = word_fixtures.WrittenGroundingTests.folder / self._testMethodName
        self.folder.mkdir()
        self.coordinator = NeuralLanguageCoordinator(agent, copy.deepcopy(self.model), "http://127.0.0.1:11438",
                                                     "fixture", self.folder, ImmediateParser)
        self.addCleanup(self.coordinator.close)

    def parsed(self):
        identifier = self.coordinator.submit('Quem estava em "vimuq" em "torbe"?', window=self.window)
        self.coordinator.poll()
        self.coordinator.poll()
        self.assertIsNotNone(self.coordinator.jobs[identifier]["plan"])
        return identifier

    def author(self, identifier):
        evidence = self.coordinator.capture(self.coordinator.jobs[identifier])
        return dict(evidence[0]["attributes"]).get("autor") if evidence else None

    def parse_manually(self, identifier):
        job = self.coordinator.jobs[identifier]
        job["status"] = "parsing"
        operation = {"question": job["question"], "model": "fixture", "stage": "parse"}
        self.assertEqual(self.coordinator.finish(job, ImmediateParser(operation).poll()), "parsed")

    def test_neural_working_cue_recalls_without_reading_names_again(self):
        identifier = self.parsed()
        before = learned_digest(self.coordinator.agent)
        with patch.object(self.coordinator.agent.words, "cue", side_effect=AssertionError("Cue was resent")), \
             patch.object(self.coordinator.agent, "query_names", side_effect=AssertionError("Metadata bypass")):
            self.assertEqual(self.author(identifier), "colega")
            self.coordinator.tick(.1)
            self.assertEqual(self.author(identifier), "colega")
        self.assertEqual(before, learned_digest(self.coordinator.agent))

    def prepare_expectation(self):
        for index in range(6):
            activity = index % 2
            self.fixture.perceive(self.coordinator.agent, truth=(activity, 0, 2 + activity, 1))
            self.coordinator.agent.consolidate_current()
        identifier = self.coordinator.submit_expectation('Quem você esperaria em "vimuq" em "torbe"?')
        self.coordinator.poll()
        self.coordinator.poll()
        return identifier

    def test_neural_working_cue_drives_expectation_without_rereading_textual_names(self):
        identifier = self.prepare_expectation()
        job = self.coordinator.jobs[identifier]
        with patch.object(self.coordinator.agent.words, "cue", side_effect=AssertionError("Cue was resent")), \
             patch.object(self.coordinator.agent, "expect_names", side_effect=AssertionError("Metadata bypass")):
            evidence = self.coordinator.capture(job)
        self.assertEqual(evidence[0]["value"], "colega")
        self.assertEqual(evidence[0]["kind"], "learned_expectation")
        self.coordinator.tasks.slots.zero_()
        self.assertEqual(self.coordinator.capture(job), [])

    def test_neural_expectation_checkpoint_keeps_mode_and_encoded_intention(self):
        identifier = self.prepare_expectation()
        path = self.folder / "expectation.pt"
        save(path, self.coordinator)
        self.coordinator.close()
        restored = load(path, self.folder / "resumed", ImmediateParser)
        self.addCleanup(restored.close)
        self.addCleanup(restored.agent.mind.actor.session.memory.close)
        self.assertEqual(restored.jobs[identifier]["mode"], "expectation")
        self.assertTrue(torch.equal(restored.tasks.slots, self.coordinator.tasks.slots))
        self.assertEqual(restored.capture(restored.jobs[identifier])[0]["value"], "colega")

    def test_question_state_survives_new_scene_and_idle_without_external_counts(self):
        identifier = self.parsed()
        slots = self.coordinator.tasks.slots.clone()
        old_scene = self.coordinator.agent.mind.actor.session.previous.clone()
        self.fixture.perceive(self.coordinator, truth=(1, 1, 0, 2))
        self.assertFalse(torch.equal(old_scene, self.coordinator.agent.mind.actor.session.previous))
        observations = self.coordinator.temporal.observations
        episodes = len(self.coordinator.mind.actor.session.memory.blocks)
        with patch.object(self.coordinator.tasks.model, "encode", side_effect=AssertionError("Request re-encoded")):
            for _ in range(100):
                self.coordinator.tick(.1)
        self.assertTrue(torch.equal(slots, self.coordinator.tasks.slots))
        self.assertEqual(self.coordinator.temporal.observations, observations)
        self.assertEqual(len(self.coordinator.mind.actor.session.memory.blocks), episodes)
        self.assertEqual(self.author(identifier), "colega")

    def test_neural_question_orients_internal_evocation_and_functional_demand(self):
        identifier = self.parsed()
        self.fixture.perceive(self.coordinator, truth=(1, 1, 0, 2))
        mind = self.coordinator.mind
        physical = mind.actor.session.previous.clone()
        observations = self.coordinator.temporal.observations
        digest = learned_digest(self.coordinator.agent)
        mind.next_evocation = 0.
        response = self.coordinator.tick(.1)
        self.assertEqual(response["cognitive_attention"]["job"], identifier)
        self.assertEqual(response["evoked"]["content"]["recall"]["autor"], "colega")
        self.assertGreaterEqual(mind.internal.activation, .4)
        self.assertTrue(torch.equal(physical, mind.actor.session.previous))
        self.assertEqual(self.coordinator.temporal.observations, observations)
        self.assertEqual(digest, learned_digest(self.coordinator.agent))

    def test_zero_weights_or_slot_remove_recall_despite_metadata(self):
        identifier = self.parsed()
        self.assertEqual(self.author(identifier), "colega")
        slots = self.coordinator.tasks.slots.clone()
        self.coordinator.tasks.slots.zero_()
        self.assertIsNone(self.author(identifier))
        self.coordinator.tasks.slots.copy_(slots)
        for value in self.coordinator.tasks.model.parameters():
            value.zero_()
        self.assertIsNone(self.author(identifier))

    def test_erased_episodic_author_not_supplied_by_working_slot(self):
        identifier = self.parsed()
        self.assertEqual(self.author(identifier), "colega")
        memory = self.coordinator.mind.actor.session.memory
        grounding = self.coordinator.agent.query_names(["vimuq", "torbe"], window=self.window)
        episode = grounding["result"]["episode"]
        memory.blocks[episode].banks[6].weights.zero_()
        self.assertIsNone(self.author(identifier))

    def test_unknown_symbol_abstains_and_cancel_releases_only_own_slot(self):
        known = self.parsed()
        unknown = self.coordinator.submit('Quem estava em "estranho"?', window=self.window)
        self.assertFalse(self.coordinator.tasks.decode(unknown)["supported"])
        slot = self.coordinator.tasks.slots[self.coordinator.tasks.index(known)].clone()
        self.coordinator.cancel(unknown)
        self.assertIsNone(self.coordinator.tasks.index(unknown))
        self.assertTrue(torch.equal(slot, self.coordinator.tasks.slots[self.coordinator.tasks.index(known)]))

    def test_external_revision_preserves_initial_and_changes_current_neural_query(self):
        current = self.parsed()
        initial = self.coordinator.submit('Quem estava em "vimuq" em "torbe"?', view="initial", window=self.window)
        self.parse_manually(initial)
        image, sound = samples((0, 0, 2, 1), random.Random(33), (True, False, False, True))
        revised_image, revised_sound = samples((0, 0, 1, 1), random.Random(34), (False, False, True, False))
        now = self.coordinator.clock + .1
        self.coordinator.agent.revise(packets(image, sound, now, 0), packets(revised_image, revised_sound, now, 2), 2, .1, self.window)
        self.assertEqual(self.author(current), "mae")
        self.assertEqual(self.author(initial), "colega")

    def test_permuted_working_slots_break_correct_target_recall(self):
        first = self.parsed()
        self.fixture.teach(self.coordinator.agent, "vemru", 0, 1)
        self.fixture.perceive(self.coordinator, truth=(1, 1, 0, 2))
        second_window = (self.coordinator.clock, self.coordinator.clock)
        second = self.coordinator.submit('Quem estava em "vemru"?', window=second_window)
        self.parse_manually(second)
        self.assertEqual((self.author(first), self.author(second)), ("colega", "pai"))
        left, right = self.coordinator.tasks.index(first), self.coordinator.tasks.index(second)
        saved = self.coordinator.tasks.slots[left].clone()
        self.coordinator.tasks.slots[left] = self.coordinator.tasks.slots[right]
        self.coordinator.tasks.slots[right] = saved
        self.assertNotEqual((self.author(first), self.author(second)), ("colega", "pai"))

    def test_context_priority_changes_with_scene_and_fifo_preserves_order(self):
        first = self.coordinator.submit('Quem estava em "vimuq"?', window=self.window)
        second = self.coordinator.submit('Quem estava em "torbe"?', window=self.window)
        waiting = list(self.coordinator.jobs.values())
        contexts = []
        for truth in ((0, 0, 2, 2), (1, 0, 2, 1)):
            for frame in range(3):
                self.fixture.perceive(self.coordinator.agent, truth=truth, elapsed=3. if frame == 0 else .2)
            contexts.append(self.coordinator.temporal.hidden.clone())
        slots = self.coordinator.tasks
        queries = torch.stack((slots.slots[slots.index(first)], slots.slots[slots.index(second)]))
        signals = torch.cat((contexts[0].repeat(2, 1), contexts[1].repeat(2, 1)))
        labels = torch.tensor([1., 0., 0., 1.])
        for value in slots.model.priority.parameters():
            value.requires_grad_(True)
        optimizer = torch.optim.Adam(slots.model.priority.parameters(), lr=.02)
        for _ in range(300):
            loss = F.binary_cross_entropy_with_logits(slots.model.score(queries.repeat(2, 1), signals), labels)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
        slots.model.requires_grad_(False)
        self.coordinator.temporal.hidden = contexts[0]
        self.assertEqual(self.coordinator.choose_waiting(waiting)["id"], first)
        self.coordinator.temporal.hidden = contexts[1]
        self.assertEqual(self.coordinator.choose_waiting(waiting)["id"], second)
        self.coordinator.attention_mode = "fifo"
        self.assertEqual(self.coordinator.choose_waiting(waiting)["id"], first)

    def test_snapshot_restore_next_tick_and_cue_exact_without_live_worker(self):
        identifier = self.parsed()
        path = self.folder / "mind.pt"
        save(path, self.coordinator)
        loaded = load(path, self.folder / "resumed", ImmediateParser)
        self.addCleanup(loaded.close)
        self.addCleanup(loaded.mind.actor.session.memory.close)
        self.assertIsNone(loaded.worker)
        self.assertTrue(torch.equal(loaded.tasks.slots, self.coordinator.tasks.slots))
        self.assertEqual(loaded.capture(loaded.jobs[identifier]), self.coordinator.capture(self.coordinator.jobs[identifier]))
        original = self.coordinator.tick(.1)
        resumed = loaded.tick(.1)
        self.assertEqual(original["action"], resumed["action"])
        self.assertTrue(torch.equal(loaded.temporal.hidden, self.coordinator.temporal.hidden))

    def test_restore_rejects_wrong_source_shape_or_owner(self):
        self.parsed()
        path = self.folder / "mind.pt"
        save(path, self.coordinator)
        payload = torch.load(path, weights_only=True)
        for kind in ("source", "shape", "owner", "nan"):
            with self.subTest(kind=kind):
                bad = copy.deepcopy(payload)
                if kind == "source":
                    bad["tasks"]["source"]["perception"] = "0" * 64
                elif kind == "shape":
                    bad["tasks"]["slots"] = torch.zeros(4, 31)
                elif kind == "owner":
                    bad["tasks"]["identifiers"][0] = 900
                else:
                    bad["tasks"]["slots"][0, 0] = float("nan")
                with self.assertRaises(ValueError):
                    restore(bad, self.folder / "invalid")

    def test_scheduler_and_fresh_process_load_neural_format(self):
        identifier = self.parsed()
        path = self.folder / "mind.pt"
        save(path, self.coordinator)
        loaded, _, _ = load_scheduler(path)
        self.addCleanup(loaded.close)
        self.addCleanup(loaded.mind.actor.session.memory.close)
        self.assertIsInstance(loaded, NeuralLanguageCoordinator)
        script = """
import json,sys,torch
from pathlib import Path
from scripts.alice_memory.neural_language import load
torch.set_num_threads(1)
a=load(Path(sys.argv[1]),Path(sys.argv[2]))
print(json.dumps({'evidence':a.capture(a.jobs[int(sys.argv[3])]),'worker':a.worker is None,'slots':a.tasks.slots.tolist()}))
a.close();a.mind.actor.session.memory.close()
"""
        result = subprocess.run([sys.executable, "-c", script, str(path), str(self.folder / "child"), str(identifier)],
                                cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        parsed = json.loads(result.stdout)
        self.assertTrue(parsed["worker"])
        self.assertEqual(dict(parsed["evidence"][0]["attributes"])["autor"], "colega")
        self.assertEqual(parsed["slots"], self.coordinator.tasks.slots.tolist())

    def test_invalid_rng_preserves_global_state_and_failed_restore_closes_memory(self):
        self.parsed()
        path = self.folder / "mind.pt"
        save(path, self.coordinator)
        payload = torch.load(path, weights_only=True)
        bad = copy.deepcopy(payload)
        bad["agent"]["torch_rng"][0] ^= 1
        before = torch.get_rng_state().clone()
        with self.assertRaises(ValueError):
            restore(bad, self.folder / "bad-rng")
        self.assertTrue(torch.equal(before, torch.get_rng_state()))
        from scripts.alice_memory import neural_language
        original = neural_language.restore_base
        created = []
        def observe_base(*args):
            result = original(*args)
            created.append(result)
            return result
        bad = copy.deepcopy(payload)
        bad["tasks"]["source"]["temporal"] = "0" * 64
        with patch.object(neural_language, "restore_base", side_effect=observe_base):
            with self.assertRaises(ValueError):
                restore(bad, self.folder / "bad-source")
        self.assertTrue(created[0].closed)
        with self.assertRaises(sqlite3.ProgrammingError):
            created[0].mind.actor.session.memory.connection.execute("SELECT 1")


if __name__ == "__main__":
    unittest.main()
