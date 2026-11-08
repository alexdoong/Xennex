"""Sound-to-name uses earlier paired episodes and an independently taught visual name."""
import unittest

import torch

from scripts.alice_memory.concept_query_language import sha
from scripts.alice_memory.native_grounding import NativeGrounding, restore
from scripts.alice_memory.native_sensor import NativeObservation


def packet(modality, axis, at, sequence, origin='environment'):
    vector = torch.nn.functional.one_hot(torch.tensor(axis), 128).float()
    return NativeObservation(modality, vector, at, sequence, sha(f'{modality}-{sequence}'), origin=origin)


def name_image(core, moment, name):
    return core.teach_retained_name(name, core.moments.reference(moment), 'image', 'person', core.clock,
        {'kind': 'external_word_reply', 'reply_sha256': sha(name), 'request_sha256': sha('Qual nome?')})


class NativeAudioNamingContracts(unittest.TestCase):
    def mind(self):
        core = NativeGrounding(implicit_recall=True)
        self.addCleanup(core.moments.close)
        return core

    def pair(self, core, sequence, image=0, sound=7):
        at = float(sequence + 1)
        return core.observe([packet('image', image, at, sequence), packet('audio', sound, at, sequence)], at)['moment']

    def test_sound_recalls_an_externally_named_image_without_teaching_the_audio_reader(self):
        core = self.mind()
        original = self.pair(core, 0)
        cue = packet('audio', 7, 2., 1)
        self.assertFalse(core.recognize_visual_name_from_sound(cue)['supported'])
        self.assertTrue(name_image(core, original, 'maruvi')['learned'])
        self.assertFalse(core.recognize(cue)['supported'])
        later = core.observe([cue], 2.)
        result = later['audio_association']
        self.assertEqual(result['name'], 'maruvi')
        self.assertEqual(result['sources'], [core.moments.reference(original)])
        self.assertFalse(result['directly_observed'])
        self.assertFalse(result['word_learning'])
        self.assertEqual(core.moments.reference(later['moment'])['known'], [False, True, False])
        self.assertEqual(int(core.readers['audio'].writes), 0)

        reopened = restore(core.snapshot(), core.clock)
        self.addCleanup(reopened.moments.close)
        again = reopened.observe([packet('audio', 7, 3., 2)], 3.)
        self.assertEqual(again['audio_association']['name'], 'maruvi')
        reopened.readers['image'].weights.zero_()
        self.assertFalse(reopened.recognize_visual_name_from_sound(packet('audio', 7, 3., 2))['supported'])

    def test_same_sound_in_two_named_scenes_requires_agreement(self):
        core = self.mind()
        self.pair(core, 0)
        self.pair(core, 1, image=1)
        name_image(core, 0, 'maruvi')
        cue = packet('audio', 7, 3., 2)
        self.assertEqual(core.recognize_visual_name_from_sound(cue)['reason'], 'remembered_image_has_no_supported_name')
        name_image(core, 1, 'selavo')
        self.assertEqual(core.recognize_visual_name_from_sound(cue)['reason'], 'conflicting_visual_names')

    def test_coarse_similarity_does_not_override_a_supported_association(self):
        from dataclasses import replace
        core = self.mind()
        self.pair(core, 0)
        competitor = packet('audio', 7, 2., 1)
        mixed = .92 * competitor.latent + (1 - .92 ** 2) ** .5 * packet('audio', 8, 2., 1).latent
        core.observe([packet('image', 1, 2., 1), replace(competitor, latent=mixed)], 2.)
        name_image(core, 0, 'maruvi')
        name_image(core, 1, 'selavo')
        result = core.recognize_visual_name_from_sound(packet('audio', 7, 3., 2))
        self.assertEqual(result['name'], 'maruvi')
        self.assertEqual([ref['id'] for ref in result['sources']], [0])

    def test_repeated_paired_episodes_can_agree_and_future_events_cannot_support_delayed_audio(self):
        core = self.mind()
        self.pair(core, 0)
        self.pair(core, 1)
        name_image(core, 0, 'maruvi')
        cue = packet('audio', 7, 3., 2)
        self.assertEqual([ref['id'] for ref in core.recognize_visual_name_from_sound(cue)['sources']], [0, 1])
        late = packet('audio', 7, 1.5, 2, origin='person')
        result = core.observe([late], 3.)['audio_association']
        self.assertEqual([ref['id'] for ref in result['sources']], [0])
        missing = packet('audio', 15, 3., 3)
        self.assertEqual(core.recognize_visual_name_from_sound(missing)['reason'], 'no_matching_audio_visual_moment')


if __name__ == '__main__':
    unittest.main()
