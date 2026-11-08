"""Learned runtime continuity, modality provenance and checkpoint transactions."""
from __future__ import annotations

import copy
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.alice_memory.contracts import Observation
from scripts.alice_memory.crossmodal import run as train
from scripts.alice_memory.predictive_loop import create, load, run, save
from scripts.alice_memory.signals import synthetic_audio
from scripts.alice_memory.world import SyntheticWorld


def advance(agent, world, steps):
    for _ in range(steps):
        agent.step(world.advance(.1, agent.last_action), .1)


class PredictiveRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        fixture = ROOT / "bin" / "AlicePredictiveTests"
        fixture.mkdir(parents=True, exist_ok=True)
        cls.directory = tempfile.TemporaryDirectory(dir=fixture)
        cls.folder = Path(cls.directory.name)
        train(cls.folder / "models", 17)
        cls.base, _ = create(cls.folder / "models/models.pt", 17)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.directory.cleanup()

    def pair(self, seed=17):
        return copy.deepcopy(self.base), SyntheticWorld(seed)

    def assert_state_equal(self, left, right):
        self.assertEqual(left.snapshot(), right.snapshot())
        for key, value in left.temporal.snapshot().items():
            actual = right.temporal.snapshot()[key]
            if isinstance(value, torch.Tensor):
                self.assertTrue(torch.equal(value, actual), key)
            else:
                self.assertEqual(value, actual, key)

    def test_new_process_resume_is_exact_without_model_or_observation_files(self):
        agent, world = self.pair()
        advance(agent, world, 8)
        state = self.folder / "anonymous.pt"
        save(state, agent, world)
        advance(agent, world, 40)
        output = self.folder / "resumed"
        result = subprocess.run([sys.executable, "-m", "scripts.alice_memory", "predictive-loop",
                                 "--checkpoint", str(state), "--steps", "40", "--output", str(output)],
                                cwd=ROOT, capture_output=True, text=True, timeout=60)
        # CLI 2 declares prediction below target while still exporting a valid state.
        self.assertIn(result.returncode, (0, 2), result.stderr)
        self.assertTrue(json.loads(result.stdout)["resumed"])
        restored, restored_world = load(output / "loop.pt")
        self.assert_state_equal(agent, restored)
        self.assertEqual(world.snapshot(), restored_world.snapshot())

    def test_missing_input_updates_learned_state_without_fake_observations(self):
        agent, _ = self.pair()
        before = agent.temporal.hidden.clone()
        result = agent.tick(.1)
        self.assertTrue(result.internal_tick)
        self.assertFalse(torch.equal(before, agent.temporal.hidden))
        self.assertEqual(agent.temporal.observations, 0)
        self.assertEqual(agent.temporal.scored, 0)
        self.assertEqual(agent.temporal.present.item(), 0)
        self.assertEqual(agent.temporal.visual.count_nonzero().item(), 0)
        self.assertTrue(torch.isfinite(agent.temporal.hidden).all())

    def test_audio_origins_remain_distinct_and_person_sound_guides_motor_code(self):
        agent, world = self.pair()
        advance(agent, world, 7)
        code = (agent.last_identity + 1) % 8
        person = Observation("audio", synthetic_audio(code, random.Random(91)), agent.clock + .1,
                             100, origin="person")
        result = agent.step([person], .1)
        self.assertEqual(result.action.kind, "emit")
        self.assertEqual(result.action.signal, code)
        self.assertEqual(agent.temporal.audio_acquired[1].item(), person.acquired_at)
        own = Observation("audio", synthetic_audio((code + 2) % 8, random.Random(92)), agent.clock + .1,
                          101, origin="self", action_id=result.action.sequence)
        agent.step([own], .1)
        self.assertEqual(agent.last_identity, code)
        self.assertEqual(agent.self_feedback, 1)
        self.assertEqual(agent.temporal.audio_acquired[2].item(), own.acquired_at)
        self.assertFalse(torch.equal(agent.temporal.audio[1], agent.temporal.audio[2]))

    def test_forecasts_score_actual_next_measurements_and_occlusion_is_excluded(self):
        agent, world = self.pair()
        advance(agent, world, 12)
        count = agent.temporal.scored
        self.assertGreater(count, 3)
        advance(agent, world, 1)  # scripted sensor dropout at step 13
        self.assertEqual(agent.temporal.present.item(), 0)
        self.assertEqual(agent.temporal.scored, count)
        advance(agent, world, 1)
        self.assertEqual(agent.temporal.scored, count)  # repeat-last baseline unavailable

    def test_future_packet_is_rejected_before_any_predictive_state_mutation(self):
        agent, _ = self.pair()
        before = copy.deepcopy(agent)
        with self.assertRaisesRegex(ValueError, "future"):
            agent.step([Observation("audio", torch.zeros(1024), .2, 0)], .1)
        self.assert_state_equal(before, agent)

    def test_failed_save_preserves_previous_state_and_invalid_load_preserves_rng(self):
        agent, world = self.pair()
        advance(agent, world, 8)
        path = self.folder / "transaction.pt"
        save(path, agent, world)
        before = path.read_bytes()
        advance(agent, world, 1)
        with patch("scripts.alice_memory.loop_checkpoint.os.replace", side_effect=OSError("Injected failure")):
            with self.assertRaises(OSError):
                save(path, agent, world)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list(self.folder.glob("*.tmp")), [])
        payload = torch.load(path, weights_only=True)
        payload["state"]["forecasts"] = 9
        torch.save(payload, path)
        rng = torch.get_rng_state().clone()
        with self.assertRaisesRegex(ValueError, "counters"):
            load(path)
        self.assertTrue(torch.equal(rng, torch.get_rng_state()))

    def test_long_runtime_remains_bounded_with_real_predictions_and_feedback(self):
        report = run(self.folder / "long-run", self.folder / "models/models.pt", 17, 10000, 120)
        self.assertTrue(report["stability_accepted"])
        self.assertGreater(report["prediction"]["scored"], 8000)
        self.assertGreater(report["self_feedback"], 1000)
        self.assertLessEqual(report["peak_pending"], 32)
        agent, _ = load(self.folder / "long-run/loop.pt")
        self.assertLessEqual(agent.temporal.audio.numel(), 48)
        self.assertFalse(hasattr(agent.temporal, "history"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
