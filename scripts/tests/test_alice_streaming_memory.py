"""Optional checks of incremental memory, correction and independent-process recall."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import torch

from scripts.alice_memory.online_memory import (OnlineMemory, load_checkpoint,
                                               make_key, save_checkpoint)
from scripts.alice_memory.streaming import run


class StreamingMemoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        parent = ROOT / "bin" / "AliceMemoryTests"
        parent.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(dir=parent)
        cls.directory = Path(cls.temporary.name).resolve()
        if not cls.directory.is_relative_to(parent.resolve()):
            raise ValueError("Temporary directory must stay inside the workspace.")
        cls.pilot = cls.directory / "stream"
        cls.report = run(cls.pilot, 17)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_old_episodes_survive_every_new_stage_without_replay(self) -> None:
        self.assertTrue(self.report["accepted"], json.dumps(self.report))
        for stage in self.report["stages"]:
            for modality in ("image", "audio"):
                self.assertGreaterEqual(stage[modality]["exact"], .9)
        self.assertEqual(self.report["replayed_observations"], 0)
        self.assertEqual(self.report["writes"], 1025)
        self.assertTrue(self.report["perception_unchanged"])
        self.assertTrue(all(self.report["unknown_episode_abstention_before_write"]))

    def test_correction_preserves_initial_interpretation_and_meal_quality(self) -> None:
        meal = self.report["meal"]
        self.assertEqual(meal["initial"]["autor"], "pai")
        self.assertEqual(meal["current"]["autor"], "mae")
        for view in meal.values():
            self.assertEqual(view["atividade"], "comer")
            self.assertEqual(view["impressao"], "agradavel")
        for modality in ("image", "audio"):
            self.assertGreaterEqual(self.report["after_correction"][modality]["exact"], .9)
            self.assertLess(self.report["zero_memory_control"][modality]["exact"], .3)
            self.assertLess(self.report["mismatched_input_control"][modality]["exact"], .3)

    def test_independent_initializations_and_random_associations(self) -> None:
        for seed in (29, 71):
            report = run(self.directory / f"seed-{seed}", seed)
            self.assertTrue(report["accepted"], json.dumps(report))

    def test_online_updates_match_independent_weighted_batch_ridge_solution(self) -> None:
        # The oracle can keep examples; the system under test receives one at a time.
        generator = torch.Generator().manual_seed(631)
        keys = torch.randn(20, 5, generator=generator, dtype=torch.float64)
        values = torch.randn(20, 3, generator=generator, dtype=torch.float64)
        strengths = torch.linspace(.5, 5, 20, dtype=torch.float64)
        memory = OnlineMemory(key_size=5, value_size=3)
        for key, value, strength in zip(keys, values, strengths):
            memory.write(key, value, strength.item())
        covariance = keys.T @ (keys * strengths[:, None]) + .001 * torch.eye(5)
        expected = torch.linalg.solve(covariance, keys.T @ (values * strengths[:, None])).T
        torch.testing.assert_close(memory.weights, expected, atol=1e-8, rtol=1e-8)

    def test_state_has_fixed_size_and_contains_no_observation_buffer(self) -> None:
        memory = OnlineMemory()
        shapes = {name: value.shape for name, value in memory.state_dict().items()}
        self.assertEqual(set(shapes), {"weights", "precision", "writes"})
        representation = torch.eye(16)[0]
        for episode in range(4):
            memory.write(make_key(representation, episode, "current"), torch.ones(12))
        self.assertEqual(shapes, {name: value.shape for name, value in memory.state_dict().items()})
        with self.assertRaises(ValueError):
            make_key(representation, 4, "current")

    def test_new_process_needs_only_weights_signal_and_requested_context(self) -> None:
        isolated = self.directory / "query-only"
        isolated.mkdir()
        shutil.copyfile(self.pilot / "weights.pt", isolated / "weights.pt")
        expected = json.loads((self.pilot / "expected.json").read_text(encoding="utf-8"))
        for modality, extension in (("image", "png"), ("audio", "wav")):
            signal = isolated / f"anonymous.{extension}"
            shutil.copyfile(self.pilot / "examples" / f"meal.{extension}", signal)
            for view in ("initial", "current"):
                process = subprocess.run(
                    [sys.executable, "-m", "scripts.alice_memory", "stream-query",
                     "--checkpoint", str(isolated / "weights.pt"), f"--{modality}", str(signal),
                     "--episode", "1", "--view", view], cwd=ROOT, capture_output=True,
                    text=True, timeout=30, check=True)
                self.assertEqual(json.loads(process.stdout)["recall"], expected[view])
        self.assertFalse((isolated / "expected.json").exists())
        self.assertFalse((isolated / "report.json").exists())

    def test_cli_abstains_when_context_has_never_been_learned(self) -> None:
        perception, _ = load_checkpoint(self.pilot / "weights.pt")
        fresh = self.directory / "fresh.pt"
        save_checkpoint(fresh, perception, OnlineMemory())
        process = subprocess.run(
            [sys.executable, "-m", "scripts.alice_memory", "stream-query", "--checkpoint",
             str(fresh), "--image", str(self.pilot / "examples" / "meal.png"),
             "--episode", "2"], cwd=ROOT, capture_output=True, text=True, timeout=30, check=True)
        result = json.loads(process.stdout)
        self.assertIsNone(result["recall"])
        self.assertTrue(result["unknown_context"])

    def test_invalid_write_is_rejected_before_any_state_change(self) -> None:
        memory = OnlineMemory()
        snapshot = {name: value.clone() for name, value in memory.state_dict().items()}
        for strength in (0, -1, float("inf"), float("nan"), 10001):
            with self.assertRaises(ValueError):
                memory.write(torch.zeros(128), torch.zeros(12), strength)
        for name, value in memory.state_dict().items():
            self.assertTrue(torch.equal(value, snapshot[name]))

    def test_invalid_persisted_matrix_is_rejected(self) -> None:
        payload = torch.load(self.pilot / "weights.pt", weights_only=True)
        payload["memory"]["precision"] = -torch.eye(128, dtype=torch.float64)
        invalid = self.directory / "invalid.pt"
        torch.save(payload, invalid)
        with self.assertRaisesRegex(ValueError, "precision"):
            load_checkpoint(invalid)


if __name__ == "__main__":
    unittest.main(verbosity=2)
