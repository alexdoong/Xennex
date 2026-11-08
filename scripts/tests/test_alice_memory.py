"""Optional CPU laboratory checks. No real data, devices, network or model downloads."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import torch

from scripts.alice_memory.experiment import run
from scripts.alice_memory.network import load_checkpoint
from scripts.alice_memory.signals import load_audio


class NeuralMemoryExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        temporary_parent = ROOT / "bin" / "AliceMemoryTests"
        temporary_parent.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(dir=temporary_parent)
        cls.directory = Path(cls.temporary.name).resolve()
        if not cls.directory.is_relative_to(temporary_parent.resolve()):
            raise ValueError("Test directory must stay within the isolated workspace.")
        cls.pilot = cls.directory / "pilot"
        cls.report = run(cls.pilot, seed=17)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_new_visual_experiences_transfer_to_untrained_audio_memory(self) -> None:
        self.assertTrue(self.report["accepted"], json.dumps(self.report))
        self.assertEqual(self.report["before"]["audio"]["exact"], 0)
        self.assertGreaterEqual(self.report["after_correction"]["audio"]["exact"], .9)
        self.assertTrue(self.report["perception_unchanged"])

    def test_controls_require_learned_weights_and_corresponding_input(self) -> None:
        for modality in ("image", "audio"):
            self.assertLess(self.report["zero_memory_control"][modality]["exact"], .2)
            self.assertLess(self.report["mismatched_input_control"][modality]["exact"], .2)

    def test_sequential_learning_measures_forgetting_and_retention(self) -> None:
        for modality in ("image", "audio"):
            self.assertGreaterEqual(self.report["first_stage_old"][modality]["exact"], .9)
            self.assertGreaterEqual(self.report["second_stage_with_replay"][modality]["exact"], .9)
            self.assertGreaterEqual(self.report["after_correction"][modality]["exact"], .9)
        # The no-replay result is a measured control, not a universal assertion.
        self.assertIn("second_stage_without_replay_old", self.report)

    def test_random_associations_and_initialization_replicate(self) -> None:
        for seed in (29, 71):
            report = run(self.directory / f"replica-{seed}", seed=seed)
            self.assertTrue(report["accepted"], json.dumps(report))

    def test_new_process_uses_only_checkpoint_and_anonymously_named_signal(self) -> None:
        expected = json.loads((self.pilot / "expected.json").read_text(encoding="utf-8"))
        isolated = self.directory / "query-only"
        isolated.mkdir()
        shutil.copyfile(self.pilot / "weights.pt", isolated / "weights.pt")
        for modality, extension in (("image", "png"), ("audio", "wav")):
            anonymous = isolated / f"unrelated-name.{extension}"
            shutil.copyfile(self.pilot / "examples" / f"object-0.{extension}", anonymous)
            process = subprocess.run(
                [sys.executable, "-m", "scripts.alice_memory", "query", "--checkpoint",
                 str(isolated / "weights.pt"), f"--{modality}", str(anonymous)],
                cwd=ROOT, capture_output=True, text=True, timeout=30, check=True)
            self.assertEqual(json.loads(process.stdout)["recall"], expected["object-0"])
        self.assertFalse((isolated / "expected.json").exists())
        self.assertFalse((isolated / "report.json").exists())

    def test_nonfinite_checkpoint_is_rejected(self) -> None:
        payload = torch.load(self.pilot / "weights.pt", weights_only=True)
        payload["memory"]["layers.0.weight"][0, 0] = float("nan")
        invalid = self.directory / "invalid.pt"
        torch.save(payload, invalid)
        with self.assertRaisesRegex(ValueError, "non-finite"):
            load_checkpoint(invalid)

    def test_experiment_does_not_overwrite_previous_run(self) -> None:
        with self.assertRaises(FileExistsError):
            run(self.pilot, seed=17)

    def test_audio_contract_rejects_non_wav_input(self) -> None:
        with self.assertRaises((EOFError, OSError, wave.Error)):
            load_audio(self.pilot / "examples" / "object-0.png")


if __name__ == "__main__":
    unittest.main(verbosity=2)
