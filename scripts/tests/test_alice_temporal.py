"""Optional causal-sequence checks, with no devices or background processes."""
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

from scripts.alice_memory.temporal import run, probe
from scripts.alice_memory.temporal_core import TemporalSession, load_checkpoint


class TemporalContinuityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        parent = ROOT / "bin" / "AliceMemoryTests"
        parent.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(dir=parent)
        cls.directory = Path(cls.temporary.name).resolve()
        if not cls.directory.is_relative_to(parent.resolve()):
            raise ValueError("Temporary directory must stay inside the workspace.")
        cls.pilot = cls.directory / "time"
        cls.report = run(cls.pilot, 17)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_prediction_requires_persistent_state_and_variable_duration(self) -> None:
        self.assertTrue(self.report["accepted"], json.dumps(self.report))
        for modality in ("image", "audio", "mixed"):
            accuracy = self.report["next_signal_accuracy"][modality]
            self.assertGreaterEqual(accuracy, .9)
            self.assertGreaterEqual(accuracy - self.report["reset_state_control"][modality], .2)
            self.assertGreaterEqual(accuracy - self.report["removed_interval_control"][modality], .2)
        self.assertTrue(self.report["perception_unchanged"])

    def test_independent_initializations_replicate(self) -> None:
        for seed in (29, 71):
            report = run(self.directory / f"seed-{seed}", seed)
            self.assertTrue(report["accepted"], json.dumps(report))

    def test_same_current_input_produces_different_expectations_from_history_and_gap(self) -> None:
        self.assertEqual(self.report["same_current_signal_probes"], {
            "forward_short": 1, "backward_short": 7, "forward_long": 2, "backward_long": 6})
        self.assertLess(self.report["shuffled_history_control"], .7)

    def test_new_process_continues_from_weights_and_current_state_without_history(self) -> None:
        isolated = self.directory / "query-only"
        isolated.mkdir()
        shutil.copyfile(self.pilot / "weights.pt", isolated / "state.pt")
        saved_bytes = (isolated / "state.pt").read_bytes()
        for modality, extension in (("image", "png"), ("audio", "wav")):
            signal = isolated / f"anonymous.{extension}"
            shutil.copyfile(self.pilot / "examples" / f"current.{extension}", signal)
            process = subprocess.run(
                [sys.executable, "-m", "scripts.alice_memory", "time-query", "--checkpoint",
                 str(isolated / "state.pt"), f"--{modality}", str(signal), "--elapsed", "1"],
                cwd=ROOT, capture_output=True, text=True, timeout=30, check=True)
            result = json.loads(process.stdout)
            self.assertEqual(result["predicted_next_identity"], 2)
            self.assertEqual(result["observations"], 4)
        self.assertEqual(saved_bytes, (isolated / "state.pt").read_bytes())
        self.assertFalse((isolated / "report.json").exists())
        self.assertTrue(self.report["persistence_exact"])

    def test_missing_measurement_advances_state_without_inventing_an_observation(self) -> None:
        perception, restored = load_checkpoint(self.pilot / "weights.pt")
        core = restored.core
        missing = probe(core, perception.anchors, [5, 6, 7], .5)
        before = missing.hidden.clone()
        missing.advance(None, 3)
        self.assertFalse(torch.equal(before, missing.hidden))
        self.assertEqual(missing.observations, 3)
        self.assertEqual(missing.since_observation, 3)
        missing.advance(perception.anchors[0:1], 1)
        uninterrupted = probe(core, perception.anchors, [5, 6, 7, 0], 4)
        torch.testing.assert_close(missing.hidden, uninterrupted.hidden)
        observed = probe(core, perception.anchors, [5, 6, 7], .5)
        observed.advance(torch.zeros(1, 16), 3)
        self.assertEqual(observed.observations, 4)
        self.assertEqual(observed.since_observation, 0)

    def test_invalid_interval_or_signal_does_not_change_session(self) -> None:
        _, session = load_checkpoint(self.pilot / "weights.pt")
        before = session.hidden.clone()
        for interval in (-1, 61, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                session.advance(None, interval)
        with self.assertRaises(ValueError):
            session.advance(torch.full((1, 16), float("nan")), 1)
        self.assertTrue(torch.equal(before, session.hidden))
        self.assertEqual(session.observations, 3)
        self.assertEqual(session.since_observation, 3)

    def test_nonfinite_persisted_state_is_rejected(self) -> None:
        payload = torch.load(self.pilot / "weights.pt", weights_only=True)
        payload["hidden"][0, 0] = float("nan")
        invalid = self.directory / "invalid.pt"
        torch.save(payload, invalid)
        with self.assertRaisesRegex(ValueError, "non-finite"):
            load_checkpoint(invalid)

    def test_continuous_session_is_bounded_and_reading_does_not_advance_it(self) -> None:
        perception, restored = load_checkpoint(self.pilot / "weights.pt")
        session = TemporalSession(restored.core)
        weights = {name: value.clone() for name, value in session.core.state_dict().items()}
        for index in range(1024):
            session.advance(perception.anchors[index % 8:index % 8 + 1], .5)
        self.assertEqual(session.hidden.numel(), 48)
        self.assertTrue(torch.isfinite(session.hidden).all())
        before = session.hidden.clone()
        session.prediction()
        session.prediction()
        self.assertTrue(torch.equal(before, session.hidden))
        self.assertEqual(session.observations, 1024)
        for name, value in session.core.state_dict().items():
            self.assertTrue(torch.equal(weights[name], value))


if __name__ == "__main__":
    unittest.main(verbosity=2)
