"""Causal simulation, bounded state, feedback identity and independent resume."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.alice_memory.agent_loop import AgentLoop
from scripts.alice_memory.contracts import Action, Observation
from scripts.alice_memory.loop_checkpoint import load, save
from scripts.alice_memory.loop_experiment import create, drive
from scripts.alice_memory.process_metrics import Budget
from scripts.alice_memory.world import SyntheticWorld


def progress(agent: AgentLoop, world: SyntheticWorld, count: int) -> list[dict]:
    outputs = []
    for _ in range(count):
        packets = world.advance(.1, agent.last_action)
        result = agent.step(packets, .1)
        outputs.append({"action": result.action, "hidden": agent.temporal.hidden.clone(),
                        "state": agent.snapshot(), "world": world.snapshot()})
    return outputs


class CausalLoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        torch.set_num_threads(2)
        torch.use_deterministic_algorithms(True)
        cls.base, _ = create(17)
        cls.fixture_root = ROOT / "bin" / "AliceLoopTests"
        cls.fixture_root.mkdir(parents=True, exist_ok=True)

    def pair(self, seed: int = 17) -> tuple[AgentLoop, SyntheticWorld]:
        return copy.deepcopy(self.base), SyntheticWorld(seed)

    def test_actions_change_observation_and_feedback_arrives_after_emission(self) -> None:
        left, right = SyntheticWorld(17), SyntheticWorld(17)
        a = left.advance(.1, Action("focus", 0, 0, target=0))
        b = right.advance(.1, Action("focus", 0, 0, target=2))
        self.assertFalse(torch.equal(a[0].payload, b[0].payload))
        packets = left.advance(.1, Action("emit", 1, .1, signal=4))
        self.assertFalse(any(packet.origin == "self" for packet in packets))
        packets = left.advance(.3)
        own = [packet for packet in packets if packet.origin == "self"]
        self.assertEqual(len(own), 1)
        self.assertEqual(own[0].action_id, 1)
        self.assertAlmostEqual(own[0].acquired_at, .4)
        self.assertFalse(any(packet.origin == "self" for packet in left.advance(.1)))
        self.assertFalse(hasattr(own[0], "identity"))

    def test_invalid_actions_do_not_change_world_or_random_state(self) -> None:
        world = SyntheticWorld(29)
        before = world.snapshot()
        for action in (Action("focus", 0, 0, target=3), Action("emit", 0, 0, signal=8),
                       Action("wait", 0, 1), Action("shell", 0, 0)):
            with self.assertRaises(ValueError):
                world.advance(.1, action)
            self.assertEqual(world.snapshot(), before)

    def test_future_packet_is_rejected_before_agent_mutation(self) -> None:
        agent, world = self.pair()
        packets = world.advance(.1)
        future = Observation("audio", torch.zeros(1024), .2, 100)
        before, hidden = agent.snapshot(), agent.temporal.hidden.clone()
        with self.assertRaisesRegex(ValueError, "future"):
            agent.step([*packets, future], .1)
        self.assertEqual(before, agent.snapshot())
        self.assertTrue(torch.equal(hidden, agent.temporal.hidden))

    def test_duplicate_and_late_delivery_do_not_become_new_observations(self) -> None:
        agent, world = self.pair()
        packets = world.advance(.1)
        first = agent.step(packets, .1)
        self.assertEqual(first.encoded, 1)
        result = agent.step(packets, .1)
        self.assertEqual(result.encoded, 0)
        self.assertEqual(result.stale, 1)
        self.assertTrue(result.internal_tick)
        late = Observation("image", packets[0].payload, .05, 100)
        self.assertEqual(agent.step([late], .1).encoded, 0)

    def test_missing_measurement_and_measured_silence_are_distinct(self) -> None:
        missing, _ = self.pair()
        silence, _ = self.pair()
        a = missing.tick(.1)
        b = silence.step([Observation("audio", torch.zeros(1024), .1, 0)], .1)
        self.assertTrue(a.internal_tick)
        self.assertFalse(b.internal_tick)
        self.assertEqual(missing.temporal.observations, 0)
        self.assertEqual(silence.temporal.observations, 1)

    def test_unrecognized_self_feedback_is_not_accepted_as_external(self) -> None:
        agent, _ = self.pair()
        packet = Observation("audio", torch.ones(1024), .1, 0, "self", action_id=10)
        result = agent.step([packet], .1)
        self.assertEqual((result.encoded, result.self_feedback, result.external_feedback), (0, 0, 0))
        self.assertEqual(result.stale, 1)

    def test_restore_preserves_pending_feedback_rng_and_entire_trajectory(self) -> None:
        agent, world = self.pair()
        progress(agent, world, 8)
        self.assertEqual(agent.last_action.kind, "emit")
        with tempfile.TemporaryDirectory(dir=self.fixture_root) as folder:
            path = Path(folder) / "state.pt"
            save(path, agent, world)
            expected = progress(agent, world, 80)
            restored, restored_world = load(path)
            actual = progress(restored, restored_world, 80)
        for left, right in zip(expected, actual):
            self.assertEqual(left["action"], right["action"])
            self.assertEqual(left["world"], right["world"])
            self.assertEqual(left["state"], right["state"])
            self.assertTrue(torch.equal(left["hidden"], right["hidden"]))

    def test_failed_atomic_replace_preserves_previous_checkpoint(self) -> None:
        agent, world = self.pair()
        progress(agent, world, 8)
        with tempfile.TemporaryDirectory(dir=self.fixture_root) as folder:
            path = Path(folder) / "state.pt"
            save(path, agent, world)
            before = path.read_bytes()
            progress(agent, world, 3)
            with patch("scripts.alice_memory.loop_checkpoint.os.replace", side_effect=OSError("Synthetic replacement failure")):
                with self.assertRaises(OSError):
                    save(path, agent, world)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(folder).glob("*.tmp")), [])
            restored, _ = load(path)
            self.assertEqual(restored.steps, 8)

    def test_invalid_checkpoint_does_not_change_global_torch_rng(self) -> None:
        agent, world = self.pair()
        progress(agent, world, 8)
        with tempfile.TemporaryDirectory(dir=self.fixture_root) as folder:
            path = Path(folder) / "state.pt"
            save(path, agent, world)
            payload = torch.load(path, weights_only=True)
            payload["agent"]["attention"] = 3
            torch.save(payload, path)
            before = torch.get_rng_state().clone()
            with self.assertRaises(ValueError):
                load(path)
            self.assertTrue(torch.equal(before, torch.get_rng_state()))

    def test_ten_thousand_steps_have_finite_state_and_bounded_queues(self) -> None:
        for seed in (17, 29, 71):
            agent, world = self.pair(seed)
            report = drive(agent, world, 10000, Budget(10000, 120))
            self.assertLessEqual(report["peak_pending"], 32)
            self.assertLessEqual(len(agent.last_sequence), 6)
            self.assertTrue(torch.isfinite(agent.temporal.hidden).all())
            self.assertGreater(agent.self_feedback, 100)
            self.assertGreater(agent.external_feedback, 100)
            self.assertFalse(hasattr(agent, "history"))

    def test_new_process_resume_needs_only_checkpoint_and_not_old_report(self) -> None:
        agent, world = self.pair()
        progress(agent, world, 8)
        with tempfile.TemporaryDirectory(dir=self.fixture_root) as folder:
            path = Path(folder) / "anonymous.pt"
            output = Path(folder) / "continued"
            save(path, agent, world)
            expected = progress(agent, world, 24)
            result = subprocess.run([sys.executable, "-m", "scripts.alice_memory", "loop",
                                     "--checkpoint", str(path), "--steps", "24", "--output", str(output)],
                                    cwd=ROOT, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report["resumed"])
            actual, actual_world = load(output / "loop.pt")
            self.assertEqual(actual.snapshot(), expected[-1]["state"])
            self.assertEqual(actual_world.snapshot(), expected[-1]["world"])
            self.assertTrue(torch.equal(actual.temporal.hidden, expected[-1]["hidden"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
