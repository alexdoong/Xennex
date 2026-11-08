"""Contracts for bounded learning of isolated spoken forms."""
import copy
import unittest

import numpy as np
import torch

from scripts.alice_memory.native_moments import NativeMoments, restore
from scripts.alice_memory.native_pronunciation import recognize, teach, validate_result
from scripts.alice_memory.native_sensor import NativeObservation
from scripts.alice_memory.spoken_pattern import describe, distance


def descriptor(level, frames=12):
    pattern = torch.ones(frames, 24) * level
    pattern[:frames // 3, 0] += 1.
    return pattern


class PronunciationContracts(unittest.TestCase):
    def memory(self, capacity=8):
        result = NativeMoments(capacity=capacity, hot_limit=1)
        self.addCleanup(result.close)
        return result

    def sound(self, memory, i, digest=None, origin='person'):
        latent = torch.nn.functional.one_hot(torch.tensor(i % 128), 128).float()
        packet = NativeObservation('audio', latent, i + 1., i, digest or f'{i:064x}', origin=origin)
        return memory.capture([packet], packet.acquired_at)

    def test_speed_alignment_and_unknown_after_restore_preserve_literal_source(self):
        memory = self.memory()
        self.sound(memory, 0)
        self.sound(memory, 1)
        self.assertEqual(teach(memory, 0, 'janela', descriptor(0.)), {'status': 'learned', 'word': 'janela'})
        teach(memory, 1, 'chuva', descriptor(2.))
        self.sound(memory, 2, origin='environment')
        saved = memory.snapshot()
        self.assertEqual(saved['format'], 9)
        restored = restore(saved, memory.clock)
        self.addCleanup(restored.close)
        result = recognize(restored, 2, descriptor(0., 18))
        self.assertEqual(result['word'], 'janela')
        self.assertEqual(result['source'], restored.reference(0))
        self.assertEqual(set(restored.pronunciations), {0, 1})
        self.assertEqual(recognize(restored, 2, descriptor(1.))['status'], 'unmatched')
        validate_result(result, restored, restored.reference(2), True, None)
        with self.assertRaises(ValueError):
            validate_result({**result, 'source': restored.reference(2)}, restored, restored.reference(2), True, None)
        bad = copy.deepcopy(saved)
        bad['pronunciations'][0]['audio_sha256'] = 'a' * 64
        with self.assertRaises(ValueError):
            restore(bad, memory.clock)

    def test_duplicate_conflicting_and_non_teacher_samples_do_not_change_vocabulary(self):
        memory = self.memory()
        for index in range(2):
            self.sound(memory, index, digest='c' * 64)
        self.sound(memory, 2, origin='environment')
        teach(memory, 0, 'pato', descriptor(0.))
        self.assertEqual(teach(memory, 1, 'pato', descriptor(0.))['status'], 'duplicate')
        self.assertEqual(teach(memory, 1, 'gato', descriptor(0.))['status'], 'conflicting_example')
        with self.assertRaises(ValueError):
            teach(memory, 2, 'pato', descriptor(0.))
        self.assertEqual(set(memory.pronunciations), {0})

    def test_ambiguous_words_and_retired_episodes_do_not_report_a_match(self):
        memory = self.memory()
        for index in range(3):
            self.sound(memory, index)
        teach(memory, 0, 'chuva', descriptor(0.))
        teach(memory, 1, 'uva', descriptor(.04))
        self.assertEqual(recognize(memory, 2, descriptor(.02))['status'], 'ambiguous')
        small = self.memory(capacity=1)
        self.sound(small, 0)
        teach(small, 0, 'chuva', descriptor(0.))
        self.sound(small, 1)
        self.assertEqual(small.pronunciations, {})
        self.assertEqual(recognize(small, 1, descriptor(0.))['status'], 'unmatched')

    def test_descriptors_ignore_leading_silence_and_reject_unusable_clips(self):
        samples = (.3 * np.sin(2 * np.pi * 380 * np.arange(8000) / 16000)).astype(np.float32)
        base = describe(samples)
        delayed = describe(np.pad(samples, (3200, 0)))
        self.assertLess(distance(base, delayed), .15)
        self.assertIsNone(describe(np.zeros(16000, np.float32)))
        self.assertIsNone(describe(np.tile(samples, 8)))


if __name__ == '__main__':
    unittest.main()
