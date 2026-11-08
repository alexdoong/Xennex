"""One finite local encoding batch; runs in the isolated perception interpreter."""
from __future__ import annotations

import argparse
import json
import re
import gc
from pathlib import Path

from .native_encoder import NativeEncoder
from .loop_checkpoint import atomic_write
from .native_sensor import REPRESENTATION
from .native_regions import validate_boxes
from .process_metrics import memory_usage


def run(request, output):
    if request.stat().st_size > 32768:
        raise ValueError("Native batch exceeds its request budget.")
    value = json.loads(request.read_text(encoding='utf-8'))
    fields = {'format', 'token', 'model_folder', 'mode', 'ram_fraction', 'items'}
    if not isinstance(value, dict) or set(value) not in (fields, fields | {'mirage_folder'}) or type(value['format']) is not int or value['format'] != 1:
        raise ValueError("Invalid native batch request.")
    if not isinstance(value['token'], str) or re.fullmatch(r'[0-9a-f]{32}', value['token']) is None:
        raise ValueError("Invalid native batch identity.")
    if not isinstance(value['items'], list) or not 1 <= len(value['items']) <= 64:
        raise ValueError("Invalid native batch size.")
    if value['mode'] not in ('full', 'image', 'audio', 'sequential'):
        raise ValueError("Invalid native batch encoder mode.")
    root = (request.parent / 'signals').resolve()
    items = [None] * len(value['items'])
    regions = {}
    region_status = {}
    acoustic = {}
    prepared = []
    for item in value['items']:
        fields = {'modality', 'file', 'sequence', 'acquired_at', 'origin'}
        if not isinstance(item, dict) or set(item) not in (fields, fields | {'image_regions'}, fields | {'auto_regions'}, fields | {'word_audio'}):
            raise ValueError("Invalid native batch signal fields.")
        if 'word_audio' in item and (item['word_audio'] is not True or item['modality'] != 'audio' or value['mode'] == 'image'):
            raise ValueError('An acoustic word requires audio encoding.')
        if 'auto_regions' in item and (item['auto_regions'] is not True or item['modality'] != 'image' or value['mode'] == 'audio'):
            raise ValueError('Automatic regions require an image encoder.')
        if 'image_regions' in item:
            if item['modality'] != 'image' or value['mode'] == 'audio':
                raise ValueError('Visual regions require an image encoder.')
            validate_boxes(item['image_regions'])
        filename = item['file']
        if not isinstance(filename, str) or Path(filename).name != filename or re.fullmatch(r'[0-9a-f]{32}\.(png|wav|txt)', filename) is None:
            raise ValueError("Native signal must be a flat owned filename.")
        path = root / filename
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("Native signal escapes its owned folder.")
        prepared.append((path, item))
    automatic = any(item.get('auto_regions') for _, item in prepared)
    if automatic != ('mirage_folder' in value) or (automatic and (not isinstance(value['mirage_folder'], str) or not value['mirage_folder'])):
        raise ValueError('Automatic regions require their local detector folder.')
    detector = None
    if automatic:
        from .mirage_detector import MirageDetector
        detector = MirageDetector(value['mirage_folder'])
    groups = [('image', {'image', 'text'}), ('audio', {'audio'})] if value['mode'] == 'sequential' else [(value['mode'], {'image', 'audio', 'text'})]
    for mode, modalities in groups:
        selected = [(index, path, item) for index, (path, item) in enumerate(prepared) if item['modality'] in modalities]
        if not selected:
            continue
        encoder = NativeEncoder(value['model_folder'], mode, value['ram_fraction'])
        for index, path, item in selected:
            if 'image_regions' in item:
                packet, regions[index] = encoder.encode_image_regions(path, item['acquired_at'], item['sequence'],
                                                                     item['origin'], item['image_regions'])
            elif item.get('auto_regions'):
                packet, record, region_status[index] = encoder.encode_detected_regions(
                    path, item['acquired_at'], item['sequence'], item['origin'], detector.boxes)
                if record is not None:
                    regions[index] = record
            elif item.get('word_audio'):
                packet, acoustic[index] = encoder.encode_word_audio(path, item['acquired_at'], item['sequence'], item['origin'])
            else:
                packet = encoder.encode(path, item['modality'], item['acquired_at'], item['sequence'], item['origin'])
            items[index] = vars(packet).copy()
        del encoder
        gc.collect()
    regional = {'regions': regions, 'region_status': region_status} if automatic else ({'regions': regions} if regions else {})
    version = 3 if automatic else (2 if regional else 1)
    acoustics = {'acoustic': acoustic} if acoustic else {}
    atomic_write(output, {'format': version + (4 if acoustics else 0), 'token': value['token'], 'representation': REPRESENTATION,
                          'items': items, 'resources': memory_usage(), **regional, **acoustics})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    run(args.request, args.output)


if __name__ == '__main__':
    main()
