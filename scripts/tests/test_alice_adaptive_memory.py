"""Numerical, bounded-state and provenance contracts for the research kernel."""
from __future__ import annotations

import copy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.alice_memory.adaptive_memory import AdaptiveMemory, load, recalled_pair, restore, save
from scripts.alice_memory.episodic_memory import EpisodicMemory


class AdaptiveContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def model(self, **overrides):
        return AdaptiveMemory(**{**dict(key_size=2, value_size=1, architecture="linear", window=2,
                                       momentum=0., learning_rate=.1, inner_steps=1), **overrides})

    def assert_state(self, model, state):
        self.assertTrue(all(torch.equal(value, model.state_dict()[name]) for name, value in state.items()))

    def test_one_linear_step_matches_finite_difference_gradient(self):
        model = self.model()
        key, value = torch.tensor([.3, .7]), torch.tensor([.8])
        parameter = tuple(model.network.parameters())[0]
        epsilon = 1e-6
        before = parameter.clone()
        gradient = torch.zeros_like(before)
        with torch.no_grad():
            for index in range(2):
                parameter[0, index] += epsilon
                high = (model.read(key) - value.double()).square().item()
                parameter[0, index] -= 2 * epsilon
                low = (model.read(key) - value.double()).square().item()
                parameter.copy_(before)
                gradient[0, index] = (high - low) / (2 * epsilon)
        model.write(key, value, 1.)
        self.assertTrue(torch.allclose(parameter, before - .1 * gradient, atol=1e-8, rtol=1e-8))

    def test_recent_window_errors_are_recomputed_at_current_weights(self):
        model = self.model()
        key1, key2 = torch.tensor([1., 0.]), torch.tensor([0., 1.])
        model.write(key1, torch.tensor([1.]), 1.)
        weight, bias = model.network.weight.detach().clone(), model.network.bias.detach().clone()
        error1 = (model.read(key1) - 1.).item()
        error2 = model.read(key2).item()
        model.write(key2, torch.tensor([0.]), 2.)
        self.assertTrue(torch.allclose(model.network.weight, weight - .1 * torch.tensor([[error1, error2]], dtype=torch.float64)))
        self.assertTrue(torch.allclose(model.network.bias, bias - .1 * (error1 + error2)))

    def test_huber_bounds_an_extreme_target_influence(self):
        mse = self.model(window=1)
        robust = self.model(window=1, loss="huber", huber_delta=.25)
        with torch.no_grad():
            mse.network.weight.zero_()
            mse.network.bias.zero_()
            robust.network.load_state_dict(mse.network.state_dict())
        key = torch.tensor([1., 0.])
        mse.write(key, torch.tensor([100.]), 1.)
        robust.write(key, torch.tensor([100.]), 1.)
        self.assertAlmostEqual(mse.read(key).item(), 40.)
        self.assertAlmostEqual(robust.read(key).item(), .05)

    def test_weight_decay_applies_even_with_zero_prediction_error(self):
        model = self.model(retention=.01)
        key = torch.tensor([1., 0.])
        value = model.read(key)
        weight = model.network.weight.detach().clone()
        model.write(key, value, 1.)
        self.assertTrue(torch.equal(model.network.weight, weight * .99))

    def test_window_cap_and_clearing_leave_learned_reads_unchanged(self):
        model = self.model(window=4)
        key = torch.tensor([1., 0.])
        for index in range(23):
            model.write(key, torch.tensor([.8]), float(index))
        self.assertEqual(int(model.count), 4)
        self.assertEqual(model.metrics()["working_context_bytes"], 128)
        before = model.read(key)
        model.clear_working_context()
        self.assertTrue(torch.equal(before, model.read(key)))
        self.assertEqual(model.metrics()["working_context_count"], 0)
        self.assertEqual(int(model.writes), 23)
        restore(model.snapshot())

    def test_read_does_not_write_or_consult_working_examples(self):
        model = self.model()
        model.write(torch.tensor([1., 0.]), torch.tensor([1.]), 1.)
        before = copy.deepcopy(model.state_dict())
        first = model.read(torch.tensor([1., 0.]))
        self.assert_state(model, before)
        model.keys.fill_(99.)
        model.values.fill_(99.)
        self.assertTrue(torch.equal(first, model.read(torch.tensor([1., 0.]))))

    def test_invalid_write_inputs_leave_every_tensor_unchanged(self):
        model = self.model()
        key, value = torch.tensor([1., 0.]), torch.tensor([1.])
        model.write(key, value, 2.)
        state = copy.deepcopy(model.state_dict())
        for bad_key, bad_value, now, strength in ((key, value, 1., 1.), (key, value, True, 1.),
                                                (key, value, 3., 0.), (key, value, 3., True),
                                                (torch.tensor([float("nan"), 0.]), value, 3., 1.),
                                                (torch.tensor([101., 0.]), value, 3., 1.),
                                                (key.long(), value, 3., 1.), (key, torch.ones(2), 3., 1.)):
            with self.subTest(now=now, strength=strength), self.assertRaises(ValueError):
                model.write(bad_key, bad_value, now, strength)
            self.assert_state(model, state)

    def test_update_failure_rolls_back_window_weights_clock_and_momentum(self):
        model = self.model(architecture="mlp", momentum=.8, inner_steps=4)
        state = copy.deepcopy(model.state_dict())
        def failure():
            with torch.no_grad():
                model.network[0].weight.add_(1.)
                model.velocity_0.add_(2.)
            raise RuntimeError("injected update failure")
        with patch.object(model, "_update", side_effect=failure), self.assertRaises(RuntimeError):
            model.write(torch.tensor([1., 0.]), torch.tensor([1.]), 1.)
        self.assert_state(model, state)

    def test_write_budget_preflights_before_window_mutation(self):
        model = self.model()
        model.writes.fill_(100000)
        state = copy.deepcopy(model.state_dict())
        with self.assertRaises(ValueError):
            model.write(torch.tensor([1., 0.]), torch.tensor([1.]), 1.)
        self.assert_state(model, state)

    def test_nested_no_grad_caller_can_still_learn_without_parameter_grad_buffers(self):
        model = self.model(architecture="mlp")
        key = torch.tensor([1., 0.])
        before = model.read(key)
        with torch.no_grad():
            model.write(key, torch.tensor([1.]), 1.)
        self.assertFalse(torch.equal(before, model.read(key)))
        self.assertTrue(all(parameter.grad is None for parameter in model.parameters()))

    def test_checkpoint_owns_tensors_and_preserves_rng_on_success_or_failure(self):
        model = self.model(architecture="mlp", momentum=.8)
        model.write(torch.tensor([1., 0.]), torch.tensor([.5]), 1.)
        payload = model.snapshot()
        rng = torch.get_rng_state().clone()
        copied = restore(payload)
        self.assertTrue(torch.equal(rng, torch.get_rng_state()))
        copied.keys.zero_()
        self.assertNotEqual(payload["state"]["keys"].count_nonzero().item(), 0)
        payload["state"]["cursor"].fill_(999)
        with self.assertRaises(ValueError):
            restore(payload)
        self.assertTrue(torch.equal(rng, torch.get_rng_state()))

    def test_checkpoint_rejects_missing_tensors_nonfinite_unused_context_and_counters(self):
        model = self.model()
        invalids = []
        for field, value in (("count", 3), ("writes", -1), ("clock", -1.)):
            payload = model.snapshot()
            payload["state"][field].fill_(value)
            invalids.append(payload)
        payload = model.snapshot()
        payload["state"]["keys"][1, 0] = 1.
        invalids.append(payload)
        payload = model.snapshot()
        payload["state"]["network.weight"][0, 0] = float("nan")
        invalids.append(payload)
        payload = model.snapshot()
        del payload["state"]["velocity_0"]
        invalids.append(payload)
        for payload in invalids:
            with self.assertRaises(ValueError):
                restore(payload)

    def test_fresh_process_resumes_next_gradient_step_exactly(self):
        model = self.model(architecture="mlp", momentum=.8, window=4, inner_steps=3)
        key = torch.tensor([.2, .8])
        for index in range(7):
            model.write(key, torch.tensor([index / 10]), float(index))
        with tempfile.TemporaryDirectory(dir=ROOT / "bin" / "AliceMemory") as directory:
            source, result = Path(directory) / "model.pt", Path(directory) / "next.pt"
            save(source, model)
            code = "from pathlib import Path; import torch; from scripts.alice_memory.adaptive_memory import load,save; torch.set_num_threads(1); m=load(Path(__import__('sys').argv[1])); m.write(torch.tensor([.7,.3]),torch.tensor([.9]),8.); save(Path(__import__('sys').argv[2]),m)"
            subprocess.run([sys.executable, "-c", code, str(source), str(result)], cwd=ROOT,
                           check=True, capture_output=True, timeout=30)
            model.write(torch.tensor([.7, .3]), torch.tensor([.9]), 8.)
            self.assert_state(load(result), model.state_dict())

    def test_recalled_targets_require_source_weights_and_exclude_target_from_key(self):
        memory = EpisodicMemory()
        cue = torch.nn.functional.one_hot(torch.tensor([0, 1, 2, 3]), num_classes=4).flatten().double()
        memory.observe(cue, 1., True)
        pair = recalled_pair(memory, 0, 1.)
        self.assertIsNotNone(pair)
        self.assertEqual(pair["key"].numel(), 12)
        self.assertEqual(pair["value"].argmax().item(), 2)
        memory.blocks[0].banks[6].weights.zero_()
        self.assertIsNone(recalled_pair(memory, 0, 1.))


if __name__ == "__main__":
    unittest.main()
