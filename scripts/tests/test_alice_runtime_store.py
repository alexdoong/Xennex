"""Detached persistence, file ownership, failed commits and genuine restart."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_alice_word_grounding as fixtures
from scripts.alice_memory.continuous_experiment import load_scheduler
from scripts.alice_memory.persistent_runtime import advance, run
from scripts.alice_memory.runtime_snapshot import capture, freeze
from scripts.alice_memory.runtime_store import RuntimeLease, RuntimeStore, atomic_json
from scripts.alice_memory.loop_checkpoint import atomic_write


class RuntimeStoreContracts(unittest.TestCase):
    def test_implicit_mode_survives_runtime_restart_without_language_or_new_perception(self):
        from scripts.alice_memory.persistent_runtime import close_agent
        source = self.root / 'implicit-source.pt'
        fixtures.save(source, self.agent)
        folder = self.root / 'implicit-runtime'
        for enabled in (True, None, False):
            report = run(folder, source, seconds=.3, native_implicit_recall=enabled)
            self.assertEqual(report['phase'], 'stopped')
            pointer = json.loads((folder / 'current.json').read_text(encoding='utf-8'))
            core, mind, _ = load_scheduler(folder / pointer['current']['file'])
            try:
                self.assertEqual(core.native.implicit_recall, enabled is not False)
                self.assertEqual(core.native.observations, 0)
            finally:
                close_agent(core, mind)
        with self.assertRaises(ValueError): run(self.root / 'invalid-mode', source, native_implicit_recall='yes')
        self.assertFalse((self.root / 'invalid-mode').exists())

    @classmethod
    def setUpClass(cls):
        fixtures.WrittenGroundingTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixtures.WrittenGroundingTests.tearDownClass()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT / "bin")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.fixture = fixtures.WrittenGroundingTests()
        self.addCleanup(self.fixture.doCleanups)
        self.agent = self.fixture.fixture()
        self.fixture.perceive(self.agent, (0, 0, 2, 1))
        self.agent.consolidate_current()

    def store(self):
        store = RuntimeStore(self.root)
        self.addCleanup(store.close)
        return store

    def restored(self, path):
        agent, mind, _ = load_scheduler(path, self.root / "workers")
        self.addCleanup(mind.actor.session.memory.close)
        return agent

    def test_writer_never_reads_living_tensors_and_busy_save_does_not_queue_more_copies(self):
        store = self.store()
        payload = capture(self.agent)
        observed = self.agent.temporal.observations
        clock = self.agent.clock
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        original = store.commit

        def delayed(*args):
            entered.set()
            self.assertTrue(release.wait(5))
            return original(*args)

        with patch.object(store, "commit", side_effect=delayed):
            self.assertTrue(store.submit(payload, clock))
            self.assertTrue(entered.wait(3))
            self.assertFalse(store.submit(payload, clock))
            self.fixture.perceive(self.agent, (1, 0, 3, 1))
            for _ in range(10):
                self.agent.tick(.1)
            self.assertGreater(self.agent.clock, clock)
            release.set()
            self.assertEqual(store.finish()["status"], "committed")
        restored = self.restored(store.candidates()[0][0])
        self.assertEqual(restored.clock, clock)
        self.assertEqual(restored.temporal.observations, observed)
        self.assertNotEqual(restored.temporal.observations, self.agent.temporal.observations)

    def test_commit_failure_keeps_last_pointer_and_a_later_commit_retains_only_two_generations(self):
        store = self.store()
        store.submit(capture(self.agent), self.agent.clock)
        self.assertEqual(store.finish()["status"], "committed")
        before = (self.root / "current.json").read_bytes()
        with patch("scripts.alice_memory.runtime_store.atomic_json", side_effect=OSError("Injected commit failure")):
            store.submit(capture(self.agent), self.agent.clock)
            self.assertEqual(store.finish()["status"], "failed")
        self.assertEqual((self.root / "current.json").read_bytes(), before)
        for _ in range(3):
            self.agent.tick(.1)
            store.submit(capture(self.agent), self.agent.clock)
            self.assertEqual(store.finish()["status"], "committed")
        self.assertEqual(len(list(self.root.glob("alice-*.pt"))), 2)
        self.assertIsNone(store.last_error)

    def test_corrupt_current_recovers_previous_and_preserves_it_on_next_commit(self):
        store = self.store()
        store.submit(capture(self.agent), self.agent.clock)
        store.finish()
        first = dict(store.manifest["current"])
        self.agent.tick(.1)
        store.submit(capture(self.agent), self.agent.clock)
        store.finish()
        store.path(store.manifest["current"]["file"]).write_bytes(b"corrupted")
        candidates = store.candidates()
        self.assertEqual(candidates[0][1], first)
        self.assertTrue(store.recovery_errors)
        restored = self.restored(candidates[0][0])
        self.assertEqual(restored.clock, first["clock"])
        store.use_recovered(first)
        store.submit(capture(restored), restored.clock)
        store.finish()
        self.assertEqual(store.manifest["previous"], first)
        self.assertEqual(len(store.candidates()), 2)

    def test_crashed_lease_owner_releases_os_lock_without_deleting_another_process_file(self):
        ready = self.root / "ready.txt"
        code = "from pathlib import Path; import time; from scripts.alice_memory.runtime_store import RuntimeLease; lease=RuntimeLease(Path(%r)); Path(%r).write_text('ready'); time.sleep(30)" % (str(self.root), str(ready))
        child = subprocess.Popen([sys.executable, "-c", code], cwd=ROOT, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                 creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        self.addCleanup(lambda: child.kill() if child.poll() is None else None)
        deadline = time.monotonic() + 10
        while not ready.exists() and time.monotonic() < deadline and child.poll() is None:
            time.sleep(.01)
        self.assertTrue(ready.exists())
        with self.assertRaises(OSError):
            RuntimeLease(self.root)
        child.kill()
        child.communicate(timeout=5)
        with RuntimeLease(self.root):
            self.assertTrue(ready.exists())

    def test_manifest_rejects_path_traversal_duplicate_generations_and_unbounded_values(self):
        store = self.store()
        store.submit(capture(self.agent), self.agent.clock)
        store.finish()
        manifest = json.loads((self.root / "current.json").read_text())
        for field, value in (("file", "../weights.pt"), ("size", 80_000_001), ("clock", True), ("captured_wall", float("inf"))):
            altered = json.loads(json.dumps(manifest))
            altered["current"][field] = value
            (self.root / "current.json").write_text(json.dumps(altered), encoding="utf-8")
            with self.assertRaises(ValueError):
                store.read_manifest()
        duplicate = {**manifest, "previous": manifest["current"]}
        atomic_json(self.root / "current.json", duplicate)
        with self.assertRaises(ValueError):
            store.read_manifest()

    def test_gap_advances_time_without_fabricating_observations_or_episodes(self):
        session = self.agent.mind.actor.session
        clock, episodes, observed = self.agent.clock, len(session.memory.blocks), self.agent.temporal.observations
        result, gap = advance(self.agent, 90.)
        self.assertTrue(gap)
        self.assertEqual(self.agent.clock, clock + 90.)
        self.assertEqual(self.agent.temporal.observations, observed)
        self.assertEqual(len(session.memory.blocks), episodes)
        with self.assertRaises(ValueError):
            advance(self.agent, 8 * 24 * 3600.)

    def test_freeze_refuses_live_objects_and_recursively_detaches_mutable_values(self):
        tensor = torch.tensor([1.])
        document = {"nested": [{"state": tensor}], "labels": ["before"]}
        copied = freeze(document)
        tensor.zero_()
        document["labels"][0] = "after"
        self.assertEqual(copied["nested"][0]["state"].item(), 1.)
        self.assertEqual(copied["labels"], ["before"])
        with self.assertRaises(ValueError):
            freeze({"worker": object()})

    def test_real_runner_initializes_persists_stops_and_resumes_without_new_observations(self):
        source = self.root / "source.pt"
        atomic_write(source, capture(self.agent))
        first = run(self.root / "runtime", source, seconds=.2, save_every=1.)
        self.assertEqual(first["phase"], "stopped")
        self.assertTrue(first["episode_count_unchanged"])
        self.assertTrue(first["observation_count_unchanged"])
        self.assertGreaterEqual(first["writer_commits"], 1)
        second = run(self.root / "runtime", seconds=.2, save_every=1.)
        self.assertEqual(second["phase"], "stopped")
        self.assertTrue(second["recovery"]["resumed"])
        self.assertGreater(second["clock"], first["clock"])
        self.assertGreater(second["recovery"]["offline_seconds"], 0.)

    def test_startup_question_error_saves_existing_mind_and_releases_owner(self):
        source = self.root / "source.pt"
        atomic_write(source, capture(self.agent))
        with self.assertRaisesRegex(ValueError, "language-coordinator"):
            run(self.root / "runtime", source, seconds=.2, question="Olá")
        self.assertEqual(json.loads((self.root / "runtime/status.json").read_text())["phase"], "failed")
        with RuntimeStore(self.root / "runtime") as store:
            self.assertTrue(store.candidates())

    def test_new_store_does_not_overwrite_existing_unrelated_status_or_claim_other_directory(self):
        existing = self.root / "status.json"
        existing.write_bytes(b'private existing document')
        with self.assertRaisesRegex(ValueError, "empty dedicated"):
            RuntimeStore(self.root)
        self.assertEqual(existing.read_bytes(), b'private existing document')
        self.assertFalse((self.root / "store.json").exists())
        self.assertFalse((self.root / "current.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
