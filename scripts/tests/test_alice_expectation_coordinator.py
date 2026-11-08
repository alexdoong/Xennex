"""Mixed recall/expectation queue, live worker ownership and checkpoint migration."""
import json
import random
import subprocess
import sys
import time
import unittest
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import test_alice_word_grounding as word_fixtures
from scripts.alice_memory.episodic_experiment import packets
from scripts.alice_memory.experience_signals import samples
from scripts.alice_memory.language_coordinator import LanguageCoordinator, load, save, restore
from scripts.alice_memory.language_process import LanguageProcess
from scripts.alice_memory.language_worker import read_operation
from scripts.alice_memory.neural_semantic_memory import NeuralSemanticMemory


class ExpectationQueueContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        word_fixtures.WrittenGroundingTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        word_fixtures.WrittenGroundingTests.tearDownClass()

    def setUp(self):
        self.fixture = word_fixtures.WrittenGroundingTests()
        self.addCleanup(self.fixture.doCleanups)
        self.agent = self.fixture.fixture()
        for index in range(8):
            activity = index % 2
            self.fixture.perceive(self.agent, (activity, 0, 2 + activity, 1))
            self.agent.consolidate_current()
        self.folder = word_fixtures.WrittenGroundingTests.folder / self._testMethodName
        self.folder.mkdir()
        self.config = self.folder / "backend.json"
        self.configure()
        self.created = []
        self.coordinator = LanguageCoordinator(self.agent, "http://127.0.0.1:11438", "fixture",
                                               self.folder, self.factory, worker_seconds=10, retry_seconds=.1)
        self.addCleanup(self.coordinator.close)
        self.question = 'Quem você esperaria durante "vimuq" em "torbe"?'
        self.assertTrue(self.agent.expect_names(["vimuq", "torbe"], 2)["prediction"]["supported"])

    def configure(self, mode="normal", delay=0.):
        self.config.write_text(json.dumps({"mode": mode, "delay": delay}), encoding="utf-8")

    def factory(self, operation):
        self.assertTrue(all(worker.process.poll() is not None for worker in self.created))
        worker = LanguageProcess(operation, self.folder / "workers", 10, "scripts.tests.alice_fake_language_worker",
                                 {"ALICE_FAKE_LANGUAGE_CONFIG": str(self.config.resolve())})
        self.created.append(worker)
        return worker

    def until(self, predicate):
        deadline = time.monotonic() + 12
        while not predicate():
            if time.monotonic() >= deadline:
                self.fail("Expectation worker did not finish within its finite budget.")
            self.coordinator.tick(.01)
            time.sleep(.01)

    def test_recall_and_expectation_share_one_bounded_queue_without_fact_conversion(self):
        identifiers = [self.coordinator.submit_expectation(self.question),
                       self.coordinator.submit('Quem estava envolvido durante "vimuq" em "torbe"?',
                                               window=(self.agent.clock - 3.1, self.agent.clock - 2.9))]
        before = self.agent.semantic.bank.weights.clone()
        self.until(lambda: all(self.coordinator.jobs[item]["status"] in ("completed", "failed") for item in identifiers))
        expected, recalled = [self.coordinator.take(item) for item in identifiers]
        self.assertEqual(expected["status"], "completed")
        self.assertEqual(expected["proposal"]["expectations"], {"autor": "colega"})
        self.assertEqual(expected["proposal"]["factual_claims"], {})
        self.assertEqual(expected["validation"]["kind"], "learned_expectation")
        self.assertEqual(recalled["status"], "completed")
        self.assertEqual(recalled["proposal"]["claims"], {"autor": "colega"})
        self.assertIsNone(recalled["validation"])
        self.assertTrue(torch.equal(before, self.agent.semantic.bank.weights))

    def test_perceptions_and_ticks_continue_and_compatible_state_update_keeps_answer(self):
        self.configure(delay=.5)
        identifier = self.coordinator.submit_expectation(self.question)
        self.until(lambda: self.coordinator.jobs[identifier]["status"] == "expressing")
        old_state = self.coordinator.jobs[identifier]["evidence"][0]["state_sha256"]
        session = self.agent.mind.actor.session
        old_observations = self.agent.temporal.observations
        old_steps = session.steps
        image, sound = samples((1, 0, 3, 1), random.Random(481))
        self.coordinator.perceive(packets(image, sound, self.agent.clock + .1, session.steps * 2), .1)
        self.until(lambda: self.coordinator.jobs[identifier]["status"] == "completed")
        answer = self.coordinator.take(identifier)
        self.assertEqual(answer["refreshes"], 0)
        self.assertGreater(session.steps, old_steps)
        self.assertEqual(self.agent.temporal.observations, old_observations + 1)
        self.assertNotEqual(old_state, answer["validation"]["evidence"][0]["state_sha256"])
        self.assertEqual(answer["proposal"]["expectations"], {"autor": "colega"})

    def test_removed_support_during_generation_refreshes_to_abstention(self):
        self.configure(delay=.2)
        identifier = self.coordinator.submit_expectation(self.question)
        self.until(lambda: self.coordinator.jobs[identifier]["status"] == "expressing")
        self.agent.semantic.bank.weights.zero_()
        self.until(lambda: self.coordinator.jobs[identifier]["status"] == "completed")
        answer = self.coordinator.take(identifier)
        self.assertEqual(answer["refreshes"], 1)
        self.assertEqual(answer["proposal"]["expectations"], {})
        self.assertTrue(answer["proposal"]["uncertain"])

    def test_delivery_rechecks_support_after_completion(self):
        identifier = self.coordinator.submit_expectation(self.question)
        self.until(lambda: self.coordinator.jobs[identifier]["status"] == "completed")
        self.agent.semantic.bank.weights.zero_()
        self.assertIsNone(self.coordinator.take(identifier))
        self.until(lambda: self.coordinator.jobs[identifier]["status"] == "completed")
        self.assertEqual(self.coordinator.take(identifier)["proposal"]["expectations"], {})

    def test_changed_supported_kernel_value_causes_regeneration(self):
        self.configure(delay=.2)
        identifier = self.coordinator.submit_expectation(self.question)
        self.until(lambda: self.coordinator.jobs[identifier]["status"] == "expressing")
        # Fault/parameter-change control: a current supported value must win over
        # a proposal from old weights. This is not an episode-learning experiment.
        self.agent.semantic.bank.weights[1] = self.agent.semantic.bank.weights[2].clone()
        self.agent.semantic.bank.weights[2].zero_()
        self.until(lambda: self.coordinator.jobs[identifier]["status"] == "completed")
        answer = self.coordinator.take(identifier)
        self.assertEqual(answer["refreshes"], 1)
        self.assertEqual(answer["proposal"]["expectations"], {"autor": "mae"})

    def test_completed_checkpoint_keeps_generation_provenance_and_revalidates_delivery(self):
        identifier = self.coordinator.submit_expectation(self.question)
        self.until(lambda: self.coordinator.jobs[identifier]["status"] == "completed")
        path = self.folder / "completed.pt"
        save(path, self.coordinator)
        restored = load(path, self.folder / "restored", self.factory)
        self.addCleanup(restored.close)
        self.addCleanup(restored.agent.mind.actor.session.memory.close)
        answer = restored.take(identifier)
        self.assertEqual(answer["proposal"]["expectations"], {"autor": "colega"})
        self.assertEqual(answer["validation"]["checked_at"], restored.clock)

    def test_pending_expectation_checkpoint_restarts_only_external_work(self):
        self.configure(delay=.5)
        identifier = self.coordinator.submit_expectation(self.question)
        self.until(lambda: self.coordinator.jobs[identifier]["status"] == "expressing")
        path = self.folder / "pending.pt"
        save(path, self.coordinator)
        payload = torch.load(path, weights_only=True)
        self.assertEqual(payload["format"], 39)
        self.coordinator.close()
        restored = load(path, self.folder / "restored", self.factory)
        self.addCleanup(restored.close)
        self.addCleanup(restored.agent.mind.actor.session.memory.close)
        self.assertEqual(restored.jobs[identifier]["status"], "waiting_expression")
        self.assertEqual(restored.jobs[identifier]["mode"], "expectation")
        self.assertIsNone(restored.worker)
        self.assertEqual(self.agent.tick(.1), restored.agent.tick(.1))
        self.coordinator = restored
        self.until(lambda: restored.jobs[identifier]["status"] == "completed")
        self.assertEqual(restored.take(identifier)["proposal"]["expectations"], {"autor": "colega"})

    def test_format39_is_recognized_by_shared_scheduler_and_evidence_extractor(self):
        from scripts.alice_memory.continuous_experiment import load_scheduler
        from scripts.alice_memory.episodic_language import extract
        from PIL import Image
        from unittest.mock import patch
        from scripts.alice_memory.paged_memory import PagedMemory
        self.coordinator.submit_expectation(self.question)
        path = self.folder / "scheduler.pt"
        save(path, self.coordinator)
        restored, mind, _ = load_scheduler(path)
        self.addCleanup(restored.close)
        self.addCleanup(mind.actor.session.memory.close)
        self.assertEqual(restored.jobs[1]["mode"], "expectation")
        image = self.folder / "cue.png"
        Image.new("RGB", (32, 32)).save(image)
        closed = []
        original = PagedMemory.close
        def close(memory):
            closed.append(memory)
            original(memory)
        with patch.object(PagedMemory, "close", close):
            evidence = extract(path, image, None)
        self.assertEqual(evidence["format"], 1)
        self.assertEqual(len(closed), 1)
        self.assertNotEqual(closed[0], self.agent.mind.actor.session.memory)

    def test_legacy_checkpoint_migrates_factual_jobs_without_mutating_input(self):
        identifier = self.coordinator.submit('Quem estava envolvido durante "vimuq" em "torbe"?')
        path = self.folder / "legacy.pt"
        save(path, self.coordinator)
        payload = torch.load(path, weights_only=True)
        self.assertEqual(payload["format"], 30)
        self.assertNotIn("mode", payload["language"]["jobs"][0])
        restored = restore(payload, self.folder / "restored", self.factory)
        self.addCleanup(restored.close)
        self.addCleanup(restored.agent.mind.actor.session.memory.close)
        self.assertEqual(restored.jobs[identifier]["mode"], "recall")
        self.assertNotIn("mode", payload["language"]["jobs"][0])

    def test_factual_or_invented_expectation_worker_output_is_not_delivered(self):
        for mode in ("expectation_as_fact", "invent_claim", "wrong_token"):
            self.configure(mode=mode)
            identifier = self.coordinator.submit_expectation(self.question)
            self.until(lambda: self.coordinator.jobs[identifier]["status"] == "failed")
            self.assertIsNone(self.coordinator.take(identifier)["proposal"])

    def test_cancel_and_resource_deferral_preserve_owned_lifecycle(self):
        self.configure(mode="deferred")
        identifier = self.coordinator.submit_expectation(self.question)
        self.until(lambda: self.coordinator.jobs[identifier]["deferrals"] == 1)
        self.assertEqual(self.coordinator.jobs[identifier]["status"], "waiting_parse")
        self.configure(delay=.5)
        self.until(lambda: self.coordinator.active_id == identifier)
        worker = self.created[-1]
        self.coordinator.cancel(identifier)
        self.until(lambda: self.coordinator.active_id is None)
        self.assertIsNotNone(worker.process.poll())
        self.assertEqual(self.coordinator.take(identifier)["status"], "cancelled")

    def test_invalid_modes_and_planted_delivery_validation_reject_before_adopting_job(self):
        for changes in ({"mode": "unknown"}, {"mode": "expectation", "view": "initial"},
                        {"mode": "expectation", "window": (self.agent.clock, self.agent.clock)}):
            with self.assertRaises(ValueError):
                self.coordinator.submit(self.question, **changes)
        identifier = self.coordinator.submit_expectation(self.question)
        path = self.folder / "pending.pt"
        save(path, self.coordinator)
        payload = torch.load(path, weights_only=True)
        payload["language"]["jobs"][0]["validation"] = {"kind": "learned_expectation"}
        with self.assertRaises(ValueError):
            restore(payload, self.folder / "invalid", self.factory)

    def test_expectation_worker_rejects_fact_evidence_and_imports_no_neural_runtime(self):
        value = {"format": 1, "token": "a" * 32, "stage": "expectation", "endpoint": "http://127.0.0.1:11438",
                 "model": "fixture", "question": self.question, "view": "current", "required": ["autor"],
                 "evidence": [{"source": "x", "interpretation": "current", "attributes": [["autor", "pai"]], "confidence": .9}]}
        path = self.folder / "operation.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaises(ValueError):
            read_operation(path)
        result = subprocess.run([sys.executable, "-c", "import sys; import scripts.alice_memory.language_worker; assert 'torch' not in sys.modules"],
                                check=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0)

    def pending_neural_source(self):
        memory = self.agent.mind.actor.session.memory
        self.agent.agent.semantic = NeuralSemanticMemory(memory)
        for index, block in enumerate(memory.blocks):
            if bool(block.known[0].all()):
                self.agent.semantic.consolidate(memory, index, self.agent.clock)
        self.fixture.perceive(self.agent, (0, 0, 2, 1))
        self.assertTrue(self.agent.semantic.pending_sources())

    def test_pending_learning_keeps_question_without_spawning_expression_and_factual_queue_advances(self):
        self.pending_neural_source()
        identifier = self.coordinator.submit_expectation(self.question)
        self.until(lambda: self.coordinator.jobs[identifier]["status"] == "waiting_expression")
        self.assertEqual(self.coordinator.jobs[identifier]["error"], "memory_learning_pending")
        self.assertIsNone(self.coordinator.worker)
        factual = self.coordinator.submit('Quem estava durante "vimuq" em "torbe"?')
        self.until(lambda: self.coordinator.jobs[factual]["status"] == "completed")
        self.assertEqual(self.coordinator.jobs[identifier]["refreshes"], 0)
        self.assertFalse(any(worker.stage == "expectation" for worker in self.created))
        self.agent.consolidate_current()
        self.assertEqual(self.agent.semantic.pending_sources(), [])
        self.until(lambda: self.coordinator.jobs[identifier]["status"] == "completed")
        answer = self.coordinator.take(identifier)
        self.assertEqual(answer["refreshes"], 0)
        self.assertEqual(answer["proposal"]["factual_claims"], {})

    def test_pending_learning_still_obeys_deadline_and_survives_checkpoint(self):
        self.pending_neural_source()
        identifier = self.coordinator.submit_expectation(self.question, ttl=5.)
        self.until(lambda: self.coordinator.jobs[identifier]["status"] == "waiting_expression")
        save(self.folder / "learning-pending.pt", self.coordinator)
        restored = load(self.folder / "learning-pending.pt", self.folder / "learning-restored", self.factory)
        self.addCleanup(restored.close)
        self.addCleanup(restored.agent.mind.actor.session.memory.close)
        self.assertTrue(restored.agent.semantic.pending_sources())
        restored.tick(5.1)
        answer = restored.take(identifier)
        self.assertEqual(answer["status"], "failed")
        self.assertEqual(answer["error"], "language_request_expired")
        self.assertIsNone(restored.worker)


if __name__ == "__main__":
    unittest.main(verbosity=2)
