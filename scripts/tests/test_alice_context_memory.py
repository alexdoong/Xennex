"""Optional temporal-routing, bounded priority and memory-budget checks."""
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
from torch.nn import functional as F

from scripts.alice_memory.context_experiment import run
from scripts.alice_memory.context_memory import ContextMemory, load_checkpoint
from scripts.alice_memory.online_memory import make_value


class ContextMemoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        parent = ROOT / "bin" / "AliceMemoryTests"
        parent.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(dir=parent)
        cls.directory = Path(cls.temporary.name).resolve()
        if not cls.directory.is_relative_to(parent.resolve()):
            raise ValueError("Temporary directory must stay inside the workspace.")
        cls.pilot = cls.directory / "context"
        cls.report = run(cls.pilot, 17)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_temporal_state_routes_memory_without_episode_numbers(self) -> None:
        report = self.report
        self.assertTrue(report["accepted"], json.dumps(report))
        for modality in ("image", "audio", "mixed"):
            self.assertGreaterEqual(report["retrieval"]["accuracy"][modality], .9)
            self.assertEqual(report["empty_memory_control"]["accuracy"][modality], 0)
            self.assertGreaterEqual(report["retrieval"]["accuracy"][modality] -
                                    report["reset_temporal_control"]["accuracy"][modality], .2)
        self.assertLessEqual(report["retrieval"]["max_blocks_read"], 2)
        self.assertTrue(report["perception_unchanged"])

    def test_relevance_protects_cold_memory_and_priority_changes_near_ties(self) -> None:
        control = self.report["heat_controls"]
        self.assertTrue(control["cold_relevant_beats_hot_unrelated"])
        self.assertTrue(control["warm_preferred_between_near_matches"])
        self.assertGreater(control["heat_after_successful_access"], control["heat_before_successful_access"])
        self.assertLess(control["old_memory_freshness"], .01)
        self.assertEqual(control["old_memory_importance"], .9)

    def test_independent_seeds_replicate(self) -> None:
        for seed in (29, 71):
            report = run(self.directory / f"seed-{seed}", seed)
            self.assertTrue(report["accepted"], json.dumps(report))

    def test_importance_survives_cooling_and_peeking_does_not_reheat(self) -> None:
        memory = ContextMemory(half_life=10)
        context, signal = torch.eye(48)[0], torch.eye(16)[0]
        memory.write(context, signal, make_value(torch.tensor([1, 0, 0])), 0, .8)
        before = {name: value.clone() for name, value in memory.state_dict().items()}
        cold = memory.read(context, signal, 1000)
        self.assertAlmostEqual(cold["heat"], .4)
        self.assertEqual(cold["importance"], .8)
        self.assertLess(cold["freshness"], 1e-20)
        for name, value in memory.state_dict().items():
            self.assertTrue(torch.equal(before[name], value))
        memory.read(context, signal, 1000, activate=True)
        reheated = memory.read(context, signal, 1000)
        self.assertEqual(reheated["freshness"], cold["freshness"])
        self.assertGreater(reheated["reactivation"], cold["reactivation"])
        self.assertEqual(reheated["importance"], .8)

    def test_capacity_rejects_novel_write_without_changing_existing_memories(self) -> None:
        memory = ContextMemory(capacity=2)
        signal, value = torch.eye(16)[0], make_value(torch.tensor([1, 0, 0]))
        for index in range(2):
            memory.write(torch.eye(48)[index], signal, value, index)
        before = {name: value.clone() for name, value in memory.state_dict().items()}
        with self.assertRaisesRegex(ValueError, "capacity"):
            memory.write(torch.eye(48)[2], signal, value, 2)
        for name, value in memory.state_dict().items():
            self.assertTrue(torch.equal(before[name], value))
        # Existing contexts remain writable when the bank is full.
        memory.write(torch.eye(48)[0], signal, make_value(torch.tensor([1, 0, 0])), 3)
        self.assertEqual(len(memory.blocks), 2)

    def test_index_scan_and_associative_read_costs_are_reported_separately(self) -> None:
        memory = ContextMemory(capacity=128)
        generator = torch.Generator().manual_seed(417)
        contexts = F.normalize(torch.randn(100, 48, generator=generator), dim=-1)
        signal, value = torch.eye(16)[0], make_value(torch.tensor([1, 0, 0]))
        growth = []
        for index, context in enumerate(contexts):
            memory.write(context, signal, value, index)
            growth.append(memory.state_bytes())
        result = memory.read(contexts[0], signal, 1000)
        self.assertEqual(result["addresses_compared"], 100)
        self.assertEqual(result["blocks_read"], 1)
        self.assertEqual(result["block"], 0)
        self.assertEqual(set(b - a for a, b in zip(growth, growth[1:])), {3592})

    def test_irrelevant_query_abstains_without_reheating(self) -> None:
        memory = ContextMemory()
        memory.write(torch.eye(48)[0], torch.eye(16)[0], make_value(torch.tensor([1, 0, 0])), 0)
        before = memory.activation.clone()
        result = memory.read(torch.eye(48)[1], torch.eye(16)[0], 100, activate=True)
        self.assertIsNone(result["recall"])
        self.assertEqual(result["blocks_read"], 0)
        self.assertTrue(torch.equal(before, memory.activation))

    def test_new_process_queries_only_current_signal_and_persisted_state(self) -> None:
        isolated = self.directory / "query-only"
        isolated.mkdir()
        shutil.copyfile(self.pilot / "weights.pt", isolated / "state.pt")
        original = (isolated / "state.pt").read_bytes()
        for modality, extension in (("image", "png"), ("audio", "wav")):
            signal = isolated / f"anonymous.{extension}"
            shutil.copyfile(self.pilot / "examples" / f"current.{extension}", signal)
            result = subprocess.run(
                [sys.executable, "-m", "scripts.alice_memory", "context-query", "--checkpoint",
                 str(isolated / "state.pt"), f"--{modality}", str(signal), "--elapsed", ".5",
                 "--now", str(self.report["query_time"])], cwd=ROOT, capture_output=True,
                text=True, timeout=30, check=True)
            self.assertEqual(json.loads(result.stdout)["recall"], self.report["expected_query"])
        self.assertFalse((isolated / "report.json").exists())
        self.assertEqual(original, (isolated / "state.pt").read_bytes())

    def test_invalid_priority_or_time_does_not_change_memory(self) -> None:
        memory = ContextMemory()
        context, signal, value = torch.eye(48)[0], torch.eye(16)[0], torch.zeros(12)
        memory.write(context, signal, value, 1)
        before = {name: value.clone() for name, value in memory.state_dict().items()}
        for importance in (-1, 2, float("nan")):
            with self.assertRaises(ValueError):
                memory.write(context, signal, value, 2, importance)
        with self.assertRaises(ValueError):
            memory.read(context, signal, 0, activate=True)
        for name, value in memory.state_dict().items():
            self.assertTrue(torch.equal(before[name], value))

    def test_corrupt_priority_metadata_is_rejected(self) -> None:
        payload = torch.load(self.pilot / "weights.pt", weights_only=True)
        payload["memory"]["importance"][0] = 2
        invalid = self.directory / "invalid.pt"
        torch.save(payload, invalid)
        with self.assertRaisesRegex(ValueError, "metadata"):
            load_checkpoint(invalid)


if __name__ == "__main__":
    unittest.main(verbosity=2)
