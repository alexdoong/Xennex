"""Owned finite encoding process, with CPU/RAM isolation and checked receipts."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import torch

from .native_encoder import file_digest
from .native_regions import DETECTION_STATUSES, validate_regions
from .native_sensor import NativeObservation, REPRESENTATION
from .process_metrics import physical_memory
from .runtime_store import atomic_json


def validate_receipt(payload, items, folder, token):
    requested = {index: item['image_regions'] for index, item in enumerate(items) if 'image_regions' in item}
    automatic = {index for index, item in enumerate(items) if item.get('auto_regions')}
    spoken = {index for index, item in enumerate(items) if item.get('word_audio')}
    fields = {'format', 'token', 'representation', 'items', 'resources'}
    if requested or automatic:
        fields.add('regions')
    if automatic:
        fields.add('region_status')
    if spoken:
        fields.add('acoustic')
    version = (3 if automatic else (2 if requested else 1)) + (4 if spoken else 0)
    if not isinstance(payload, dict) or set(payload) != fields or type(payload['format']) is not int or payload['format'] != version or payload['token'] != token or payload['representation'] != REPRESENTATION or not isinstance(payload['items'], list) or len(payload['items']) != len(items):
        raise ValueError("Native encoder receipt changed its request.")
    packets = []
    for record, expected in zip(payload['items'], items):
        if not isinstance(record, dict) or set(record) != {'modality', 'latent', 'acquired_at', 'sequence', 'sample_sha256', 'representation', 'origin'}:
            raise ValueError("Invalid native receipt percept fields.")
        packet = NativeObservation(**record)
        packet.validate()
        if any(record[name] != expected[name] for name in ('modality', 'acquired_at', 'sequence', 'origin')) or packet.sample_sha256 != file_digest(folder / 'signals' / expected['file']):
            raise ValueError("Native encoder receipt changed the signal or source.")
        packets.append(packet)
    regions = payload.get('regions', {})
    status = payload.get('region_status', {})
    if not isinstance(status, dict) or set(status) != automatic or any(type(index) is not int or value not in DETECTION_STATUSES for index, value in status.items()):
        raise ValueError('Native encoder receipt changed its automatic region outcomes.')
    expected = set(requested) | {index for index, value in status.items() if value == 'detected'}
    if not isinstance(regions, dict) or set(regions) != expected or any(type(index) is not int for index in regions):
        raise ValueError('Native encoder receipt changed its requested regions.')
    for index, record in regions.items():
        validate_regions(record, packets[index].sample_sha256, requested.get(index))
    patterns = payload.get('acoustic', {})
    if not isinstance(patterns, dict) or set(patterns) != spoken or any(type(index) is not int for index in patterns):
        raise ValueError('Native encoder receipt changed its acoustic word sources.')
    if spoken:
        from .spoken_pattern import validate
        for pattern in patterns.values():
            if pattern is not None:
                validate(pattern)
    return packets


def encode_batch(folder, model_folder, interpreter, items, ram_fraction=.75, on_tick=None):
    folder = folder.resolve()
    if not Path(interpreter).is_file() or not isinstance(items, list) or not 1 <= len(items) <= 64:
        raise ValueError("Native batch requires an installed interpreter and bounded signals.")
    if isinstance(ram_fraction, bool) or not isinstance(ram_fraction, (float, int)) or not .5 <= ram_fraction <= .9:
        raise ValueError("Invalid native batch RAM budget.")
    request, output = folder / ('encode-' + uuid4().hex + '.json'), folder / ('encode-' + uuid4().hex + '.pt')
    token = uuid4().hex
    atomic_json(request, {'format': 1, 'token': token, 'model_folder': str(model_folder.resolve()),
                          'mode': 'full', 'ram_fraction': ram_fraction, 'items': items})
    environment = os.environ.copy()
    environment.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', PYTHONIOENCODING='utf-8')
    process = None
    samples = []
    started = previous = time.monotonic()
    try:
        with (folder / 'encoder.stdout.log').open('wb') as stdout, (folder / 'encoder.stderr.log').open('wb') as stderr:
            process = subprocess.Popen([str(interpreter), '-m', 'scripts.alice_memory.native_encoder_worker', '--request', str(request),
                                        '--output', str(output)], cwd=Path(__file__).resolve().parents[2], env=environment,
                                       stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                       creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        while process.poll() is None:
            now = time.monotonic()
            if now - started > 240:
                raise TimeoutError("Native encoder exceeded its finite four-minute deadline.")
            ram = physical_memory()
            samples.append(ram['used_bytes'])
            if ram['used_bytes'] > ram['total_bytes'] * ram_fraction:
                raise RuntimeError("Actual RAM crossed the native encoder's authorized limit.")
            if on_tick is not None:
                on_tick(now - previous)
            previous = now
            time.sleep(.05)
        if process.returncode != 0 or not output.is_file() or output.stat().st_size > 200000:
            raise ValueError("Native encoder exited without a bounded receipt; inspect encoder.stderr.log.")
        payload = torch.load(output, map_location='cpu', weights_only=True)
        packets = validate_receipt(payload, items, folder, token)
        return packets, {'encoder': payload['resources'], 'peak_sampled_pc_ram_bytes': max(samples, default=physical_memory()['used_bytes']),
                         'worker_wall_seconds': time.monotonic() - started, 'worker_terminal': True}
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=5)
