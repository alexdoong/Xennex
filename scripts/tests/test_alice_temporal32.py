"""Temporal causality, command purposes, missing input and fair model capacity."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.alice_memory.temporal32 import Temporal32, Temporal32Session, action_features


class Temporal32Tests(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(17)
        torch.set_num_threads(2)

    def test_parameter_counts_are_within_five_percent(self):
        counts = [sum(value.numel() for value in Temporal32(kind).parameters()) for kind in ("multi", "gru")]
        self.assertLess(abs(counts[0] - counts[1]) / max(counts), .05)
        self.assertLess(max(counts), 25000)

    def test_legacy_architectures_remain_distinct(self):
        self.assertEqual(Temporal32("gru-v1").initial(1).shape, (1, 60))
        self.assertEqual(Temporal32("gru").initial(1).shape, (1, 48))
        self.assertIsInstance(Temporal32("multi-gru-v1").slow, torch.nn.GRUCell)
        self.assertIsInstance(Temporal32("multi").slow, torch.nn.Linear)

    def test_future_inputs_cannot_change_an_earlier_prediction(self):
        core = Temporal32()
        signals = torch.nn.functional.normalize(torch.randn(2, 12, 32), dim=-1)
        commands = torch.stack([action_features(index % 4, index % 4) for index in range(12)]).expand(2, -1, -1)
        gaps, presence = torch.full((2, 12, 1), .1), torch.ones(2, 12, 1)
        before = core.sequence(signals, commands, gaps, presence)
        signals[:, 6:] = torch.randn_like(signals[:, 6:])
        after = core.sequence(signals, commands, gaps, presence)
        self.assertTrue(torch.equal(before[:, :6], after[:, :6]))

    def test_absent_payload_is_not_used_as_an_observation(self):
        core = Temporal32()
        hidden = torch.randn(1, 64)
        gap, absent = torch.tensor([[2.]]), torch.zeros(1, 1)
        first = core.advance(torch.randn(1, 32), hidden, gap, absent)
        second = core.advance(torch.randn(1, 32) * 100, hidden, gap, absent)
        self.assertTrue(torch.equal(first, second))

    def test_internal_decay_keeps_the_action_copy_until_next_perception(self):
        session = Temporal32Session(Temporal32())
        session.advance(torch.nn.functional.normalize(torch.randn(32), dim=0), .1)
        session.predict(2, 2)
        before = session.command.clone()
        session.advance(None, 1.)
        self.assertTrue(torch.equal(before, session.command))
        self.assertEqual(session.observations, 1)
        session.advance(torch.nn.functional.normalize(torch.randn(32), dim=0), .1)
        self.assertEqual(session.command.sum().item(), 0.)
        self.assertEqual(session.observations, 2)

    def test_command_purpose_is_separate_from_its_tone_code(self):
        motor = action_features(2, 0)
        speech = action_features(2, 2)
        self.assertTrue(torch.equal(motor[:4], speech[:4]))
        self.assertFalse(torch.equal(motor[4:8], speech[4:8]))
        self.assertEqual(action_features().sum().item(), 0.)
        for code, field in ((True, 0), (4, 0), (0, 4)):
            with self.assertRaises(ValueError):
                action_features(code, field)

    def test_invalid_latent_or_time_preserves_the_session(self):
        session = Temporal32Session(Temporal32())
        before = copy.deepcopy(session.snapshot())
        for latent, elapsed in ((torch.zeros(16), .1), (torch.full((32,), float("nan")), .1),
                                (torch.zeros(32, dtype=torch.float64), .1), (None, 61.)):
            with self.assertRaises(ValueError):
                session.advance(latent, elapsed)
        self.assertEqual(before["clock"], session.clock)
        self.assertTrue(torch.equal(before["hidden"], session.hidden))


if __name__ == "__main__":
    unittest.main(verbosity=2)
