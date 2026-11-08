"""Evidence for paired perception, action dependence and predictive restoration."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.alice_memory.crossmodal import curriculum, load, paired_scores, prediction_scores, run
from scripts.alice_memory.predictive_training import curriculum as long_curriculum


class PredictiveLearningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture_root = ROOT / "bin" / "AliceCrossmodalTests"
        cls.fixture_root.mkdir(parents=True, exist_ok=True)
        cls.directory = tempfile.TemporaryDirectory(dir=cls.fixture_root)
        cls.pilot = Path(cls.directory.name) / "pilot"
        cls.report = run(cls.pilot, 17)
        cls.perception, cls.predictor = load(cls.pilot / "models.pt")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.directory.cleanup()

    def test_paired_learning_transfers_without_anchor_targets(self) -> None:
        scores = paired_scores(self.perception, 9017)
        self.assertGreaterEqual(scores["image_to_audio"], .9)
        self.assertGreaterEqual(scores["audio_to_image"], .9)
        self.assertLess(scores["shuffled_correspondence"], .2)
        self.assertGreater(scores["latent_variance"], .005)
        # Anchors were never changed or used as loss targets.
        self.assertTrue(torch.equal(self.perception.anchors, torch.eye(8, 16)))

    def test_action_conditioned_history_improves_reserved_consequences(self) -> None:
        self.assertTrue(self.report["accepted"])
        self.assertGreaterEqual(self.report["prediction"]["relative_improvement"], .2)
        self.assertGreater(self.report["reset_state"]["mse"], self.report["prediction"]["mse"])
        self.assertGreater(self.report["shuffled_actions"]["mse"], self.report["prediction"]["mse"])

    def test_missing_views_are_masked_instead_of_used_as_semantic_black_images(self) -> None:
        features, _, _, present = curriculum(self.perception, 1017, 8)
        missing = present.squeeze(-1) == 0
        self.assertTrue(missing.any())
        self.assertEqual(features[missing].count_nonzero().item(), 0)
        norms = features[~missing].norm(dim=-1)
        self.assertTrue(torch.allclose(norms, torch.ones_like(norms), atol=1e-5))

    def test_restored_network_gives_identical_forecasts_without_training_dataset(self) -> None:
        data = curriculum(self.perception, 5017, 8)
        expected = prediction_scores(self.predictor, data)
        restored_perception, restored_predictor = load(self.pilot / "models.pt")
        actual = prediction_scores(restored_predictor, curriculum(restored_perception, 5017, 8))
        self.assertEqual(expected, actual)
        self.assertFalse(hasattr(restored_predictor, "history"))

    def test_nonfinite_predictive_checkpoint_is_rejected(self) -> None:
        path = Path(self.directory.name) / "invalid.pt"
        payload = torch.load(self.pilot / "models.pt", weights_only=True)
        payload["predictor"]["mean.weight"][0, 0] = float("nan")
        torch.save(payload, path)
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            load(path)

    def test_long_curriculum_has_real_counterfactual_actions_and_masked_dropouts(self) -> None:
        features, actions, gaps, present = long_curriculum(self.perception, 11017, 8, 64)
        self.assertTrue((actions != actions.roll(1, 0)).any())
        self.assertGreater((actions[:, 1:] == actions[:, :-1]).float().mean().item(), .3)
        self.assertTrue((present == 0).any())
        self.assertEqual(features[present.squeeze(-1) == 0].count_nonzero().item(), 0)
        self.assertEqual(gaps.shape, (8, 64, 1))
        repeated = long_curriculum(self.perception, 11017, 8, 64)
        self.assertTrue(all(torch.equal(left, right) for left, right in zip((features, actions, gaps, present), repeated)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
