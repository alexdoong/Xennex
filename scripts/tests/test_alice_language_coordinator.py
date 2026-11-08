"""Continuity, neural provenance and owned-worker lifecycle during language I/O."""
import copy
import json
import random
import subprocess
import sys
import time
import unittest
from dataclasses import asdict
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import test_alice_word_grounding as word_fixtures
from scripts.alice_memory.episodic_experiment import packets
from scripts.alice_memory.experience_signals import samples
from scripts.alice_memory.grounded_language import learned_digest
from scripts.alice_memory.language_coordinator import LanguageCoordinator, load, save
from scripts.alice_memory.language_process import LanguageProcess


class CoordinatorTests(unittest.TestCase):
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
        self.fixture.perceive(self.agent)
        self.window = (self.agent.clock, self.agent.clock)
        self.folder = word_fixtures.WrittenGroundingTests.folder / self._testMethodName
        self.folder.mkdir()
        self.config = self.folder / "backend.json"
        self.configure()
        self.created = []
        self.coordinator = LanguageCoordinator(self.agent, "http://127.0.0.1:11438", "fixture", self.folder,
                                               self.factory, worker_seconds=10, retry_seconds=.2)
        self.addCleanup(self.coordinator.close)

    def configure(self, mode="normal", delay=0.):
        self.config.write_text(json.dumps({"mode": mode, "delay": delay}), encoding="utf-8")

    def factory(self, operation):
        worker = LanguageProcess(operation, self.folder, 10,
                                 "scripts.tests.alice_fake_language_worker",
                                 {"ALICE_FAKE_LANGUAGE_CONFIG": str(self.config.resolve())})
        self.created.append(worker)
        return worker

    def submit(self):
        return self.coordinator.submit('Quem estava envolvido durante "vimuq" em "torbe"?', window=self.window)

    def until(self, predicate, seconds=12):
        deadline = time.monotonic() + seconds
        while not predicate():
            self.coordinator.tick(.01)
            if time.monotonic() >= deadline:
                self.fail("Language test worker did not reach its bounded condition.")
            time.sleep(.01)

    def revise_author(self, category=1):
        image, sound = samples((0, 0, 2, 1), random.Random(33), (True, False, False, True))
        evidence_image, evidence_sound = samples((0, 0, category, 1), random.Random(34), (False, False, True, False))
        now = self.agent.clock + .1
        self.agent.revise(packets(image, sound, now, 0), packets(evidence_image, evidence_sound, now, 2), 2, .1, self.window)

    def test_ticks_continue_and_language_does_not_teach_facts(self):
        self.configure(delay=.4)
        before = learned_digest(self.agent)
        identifier = self.submit()
        start, steps, observations = self.agent.clock, self.agent.mind.actor.session.steps, self.agent.temporal.observations
        self.until(lambda: self.coordinator.jobs[identifier]["status"] == "completed")
        answer = self.coordinator.take(identifier)
        self.assertEqual(answer["proposal"]["claims"], {"autor": "colega"})
        self.assertGreater(self.agent.clock - start, .5)
        self.assertGreater(self.agent.mind.actor.session.steps - steps, 50)
        self.assertEqual(observations, self.agent.temporal.observations)
        self.assertEqual(before, learned_digest(self.agent))
        self.assertTrue(all(worker.process.poll() == 0 for worker in self.created))

    def test_external_perceptions_continue_during_worker_delay(self):
        self.configure(delay=.5)
        identifier = self.submit()
        self.coordinator.poll()
        episodes, observations = len(self.agent.mind.actor.session.memory.blocks), self.agent.temporal.observations
        image, sound = samples((1, 1, 0, 3), random.Random(19))
        now = self.agent.clock + 3.
        self.coordinator.perceive(packets(image, sound, now, self.agent.mind.actor.session.steps * 2), 3.)
        self.assertGreater(len(self.agent.mind.actor.session.memory.blocks), episodes)
        self.assertEqual(self.agent.temporal.observations, observations + 1)
        self.until(lambda: self.coordinator.jobs[identifier]["status"] == "completed")
        self.assertEqual(self.coordinator.take(identifier)["proposal"]["claims"], {"autor": "colega"})

    def test_revision_during_generation_discards_old_answer_and_refreshes(self):
        self.configure(delay=.4)
        identifier = self.submit()
        self.until(lambda: self.coordinator.jobs[identifier]["status"] == "expressing")
        self.revise_author()
        self.until(lambda: self.coordinator.jobs[identifier]["status"] == "completed")
        answer = self.coordinator.take(identifier)
        self.assertEqual(answer["refreshes"], 1)
        self.assertEqual(answer["proposal"]["claims"], {"autor": "mae"})
        self.assertEqual(len(self.created), 3)

    def test_revision_after_completion_is_rechecked_before_delivery(self):
        identifier = self.submit()
        self.until(lambda: self.coordinator.jobs[identifier]["status"] == "completed")
        self.revise_author()
        self.assertIsNone(self.coordinator.take(identifier))
        self.until(lambda: self.coordinator.jobs[identifier]["status"] == "completed")
        self.assertEqual(self.coordinator.take(identifier)["proposal"]["claims"], {"autor": "mae"})

    def test_resource_deferral_preserves_request_and_retries_after_budget_returns(self):
        self.configure(mode="deferred")
        identifier = self.submit()
        self.until(lambda: self.coordinator.jobs[identifier]["deferrals"] == 1)
        self.assertEqual(self.coordinator.jobs[identifier]["status"], "waiting_parse")
        self.configure()
        self.until(lambda: self.coordinator.jobs[identifier]["status"] == "completed")
        self.assertEqual(self.coordinator.take(identifier)["proposal"]["claims"], {"autor": "colega"})

    def test_cancel_stops_only_the_owned_process_without_answer(self):
        self.configure(delay=5.)
        identifier = self.submit()
        self.coordinator.poll()
        process = self.created[0].process
        self.assertIsNone(process.poll())
        self.coordinator.cancel(identifier)
        self.until(lambda: self.coordinator.active_id is None)
        self.assertIsNotNone(process.poll())
        self.assertEqual(self.coordinator.take(identifier)["status"], "cancelled")

    def test_cancel_cleans_interrupted_atomic_result_inside_owned_exchange_only(self):
        self.configure(delay=5.)
        identifier = self.submit()
        self.coordinator.poll()
        worker = self.created[0]
        leftover = worker.folder / ('result.json.' + 'a' * 32 + '.tmp')
        leftover.write_text('{', encoding='utf-8')
        outside = self.folder / ('result.json.' + 'b' * 32 + '.tmp')
        outside.write_text('preserve', encoding='utf-8')
        self.coordinator.cancel(identifier)
        self.until(lambda: self.coordinator.active_id is None)
        self.assertIsNotNone(worker.process.poll())
        self.assertFalse(worker.folder.exists())
        self.assertEqual(outside.read_text(encoding='utf-8'), 'preserve')

    def test_deadline_is_monotonic_even_when_neural_time_does_not_advance(self):
        self.configure(delay=5.)
        identifier = self.submit()
        self.coordinator.poll()
        worker = self.created[0]
        worker.deadline = time.monotonic() - 1.
        clock = self.agent.clock
        for _ in range(100):
            self.coordinator.poll()
            if self.coordinator.active_id is None:
                break
            time.sleep(.01)
        self.assertIsNotNone(worker.process.poll())
        self.assertEqual(self.agent.clock, clock)
        self.assertIn("worker_deadline", self.coordinator.take(identifier)["error"])

    def test_bounded_queue_preserves_previous_jobs(self):
        for _ in range(4):
            self.submit()
        before = copy.deepcopy(self.coordinator.jobs)
        with self.assertRaises(ValueError):
            self.submit()
        self.assertEqual(self.coordinator.jobs, before)

    def test_wrong_token_oversize_missing_result_and_invented_claim_rejected(self):
        for mode in ("wrong_token", "oversized", "no_result", "invent_claim"):
            self.configure(mode=mode)
            identifier = self.submit()
            self.until(lambda: self.coordinator.jobs[identifier]["status"] == "failed")
            answer = self.coordinator.take(identifier)
            self.assertIsNone(answer["proposal"])
            self.assertTrue(all(worker.process.poll() is not None for worker in self.created))

    def test_checkpoint_requeues_external_work_and_keeps_neural_state(self):
        self.configure(delay=.5)
        identifier = self.submit()
        self.coordinator.poll()
        path = self.folder / "pending.pt"
        save(path, self.coordinator)
        self.coordinator.close()
        restored = load(path, self.folder / "restored", self.factory)
        self.addCleanup(restored.close)
        self.addCleanup(restored.agent.mind.actor.session.memory.close)
        self.assertEqual(restored.jobs[identifier]["status"], "waiting_parse")
        self.assertIsNone(restored.worker)
        self.assertEqual(self.agent.tick(.1), restored.agent.tick(.1))
        self.assertTrue(torch.equal(self.agent.temporal.hidden, restored.temporal.hidden))
        self.assertEqual(learned_digest(self.agent), learned_digest(restored.agent))

    def test_invalid_checkpoint_preserves_rng(self):
        self.submit()
        path = self.folder / "bad.pt"
        save(path, self.coordinator)
        payload = torch.load(path, weights_only=True)
        payload["language"]["jobs"][0]["expires"] = float("nan")
        torch.save(payload, path)
        before = torch.get_rng_state().clone()
        with self.assertRaises(ValueError):
            load(path, self.folder / "bad")
        self.assertTrue(torch.equal(before, torch.get_rng_state()))

    def test_expired_request_stops_live_worker_without_a_proposal(self):
        self.configure(delay=5.)
        identifier = self.submit()
        self.coordinator.poll()
        self.coordinator.unobserved_gap(301.)
        self.until(lambda: self.coordinator.active_id is None)
        answer = self.coordinator.take(identifier)
        self.assertEqual(answer["status"], "failed")
        self.assertEqual(answer["error"], "language_request_expired")
        self.assertIsNone(answer["proposal"])

    def test_completed_worker_exchange_is_removed_by_default(self):
        identifier = self.submit()
        self.until(lambda: self.coordinator.jobs[identifier]["status"] == "completed")
        self.assertTrue(all(not worker.folder.exists() for worker in self.created))
        self.assertEqual(self.coordinator.take(identifier)["proposal"]["claims"], {"autor": "colega"})

    def test_finite_scheduler_saves_format30_and_closes_owned_worker(self):
        from unittest.mock import patch
        from scripts.alice_memory.continuous_experiment import run
        self.configure(delay=5.)
        self.submit()
        path = self.folder / "source.pt"
        save(path, self.coordinator)
        with patch("scripts.alice_memory.continuous_experiment.load_scheduler", return_value=(self.coordinator, self.agent.mind, save)):
            report = run(path, self.folder / "scheduler", steps=5)
        self.assertTrue(report["accepted"])
        self.assertTrue(self.coordinator.closed)
        self.assertTrue(all(worker.process.poll() is not None for worker in self.created))
        payload = torch.load(self.folder / "scheduler" / "mind.pt", weights_only=True)
        self.assertEqual(payload["format"], 30)
        self.assertEqual(payload["language"]["jobs"][0]["status"], "waiting_parse")

    def test_fresh_process_needs_only_checkpoint_for_question_and_memory(self):
        identifier = self.submit()
        path = self.folder / "child.pt"
        save(path, self.coordinator)
        self.coordinator.close()
        self.agent.mind.actor.session.memory.close()
        script = """
import json,sys,time,torch
from pathlib import Path
from scripts.alice_memory.language_coordinator import load
from scripts.alice_memory.language_process import LanguageProcess
torch.set_num_threads(1)
folder=Path(sys.argv[2]);config=folder/'backend.json'
factory=lambda operation: LanguageProcess(operation,folder,10,'scripts.tests.alice_fake_language_worker',{'ALICE_FAKE_LANGUAGE_CONFIG':str(config.resolve())})
a=load(Path(sys.argv[1]),folder,factory)
try:
    for _ in range(1000):
        a.tick(.01)
        r=a.take(1)
        if r is not None:
            print(json.dumps(r));break
        time.sleep(.01)
    else: raise TimeoutError('Child language operation did not complete.')
finally:
    a.close();a.agent.mind.actor.session.memory.close()
"""
        result = subprocess.run([sys.executable, "-c", script, str(path.resolve()), str(self.folder.resolve())],
                                cwd=ROOT, capture_output=True, text=True, check=True, timeout=30)
        answer = json.loads(result.stdout)
        self.assertEqual(answer["id"], identifier)
        self.assertEqual(answer["proposal"]["claims"], {"autor": "colega"})


if __name__ == "__main__":
    torch.set_num_threads(1)
    unittest.main(verbosity=2)
