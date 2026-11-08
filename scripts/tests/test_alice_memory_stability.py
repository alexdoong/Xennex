"""Retention contracts: parameter protection, representative routes and sources."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.alice_memory.adaptive_memory import AdaptiveMemory, recalled_pair
from scripts.alice_memory.episodic_memory import EpisodicMemory
from scripts.alice_memory.neural_consolidation import consolidation_cycle
from scripts.alice_memory.protected_memory import ProtectedMemory, restore as restore_protected
from scripts.alice_memory.reactivation_index import ReactivationIndex, restore as restore_index


def cue(values):
    return torch.nn.functional.one_hot(torch.tensor(values), num_classes=4).flatten().double()


class StabilityContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def model(self, **options):
        return ProtectedMemory(**{**dict(key_size=2, value_size=1, architecture="linear", window=2,
                                         inner_steps=1, momentum=0., period=2), **options})

    def assert_state(self, actual, state):
        self.assertTrue(all(torch.equal(value, actual.state_dict()[name]) for name, value in state.items()))

    def source(self, capacity=16, count=3):
        memory = EpisodicMemory(capacity)
        for index in range(count):
            memory.observe(cue((index, 0, (index + 1) % 4, 0)), float(index + 1), True)
        routes = ReactivationIndex(capacity, seed=123)
        for index in range(count):
            routes.observe(memory, index, memory.clock)
        return memory, routes

    def test_periodic_anchor_and_sensitivity_are_learned_inside_write(self):
        model = self.model()
        original = model.anchor_0.clone()
        model.write(torch.tensor([1., 0.]), torch.tensor([1.]), 1.)
        self.assertTrue(torch.equal(original, model.anchor_0))
        self.assertGreater(model.sensitivity_0.sum().item(), 0.)
        self.assertEqual(int(model.consolidations), 0)
        model.write(torch.tensor([0., 1.]), torch.tensor([0.]), 2.)
        self.assertEqual(int(model.consolidations), 1)
        self.assertTrue(torch.equal(model.anchor_0, model.network.weight))

    def test_protection_penalty_is_zero_at_anchor_and_positive_after_displacement(self):
        model = self.model(period=1)
        model.write(torch.tensor([1., 0.]), torch.tensor([1.]), 1.)
        base_loss = AdaptiveMemory._loss(model)
        self.assertTrue(torch.equal(base_loss, model._loss()))
        with torch.no_grad():
            model.network.weight.add_(.2)
        self.assertGreater(model._loss().item(), AdaptiveMemory._loss(model).item())

    def test_zero_stability_reproduces_the_unprotected_gradient_exactly(self):
        model = self.model(stability=0.)
        baseline = AdaptiveMemory(**model.config)
        baseline.load_state_dict(model.snapshot()["adaptive"]["state"])
        for step in range(7):
            key = torch.tensor([1., 0.]) if step % 2 else torch.tensor([0., 1.])
            value = torch.tensor([step / 10])
            model.write(key, value, float(step))
            baseline.write(key, value, float(step))
        for name, parameter in baseline.network.state_dict().items():
            self.assertTrue(torch.equal(parameter, model.network.state_dict()[name]))

    def test_failed_protected_write_restores_sensitivity_anchor_and_base_state(self):
        model = self.model()
        before = copy.deepcopy(model.state_dict())
        def failure():
            model.anchor_0.add_(1.)
            model.sensitivity_0.add_(1.)
            model.consolidations.add_(1)
            raise RuntimeError("injected")
        with patch.object(model, "_update", side_effect=failure), self.assertRaises(RuntimeError):
            model.write(torch.tensor([1., 0.]), torch.tensor([1.]), 1.)
        self.assert_state(model, before)

    def test_protected_checkpoint_next_gradient_and_clear_context_are_exact(self):
        model = self.model(momentum=.8, inner_steps=3)
        for step in range(4):
            model.write(torch.tensor([.3, .7]), torch.tensor([.8]), float(step))
        payload = model.snapshot()
        rng = torch.get_rng_state().clone()
        resumed = restore_protected(payload)
        self.assertTrue(torch.equal(rng, torch.get_rng_state()))
        for candidate in (model, resumed):
            candidate.write(torch.tensor([.7, .3]), torch.tensor([.2]), 5.)
        self.assert_state(resumed, model.state_dict())
        before = resumed.read(torch.tensor([.3, .7]))
        resumed.clear_working_context()
        self.assertTrue(torch.equal(before, resumed.read(torch.tensor([.3, .7]))))
        resumed.anchor_0.zero_()
        self.assertTrue(payload["state"]["anchor_0"].count_nonzero())

    def test_invalid_protected_counter_and_sensitivity_preserve_caller_rng(self):
        model = self.model()
        payload = model.snapshot()
        rng = torch.get_rng_state().clone()
        payload["state"]["consolidations"].fill_(1)
        with self.assertRaises(ValueError):
            restore_protected(payload)
        self.assertTrue(torch.equal(rng, torch.get_rng_state()))
        payload = model.snapshot()
        payload["state"]["sensitivity_0"].fill_(-1.)
        with self.assertRaises(ValueError):
            restore_protected(payload)

    def test_latest_source_replaces_route_without_erasing_old_episode(self):
        memory, routes = self.source(count=1)
        memory.observe(cue((0, 0, 3, 0)), 2., True)
        routes.observe(memory, 1, 2.)
        self.assertEqual(int(routes.count), 1)
        pair = routes.select(memory, 1)["pairs"][0]
        self.assertEqual(pair["source_episode"], 1)
        self.assertEqual(pair["value"].argmax().item(), 3)
        self.assertEqual(recalled_pair(memory, 0, 2.)["value"].argmax().item(), 1)
        before = copy.deepcopy(routes.state_dict())
        self.assertFalse(routes.observe(memory, 0, 2.)["indexed"])
        self.assert_state(routes, before)

    def test_duplicate_source_and_excluded_current_visit_are_not_reactivated(self):
        memory, routes = self.source()
        before = copy.deepcopy(routes.state_dict())
        self.assertFalse(routes.observe(memory, 2, memory.clock)["indexed"])
        self.assert_state(routes, before)
        result = routes.select(memory, 3, exclude=2)
        self.assertEqual(result["attempted"], 2)
        self.assertEqual({pair["source_episode"] for pair in result["pairs"]}, {0, 1})

    def test_no_cached_target_can_replace_erased_source_weights(self):
        memory, routes = self.source(count=1)
        memory.blocks[0].banks[6].weights.zero_()
        result = routes.select(memory, 1)
        self.assertEqual(result["pairs"], [])
        self.assertEqual(result["skipped"][0]["reason"], "source weights changed")
        self.assertEqual(routes.metrics()["cached_target_values"], 0)
        self.assertEqual(routes.select(memory, 1, policy="history")["pairs"], [])

    def test_source_revision_requires_refresh_before_reactivation(self):
        memory, routes = self.source(count=1)
        memory.revise(cue((0, 0, 1, 0)), 2, torch.tensor([0., 0., 0., 1., 0.]), 2.)
        memory.clock = 2.
        self.assertEqual(routes.select(memory, 1)["pairs"], [])
        self.assertTrue(routes.observe(memory, 0, 2.)["indexed"])
        self.assertEqual(routes.select(memory, 1)["pairs"][0]["value"].argmax().item(), 3)

    def test_revised_input_cue_replaces_obsolete_route_and_checkpoint_stays_valid(self):
        memory, _ = self.source(count=1)
        routes = ReactivationIndex(memory.capacity, capacity=1)
        routes.observe(memory, 0, memory.clock)
        memory.revise(cue((0, 0, 1, 0)), 3, torch.tensor([0., 1., 0., 0., 0.]), 2.)
        memory.clock = 2.
        self.assertTrue(routes.observe(memory, 0, 2.)["indexed"])
        self.assertEqual(int(routes.count), 1)
        restored = restore_index(routes.snapshot(), memory)
        self.assertEqual(restored.select(memory, 1)["pairs"][0]["key"].reshape(3, 4)[2].argmax().item(), 1)
        initial = memory.read(cue((0, 0, 0, 0)), 2., view="initial")
        self.assertEqual(initial["distributions"][3].index(max(initial["distributions"][3])), 0)

    def test_capacity_failure_and_invalid_requests_preserve_routes_and_rng(self):
        memory, _ = self.source(count=2)
        routes = ReactivationIndex(memory.capacity, capacity=1)
        routes.observe(memory, 0, memory.clock)
        before = copy.deepcopy(routes.state_dict())
        rng = routes.generator.get_state().clone()
        with self.assertRaises(ValueError):
            routes.observe(memory, 1, memory.clock)
        self.assert_state(routes, before)
        for limit, exclude in ((True, None), (17, None), (1, 999)):
            with self.assertRaises(ValueError):
                routes.select(memory, limit, exclude)
        self.assertTrue(torch.equal(rng, routes.generator.get_state()))

    def test_sampling_io_failure_restores_rng_before_retry(self):
        memory, routes = self.source()
        rng = routes.generator.get_state().clone()
        with patch("scripts.alice_memory.reactivation_index.recalled_pair", side_effect=OSError("injected")), self.assertRaises(OSError):
            routes.select(memory, 3)
        self.assertTrue(torch.equal(rng, routes.generator.get_state()))

    def test_checkpoint_resumes_sampler_owns_tensors_and_verifies_source_digest(self):
        memory, routes = self.source()
        payload = routes.snapshot()
        rng = torch.get_rng_state().clone()
        resumed = restore_index(payload, memory)
        self.assertTrue(torch.equal(rng, torch.get_rng_state()))
        first, second = routes.select(memory, 2), resumed.select(memory, 2)
        self.assertEqual([pair["source_episode"] for pair in first["pairs"]], [pair["source_episode"] for pair in second["pairs"]])
        self.assertTrue(torch.equal(routes.generator.get_state(), resumed.generator.get_state()))
        resumed.keys.zero_()
        self.assertTrue(payload["state"]["keys"].count_nonzero())
        memory.blocks[0].banks[6].weights.add_(.1)
        with self.assertRaises(ValueError):
            restore_index(payload, memory)

    def test_checkpoint_rejects_future_and_duplicate_routes_and_invalid_sampler(self):
        memory, routes = self.source()
        for name, value in (("clock", memory.clock + 1.), ("count", routes.capacity + 1), ("updates", -1)):
            payload = routes.snapshot()
            payload["state"][name].fill_(value)
            with self.assertRaises(ValueError):
                restore_index(payload, memory)
        payload = routes.snapshot()
        payload["generator"] = torch.zeros(1, dtype=torch.uint8)
        with self.assertRaises(ValueError):
            restore_index(payload, memory)
        payload = routes.snapshot()
        for name in ("keys", "episodes", "revisions", "learned_at", "digests"):
            payload["state"][name][1].copy_(payload["state"][name][0])
        with self.assertRaises(ValueError):
            restore_index(payload, memory)

    def test_multi_source_cycle_failure_rolls_back_weights_routes_and_sampler(self):
        memory, routes = self.source()
        model = AdaptiveMemory(window=16)
        before = copy.deepcopy(model.state_dict())
        index_state = routes.snapshot()
        original = model.write
        calls = []
        def fail_on_second(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError("second source failed")
            return original(*args, **kwargs)
        with patch.object(model, "write", side_effect=fail_on_second), self.assertRaises(RuntimeError):
            consolidation_cycle(model, routes, memory, 2)
        self.assert_state(model, before)
        self.assert_state(routes, index_state["state"])
        self.assertTrue(torch.equal(index_state["generator"], routes.generator.get_state()))
        self.assertEqual(recalled_pair(memory, 0, memory.clock)["value"].argmax().item(), 1)

    def test_cycle_budget_preflights_all_writes_and_rewinds_sampler(self):
        memory, routes = self.source()
        model = AdaptiveMemory(window=16)
        model.writes.fill_(99999)
        before = copy.deepcopy(model.state_dict())
        index_state = routes.snapshot()
        with self.assertRaises(ValueError):
            consolidation_cycle(model, routes, memory, 2)
        self.assert_state(model, before)
        self.assert_state(routes, index_state["state"])
        self.assertTrue(torch.equal(index_state["generator"], routes.generator.get_state()))


if __name__ == "__main__":
    unittest.main()
