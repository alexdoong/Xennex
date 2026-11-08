"""Learned field roles, cautious projection, source integrity and continuation."""
from __future__ import annotations

import copy
import random
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.alice_memory.episodic_memory import EpisodicMemory
from scripts.alice_memory.projected_semantic_memory import ProjectedSemanticMemory, restore


def cue(values):
    return torch.nn.functional.one_hot(torch.tensor(values), num_classes=4).flatten().double()


class ProjectionContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)
        cls.fixtures = []
        # The nuisance field changes roles. No field name or irrelevant mask
        # enters training; targets are teaching data for the associative kernel.
        for ignored in range(4):
            memory = EpisodicMemory(128)
            model = ProjectedSemanticMemory(memory, seed=793017)
            model.bank.config['inner_steps'] = 16
            rng = random.Random(123)
            for round_number in range(3):
                values = [(a, b, n) for a in range(4) for b in range(4) for n in (0, 2)]
                rng.shuffle(values)
                for a, b, nuisance in values:
                    key = [a, b, nuisance] if ignored == 3 else [a, b]
                    if ignored != 3:
                        key.insert(ignored, nuisance)
                    target = (a + b + (nuisance if ignored == 3 else 0)) % 4
                    full = (key[0], key[1], target, key[2])
                    memory.observe(cue(full), memory.clock + 1., True)
                    model.consolidate(memory, len(memory.blocks) - 1, memory.clock)
            cls.fixtures.append((memory, model.snapshot()))

    def fixture(self, role=1):
        memory, payload = self.fixtures[role]
        return memory, restore(payload, memory)

    def test_three_roles_are_inferred_from_actual_gradient_learning(self):
        for role in range(3):
            memory, model = self.fixture(role)
            self.assertEqual(int(model.projection.ignored), role)
            correct, total = 0, 0
            for a in range(4):
                for b in range(4):
                    key = [a, b]
                    key.insert(role, 1)
                    query = cue((key[0], key[1], 0, key[2]))
                    result = model.predict(query)
                    total += 1
                    correct += result['supported'] and int(torch.tensor(result['distribution']).argmax()) == (a + b) % 4
                    self.assertEqual(result.get('ignored_field'), [0, 1, 3][role])
            self.assertEqual((correct, total), (16, 16))

    def test_missing_ignored_field_is_projected_but_required_fields_are_not_invented(self):
        memory, model = self.fixture()
        query = cue((0, 0, 0, 1))
        query[4:8] = 0
        self.assertTrue(model.predict(query)['supported'])
        query[:4] = 0
        self.assertFalse(model.predict(query)['supported'])
        noisy = cue((0, 0, 0, 1))
        noisy[4:8] = .25
        self.assertTrue(model.predict(noisy)['supported'])
        noisy[:4] = .25
        self.assertFalse(model.predict(noisy)['supported'])

    def test_query_target_does_not_supply_the_projected_answer_and_reads_do_not_learn(self):
        memory, model = self.fixture()
        before = model.transaction_state()
        first, second = cue((1, 1, 0, 1)), cue((1, 1, 3, 1))
        saved = second.clone()
        self.assertEqual(model.predict(first), model.predict(second))
        self.assertTrue(torch.equal(second, saved))
        self.assertTrue(all(torch.equal(value, model.state_dict()[name]) for name, value in before[0].items()))
        self.assertTrue(torch.equal(before[1], model.index.generator.get_state()))

    def test_erased_kernel_cannot_answer_from_the_projection_or_route_index(self):
        memory, model = self.fixture()
        with torch.no_grad():
            for parameter in model.bank.network.parameters():
                parameter.zero_()
        self.assertFalse(model.predict(cue((0, 1, 0, 1)))['supported'])

    def test_two_witness_reads_are_bounded_and_storage_failure_abstains(self):
        memory, model = self.fixture()
        from scripts.alice_memory.reactivation_index import source_digest
        with patch('scripts.alice_memory.projected_semantic_memory.source_digest', wraps=source_digest) as reader:
            result = model.predict(cue((0, 1, 0, 1)))
        self.assertTrue(result['supported'])
        self.assertEqual(reader.call_count, 2)
        with patch('scripts.alice_memory.projected_semantic_memory.source_digest', side_effect=OSError('injected')):
            self.assertEqual(model.predict(cue((0, 1, 0, 1)))['reason'], 'source storage unavailable')

    def test_projection_fit_failure_rolls_back_gradients_sampler_and_source_ledger(self):
        # A separate owner keeps the shared teaching fixtures immutable.
        memory = EpisodicMemory(16)
        model = ProjectedSemanticMemory(memory)
        memory.observe(cue((0, 0, 1, 0)), 1., True)
        model.consolidate(memory, 0, 1.)
        before = model.transaction_state()
        memory.observe(cue((1, 0, 2, 1)), 2., True)
        def fail(*args):
            model.projection.effects.fill_(1.)
            raise RuntimeError('injected')
        with patch.object(model.projection, 'fit', side_effect=fail), self.assertRaises(RuntimeError):
            model.consolidate(memory, 1, 2.)
        self.assertTrue(all(torch.equal(value, model.state_dict()[name]) for name, value in before[0].items()))
        self.assertTrue(torch.equal(before[1], model.index.generator.get_state()))

    def test_manual_mask_and_effects_are_rejected_and_callers_rng_is_preserved(self):
        memory, model = self.fixture()
        for name in ('ignored', 'effects', 'fitted_writes'):
            payload = copy.deepcopy(model.snapshot())
            payload['projection'][name].add_(1)
            rng = torch.get_rng_state().clone()
            with self.assertRaises(ValueError):
                restore(payload, memory)
            self.assertTrue(torch.equal(rng, torch.get_rng_state()))

    def test_projection_requires_coverage_not_merely_a_constant_confident_function(self):
        memory = EpisodicMemory(16)
        model = ProjectedSemanticMemory(memory)
        for episode in range(8):
            memory.observe(cue((episode % 4, (episode % 2) * 2, 1, 0)), float(episode + 1), True)
            model.consolidate(memory, episode, memory.clock)
        self.assertEqual(int(model.projection.ignored), -1)
        self.assertFalse(model.predict(cue((0, 1, 0, 3)))['supported'])

    def test_all_three_influential_fields_do_not_receive_an_ignored_mask(self):
        memory, model = self.fixture(3)
        self.assertEqual(int(model.projection.ignored), -1)
        self.assertFalse(model.predict(cue((0, 0, 0, 1)))['supported'])

    def test_changed_second_witness_cannot_be_replaced_by_the_saved_projection(self):
        memory, model = self.fixture()
        query = cue((0, 1, 0, 1))
        witness = model.predict(query)['witnesses'][1]
        bank = memory.blocks[witness].banks[6]
        before = bank.weights.clone()
        try:
            bank.weights.zero_()
            self.assertEqual(model.predict(query)['reason'], 'source weights changed')
        finally:
            bank.weights.copy_(before)


if __name__ == '__main__':
    unittest.main()
