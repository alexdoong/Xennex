"""Explicit fixture worker for native stream delay, refusal and broken receipts."""
import argparse
import hashlib
import json
import os
import time
from pathlib import Path

import torch

from scripts.alice_memory.loop_checkpoint import atomic_write
from scripts.alice_memory.native_sensor import NativeObservation, REPRESENTATION
from scripts.alice_memory.process_metrics import memory_usage
from scripts.alice_memory.runtime_store import atomic_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--outcome', type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding='utf-8'))
    config = json.loads(Path(os.environ['ALICE_FAKE_NATIVE_CONFIG']).read_text(encoding='utf-8'))
    delay = config.get('delay', .2)
    if not isinstance(delay, (float, int)) or not 0 <= delay <= 5:
        raise ValueError("Invalid fake native delay.")
    time.sleep(delay)
    mode = config.get('mode', 'normal')
    status = 'deferred' if mode == 'deferred' else 'ready'
    items = []
    regions = {}
    region_status = {}
    acoustic = {}
    for index, item in enumerate(request['items']):
        path = args.request.parent / 'signals' / item['file']
        latent = torch.nn.functional.one_hot(torch.tensor({'image': 0, 'audio': 3, 'text': 6}[item['modality']]), 128).float()
        packet = NativeObservation(item['modality'], latent, item['acquired_at'], item['sequence'], hashlib.sha256(path.read_bytes()).hexdigest(), origin=item['origin'])
        items.append(vars(packet).copy())
        boxes = item.get('image_regions')
        if item.get('auto_regions'):
            region_status[index] = config.get('automatic_result', 'detected')
            if region_status[index] == 'detected':
                boxes = [[10, 12, 90, 80]]
        if boxes is not None:
            vectors = [torch.nn.functional.one_hot(torch.tensor(box[0] % 128), 128).float() for box in boxes]
            regions[index] = {'source_sha256': packet.sample_sha256, 'boxes': boxes, 'routes': torch.stack(vectors)}
        if item.get('word_audio'):
            acoustic[index] = torch.zeros(10, 24)
    if mode == 'changed_hash':
        items[0]['sample_sha256'] = '0' * 64
    if mode == 'changed_source':
        items[0]['acquired_at'] += 1.
    if mode == 'changed_region_box' and regions:
        next(iter(regions.values()))['boxes'][0][0] += 1
    if status == 'ready':
        payload = {'format': 3 if region_status else (2 if regions else 1), 'token': request['token'], 'representation': REPRESENTATION,
                   'items': items, 'resources': memory_usage()}
        if regions or region_status:
            payload['regions'] = regions
        if region_status:
            payload['region_status'] = region_status
        if acoustic:
            payload['format'] += 4
            payload['acoustic'] = acoustic
        atomic_write(args.output, payload)
    atomic_json(args.outcome, {'format': 1, 'token': request['token'], 'status': status,
                               'error': 'fixture admission' if status == 'deferred' else None})


if __name__ == '__main__':
    main()
