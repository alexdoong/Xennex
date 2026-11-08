"""Context-conditioned transfer, causal acquisition and contextual abstention."""
import copy
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import torch
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alice_memory.native_grounding import NativeGrounding, restore as restore_grounding
from scripts.alice_memory.native_links import NativeLinks, restore
from scripts.alice_memory.native_moments import NativeMoments
from scripts.alice_memory.native_sensor import NativeObservation
from scripts.alice_memory.online_memory import OnlineMemory


def packet(name, value, now, sequence):
    return NativeObservation(name, F.normalize(value.float(), dim=0), now, sequence, 'a' * 64)


class ContextualLinkContracts(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)

    def test_reserved_correspondence_changes_with_context_without_changing_cue(self):
        for seed in (17, 29, 71):
            generator = torch.Generator().manual_seed(seed)
            visual = torch.linalg.qr(torch.randn(128, 128, generator=generator)).Q
            sound = torch.linalg.qr(torch.randn(128, 128, generator=generator)).Q
            history = F.normalize(torch.randn(128, generator=generator), dim=0)
            links = NativeLinks()
            for index in range(16):
                sign = 1 if index % 2 == 0 else -1
                theta = ((index // 2) % 4) * math.pi / 2
                cue = math.cos(theta) * visual[:, 0] + math.sin(theta) * visual[:, 1]
                expected = sign * (math.cos(theta) * sound[:, 0] + math.sin(theta) * sound[:, 1])
                now = float(index + 1)
                links.observe([packet('image', cue, now, index), packet('audio', expected, now, index)], now, sign * history)
            payload = links.snapshot()
            resumed = restore(payload, 16., 16)
            for index in range(12):
                theta = (index + .5) * math.pi / 6
                cue = packet('image', math.cos(theta) * visual[:, 0] + math.sin(theta) * visual[:, 1], 16., 0)
                expected = math.cos(theta) * sound[:, 0] + math.sin(theta) * sound[:, 1]
                self.assertFalse(links.predict(cue, 'audio')['supported'])  # Opposite outcomes average to zero.
                for sign in (1, -1):
                    prediction = links.predict(cue, 'audio', sign * history)
                    self.assertTrue(prediction['supported'])
                    self.assertTrue(prediction['conditioned_on_context'])
                    self.assertGreater(float(prediction['latent'] @ (sign * expected)), .999)
                    self.assertTrue(torch.equal(resumed.predict(cue, 'audio', sign * history)['latent'], prediction['latent']))
            unfamiliar = F.normalize(torch.randn(128, generator=generator), dim=0)
            self.assertFalse(links.predict(cue, 'audio', unfamiliar)['supported'])
            links.contextual_banks['image:audio'].weights.zero_()
            self.assertFalse(links.predict(cue, 'audio', history)['supported'])

    def test_real_prior_state_is_used_before_receiving_target_and_after_episode_retirement(self):
        native = NativeGrounding()
        native.moments.close()
        native.moments = NativeMoments(2, 1)
        marker = F.one_hot(torch.tensor(32), 128).float()
        visual = F.one_hot(torch.tensor(1), 128).float()
        sound = F.one_hot(torch.tensor(63), 128).float()
        sequence = 0
        def prime(sign):
            nonlocal sequence
            for _ in range(8):
                at = native.clock + .1
                native.observe([packet('image', sign * marker, at, sequence)], at)
                sequence += 1
        try:
            for trial in range(16):
                sign = 1 if trial % 2 == 0 else -1
                prime(sign)
                at = native.clock + .1
                previous = native.working.clone() * 2. ** (-.1 / 5.)
                original = native.links.observe
                contexts = []
                def record(packets, now, context):
                    contexts.append(context.clone())
                    return original(packets, now, context)
                with patch.object(native.links, 'observe', side_effect=record):
                    native.observe([packet('image', visual, at, sequence), packet('audio', sign * sound, at, sequence)], at)
                self.assertTrue(torch.allclose(contexts[0], previous, atol=1e-6, rtol=0))
                self.assertFalse(torch.allclose(contexts[0], native.working))
                sequence += 1
            for sign in (1, -1):
                prime(sign)
                cue = packet('image', visual, native.clock, 0)
                prediction = native.associate(cue, 'audio', contextual=True)
                self.assertTrue(prediction['supported'])
                self.assertGreater(float(prediction['latent'] @ (sign * sound)), .99)
                self.assertFalse(native.recall_moments([cue])['supported'])
            self.assertFalse(native.names)
            self.assertEqual(native.links.context_frames, 16)
            resumed = restore_grounding(native.snapshot(), native.clock)
            try:
                self.assertTrue(torch.equal(resumed.associate(cue, 'audio', contextual=True)['latent'], prediction['latent']))
            finally:
                resumed.moments.close()
        finally:
            native.moments.close()

    def test_absent_small_context_and_single_channel_do_not_train_conditioned_pair(self):
        links = NativeLinks()
        vector = F.one_hot(torch.tensor(0), 128).float()
        pair = [packet('image', vector, 1., 0), packet('audio', vector, 1., 0)]
        links.observe(pair, 1., torch.zeros(128))
        self.assertEqual(links.context_frames, 0)
        self.assertEqual(links.predict(pair[0], 'audio', torch.zeros(128))['reason'], 'no_conditioning_context')
        links.observe([packet('image', vector, 2., 1)], 2., vector)
        self.assertEqual(links.context_frames, 0)

    def test_failed_conditioned_direction_keeps_both_model_groups_and_counts(self):
        links = NativeLinks()
        vector = F.one_hot(torch.tensor(0), 128).float()
        original = OnlineMemory.write
        calls = []
        def fail(bank, *args, **kwargs):
            calls.append(bank)
            if len(calls) == 4:
                raise ValueError('second conditioned direction refused')
            return original(bank, *args, **kwargs)
        with patch.object(OnlineMemory, 'write', fail):
            with self.assertRaises(ValueError):
                links.observe([packet('image', vector, 1., 0), packet('audio', vector, 1., 0)], 1., vector)
        self.assertEqual((links.frames, links.context_frames, links.clock), (0, 0, 0.))
        self.assertTrue(all(int(bank.writes) == 0 for bank in (*links.banks.values(), *links.contextual_banks.values())))

    def test_migration_does_not_invent_past_context_and_restoration_refuses_corruption(self):
        links = NativeLinks()
        vector = F.one_hot(torch.tensor(0), 128).float()
        pair = [packet('image', vector, 1., 0), packet('audio', vector, 1., 0)]
        links.observe(pair, 1., vector)
        payload = links.snapshot()
        old = copy.deepcopy(payload)
        old['format'] = 1
        for name in ('contextual_banks', 'context_frames', 'feature_basis', 'retention_rule', 'retention_seconds', 'updated_at'):
            old.pop(name)
        resumed = restore(old, 1., 1)
        self.assertTrue(resumed.predict(pair[0], 'audio')['supported'])
        self.assertFalse(resumed.predict(pair[0], 'audio', vector)['supported'])
        for corruption in ('basis', 'count', 'nan', 'precision', 'hidden'):
            bad = copy.deepcopy(payload)
            if corruption == 'basis':
                bad['feature_basis'] = 'another-projection'
            elif corruption == 'count':
                bad['context_frames'] = 0
            elif corruption == 'nan':
                bad['contextual_banks']['image:audio']['weights'][0, 0] = float('nan')
            elif corruption == 'precision':
                bad['contextual_banks']['image:audio']['precision'].zero_()
            else:
                bad['contextual_banks']['image:text']['weights'][0, 0] = 1.
            with self.assertRaises(ValueError):
                restore(bad, 1., 1)


if __name__ == '__main__':
    unittest.main()
