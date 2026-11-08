"""Visual detail routes, controls, and source binding without a model download."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import torch
from PIL import Image

from scripts.alice_memory.native_encoder import NativeEncoder
from scripts.alice_memory.native_encoder_worker import run as encode_worker
from scripts.alice_memory.native_batch import validate_receipt
from scripts.alice_memory.mirage_detector import MirageDetector
from scripts.alice_memory.mirage_regions import select_boxes
from scripts.alice_memory.native_grounding import NativeGrounding
from scripts.alice_memory.native_moments import NativeMoments, restore
from scripts.alice_memory.native_regions import validate_boxes
from scripts.alice_memory.native_sensor import NativeObservation

ROOT = Path(__file__).resolve().parents[2]


def vector(axis):
    return torch.nn.functional.one_hot(torch.tensor(axis), 128).float()


def packet(modality, axis, sequence):
    digest = f'{1 + sequence + (128 if modality == "audio" else 0):064x}'
    return NativeObservation(modality, vector(axis), float(sequence + 1), sequence, digest)


def detail(image, *axes):
    return {'source_sha256': image.sample_sha256, 'boxes': [[i, 0, i + 1, 1] for i in range(len(axes))],
            'routes': torch.stack([vector(axis) for axis in axes])}


class RegionContracts(unittest.TestCase):
    def archive(self, capacity=4):
        memory = NativeMoments(capacity=capacity, hot_limit=1)
        self.addCleanup(memory.close)
        return memory

    def test_crop_routes_to_audio_across_backgrounds_with_no_text_or_new_write(self):
        memory = self.archive()
        original, distractor, query = [packet('image', axis, i) for i, axis in enumerate((0, 1, 1))]
        audio = packet('audio', 20, 0)
        memory.capture([original, audio], 1., regions=detail(original, 9))
        memory.capture([distractor, packet('audio', 21, 1)], 2., regions=detail(distractor, 10))
        scene_only = memory.recall([query], 3., reactivate=False)
        self.assertEqual(scene_only['moment']['id'], 1)
        actual = memory.recall_regions(query, detail(query, 9), 3.)['entries'][0]
        wrong_frame = memory.recall_regions(query, detail(query, 10), 3.)['entries'][0]
        self.assertEqual((actual['moment']['id'], wrong_frame['moment']['id']), (0, 1))
        self.assertTrue(torch.equal(actual['representations']['audio'], audio.latent))
        self.assertEqual(memory.next_id, 2)
        self.assertEqual([trace['recalls'] for trace in memory.traces], [0, 0])

    def test_matching_objects_in_separate_moments_are_ambiguous_without_paging(self):
        memory = self.archive()
        for i in range(2):
            image = packet('image', i, i)
            memory.capture([image], i + 1., regions=detail(image, 10, 11))
        query = packet('image', 2, 2)
        result = memory.recall_regions(query, detail(query, 11), 3.)
        self.assertEqual(result, {'entries': [], 'candidate_count': 2, 'reason': 'ambiguous_regions'})
        self.assertEqual(memory.loads, 0)
        self.assertEqual(memory.recall_regions(query, detail(query, 12), 3.)['reason'], 'no_supported_region')

    def test_regional_archive_roundtrip_rejects_foreign_source_and_retires_with_moment(self):
        memory = self.archive(capacity=1)
        image = packet('image', 0, 0)
        regions = detail(image, 5)
        memory.capture([image], 1., regions=regions)
        regions['routes'].zero_()
        saved = memory.snapshot()
        recovered = restore(saved, 1.)
        self.addCleanup(recovered.close)
        self.assertEqual(saved['format'], 7)
        self.assertTrue(torch.equal(recovered.regions[0]['routes'][0], vector(5)))
        bad = copy.deepcopy(saved)
        bad['regions'][0]['source_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'source image'):
            restore(bad, 1.)
        recovered.capture([packet('image', 1, 1)], 2.)
        self.assertEqual(recovered.regions, {})
        self.assertEqual(recovered.snapshot()['format'], 5)

    def test_live_route_uses_regional_evidence_only_when_vision_is_attended(self):
        mind = NativeGrounding(implicit_recall=True)
        self.addCleanup(mind.moments.close)
        first, query = packet('image', 0, 0), packet('image', 1, 1)
        mind.observe([first, packet('audio', 20, 0)], 1., regions=detail(first, 9))
        output = mind.observe([query], 2., regions=detail(query, 9))
        self.assertEqual(output['implicit_reactivation']['moments'], [0])
        self.assertEqual(output['implicit_reactivation']['visual_route'], 'supported')
        self.assertEqual(mind.moments.get(0)['recalls'], 1)
        self.assertEqual(mind.names, [])
        unattended = packet('image', 2, 2)
        with patch.object(mind.attention, 'choose', return_value={'id': None, 'modalities': ['audio']}):
            output = mind.observe([unattended, packet('audio', 21, 2)], 3., regions=detail(unattended, 9))
        self.assertNotIn(output['moment'], mind.moments.regions)
        self.assertNotIn('visual_route', output['implicit_reactivation'])

    def test_crop_uses_actual_source_pixels_and_bounds(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'bin') as folder:
            path = Path(folder) / 'image.png'
            source = Image.new('RGB', (6, 5), 'red')
            source.paste((0, 255, 0), (2, 1, 4, 4))
            source.save(path)
            encoder = NativeEncoder(folder, 'image')
            seen = []

            def inspect(signal):
                image = signal['image']
                seen.append((image.size, image.getpixel((0, 0))))
                return vector(len(seen))

            with patch.object(encoder, 'encode_signal', side_effect=inspect):
                image, record = encoder.encode_image_regions(path, 1., 0, 'environment', [[2, 1, 4, 4]])
                self.assertEqual(seen, [((6, 5), (255, 0, 0)), ((2, 3), (0, 255, 0))])
                self.assertEqual(image.sample_sha256, record['source_sha256'])
                with self.assertRaisesRegex(ValueError, 'beyond'):
                    encoder.encode_image_regions(path, 1., 0, 'environment', [[2, 1, 7, 4]])
                self.assertEqual(len(seen), 2)
        for boxes in ([[0, 0, 2, 2]] * 2, [[False, 0, 1, 1]], [[1, 0, 1, 2]]):
            with self.assertRaises(ValueError):
                validate_boxes(boxes)

    def test_encoder_worker_receipt_binds_crops_to_its_owned_request(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'bin') as folder:
            root = Path(folder)
            signals = root / 'signals'
            signals.mkdir()
            file = 'a' * 32 + '.png'
            Image.new('RGB', (10, 10), 'red').save(signals / file)
            request, output = root / 'request.json', root / 'output.pt'
            token = 'b' * 32
            items = [{'file': file, 'modality': 'image', 'origin': 'person', 'sequence': 1,
                      'acquired_at': 1., 'image_regions': [[0, 0, 5, 5]]}]
            request.write_text(json.dumps({'format': 1, 'token': token, 'model_folder': str(root),
                                           'mode': 'sequential', 'ram_fraction': .75, 'items': items}))
            with patch.object(NativeEncoder, 'encode_signal', side_effect=[vector(3), vector(4)]):
                encode_worker(request, output)
            saved = torch.load(output, weights_only=True)
            image, = validate_receipt(saved, items, root, token)
            self.assertTrue(torch.equal(image.latent, vector(3)))
            self.assertTrue(torch.equal(saved['regions'][0]['routes'][0], vector(4)))
            saved['regions'][0]['source_sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'source image'):
                validate_receipt(saved, items, root, token)

    def test_automatic_worker_filters_background_and_keeps_scene_on_unavailable_detector(self):
        detection = {'objects': [{'bbox': [0, 0, 999, 999], 'score': .99},
                                 {'bbox': [200, 100, 700, 500], 'score': .4}]}
        self.assertEqual(select_boxes(detection, 10, 10, skip_scene=True), [[2, 1, 7, 5]])
        with tempfile.TemporaryDirectory(dir=ROOT / 'bin') as folder:
            root = Path(folder)
            signals = root / 'signals'
            signals.mkdir()
            file = 'a' * 32 + '.png'
            Image.new('RGB', (10, 10), 'red').save(signals / file)
            request, output = root / 'request.json', root / 'output.pt'
            token = 'b' * 32
            items = [{'file': file, 'modality': 'image', 'origin': 'person', 'sequence': i,
                      'acquired_at': 1., 'auto_regions': True} for i in range(3)]
            request.write_text(json.dumps({'format': 1, 'token': token, 'model_folder': str(root), 'mirage_folder': str(root),
                                           'mode': 'sequential', 'ram_fraction': .75, 'items': items}))
            with (patch.object(NativeEncoder, 'admit'), patch.object(NativeEncoder, 'encode_signal', return_value=vector(3)),
                  patch.object(MirageDetector, 'boxes', side_effect=[[[2, 1, 7, 5]], None, OSError('asset unavailable')])):
                encode_worker(request, output)
            saved = torch.load(output, weights_only=True)
            self.assertEqual(len(validate_receipt(saved, items, root, token)), 3)
            self.assertEqual(saved['region_status'], {0: 'detected', 1: 'no_useful_box', 2: 'detector_error'})
            self.assertEqual(list(saved['regions']), [0])
            saved['region_status'][1] = 'detected'
            with self.assertRaisesRegex(ValueError, 'requested regions'):
                validate_receipt(saved, items, root, token)


if __name__ == '__main__':
    unittest.main()
