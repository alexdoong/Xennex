"""Offline EmbeddingGemma 2 adapter; optional dependencies stay in its worker.

This module consumes local signals. It never asks a language model for a caption
or transcript. Pretrained features are distinct from associations Alice learns.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import wave
from pathlib import Path

import torch
from torch.nn import functional as F

from .language import AdmissionDeferred
from .native_sensor import NativeObservation, REVISION
from .process_metrics import physical_memory

FILE_SET = '7f27c3586fd1e16df69ffd0a0ecb58df69d89bcbee20d7a78ba99b0b5775c96a'


def file_digest(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify_model(folder):
    folder = folder.resolve()
    marker = folder / 'download-manifest.json'
    if marker.is_symlink() or marker.stat().st_size > 32768:
        raise ValueError("Invalid native encoder manifest.")
    manifest = json.loads(marker.read_text(encoding='utf-8'))
    if not isinstance(manifest, dict) or manifest.get('revision') != REVISION or not isinstance(manifest.get('files'), list):
        raise ValueError("Native encoder is not the pinned revision.")
    records = manifest['files']
    if any(not isinstance(item, dict) or set(item) != {'file', 'size', 'sha256'} or not isinstance(item['file'], str) for item in records):
        raise ValueError("Invalid native encoder file records.")
    canonical = json.dumps(sorted(records, key=lambda item: item['file']), sort_keys=True)
    if hashlib.sha256(canonical.encode()).hexdigest() != FILE_SET:
        raise ValueError("Native encoder file set differs from its verified release.")
    for item in records:
        path = folder / item['file']
        if path.is_symlink() or not path.resolve().is_relative_to(folder) or path.stat().st_size != item['size'] or file_digest(path) != item['sha256']:
            raise ValueError("Native encoder checksum/size mismatch.")
    return sum(item['size'] for item in records)


class NativeEncoder:
    def __init__(self, folder, mode='full', ram_fraction=.75):
        if mode not in ('full', 'image', 'audio') or isinstance(ram_fraction, bool) or not isinstance(ram_fraction, (int, float)) or not .5 <= ram_fraction <= .9:
            raise ValueError("Invalid encoder mode/RAM budget.")
        self.folder, self.mode, self.ram_fraction = Path(folder), mode, ram_fraction
        self.model = None

    def admit(self, reserve=0):
        measured = physical_memory()
        if measured['used_bytes'] + reserve > measured['total_bytes'] * self.ram_fraction:
            raise AdmissionDeferred(measured, reserve, self.ram_fraction)

    def load(self):
        if self.model is not None:
            return
        size = verify_model(self.folder)
        # Conservative effective BF16 weights for the selected architecture;
        # the full checkpoint on SSD does not mean every encoder is resident.
        effective = size if self.mode == 'full' else min(size, 900_000_000 if self.mode == 'image' else 1_200_000_000)
        self.admit(effective * 1.5 + 384 * 1024**2)
        # No remote code, inputs or downloads are allowed during inference.
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        from sentence_transformers import SentenceTransformer
        config = {} if self.mode == 'full' else {'audio_config': None} if self.mode == 'image' else {'vision_config': None}
        torch.set_num_threads(2)
        self.model = SentenceTransformer(str(self.folder), device='cpu', local_files_only=True,
                                        trust_remote_code=False, config_kwargs=config,
                                        model_kwargs={'dtype': torch.bfloat16, 'attn_implementation': 'eager'})
        self.admit()

    def read_signal(self, path, modality):
        from PIL import Image
        path = Path(path)
        if modality not in ('image', 'audio', 'text') or not path.is_file() or path.stat().st_size > 32_000_000:
            raise ValueError("Native input requires a bounded local signal file.")
        with path.open('rb') as stream:
            data = stream.read(32_000_001)
        if len(data) > 32_000_000:
            raise ValueError("Native signal grew beyond its byte budget.")
        digest = hashlib.sha256(data).hexdigest()
        if modality == 'text':
            if len(data) > 16000:
                raise ValueError("Native text exceeds its byte budget.")
            text = data.decode('utf-8-sig')
            if not 1 <= len(text) <= 4000:
                raise ValueError("Native text exceeds its character budget.")
            return text, digest
        if modality == 'image':
            if self.mode == 'audio':
                raise ValueError("Vision encoder is not loaded in audio mode.")
            with Image.open(io.BytesIO(data)) as image:
                if image.width * image.height > 4_000_000:
                    raise ValueError("Native image exceeds its pixel budget.")
                return {'image': image.convert('RGB').copy()}, digest
        if self.mode == 'image':
            raise ValueError("Audio encoder is not loaded in image mode.")
        import numpy as np
        with wave.open(io.BytesIO(data), 'rb') as stream:
            channels, width, rate, count = stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getnframes()
            if channels not in (1, 2) or width != 2 or not 8000 <= rate <= 48000 or not 1 <= count <= rate * 10 or stream.getcomptype() != 'NONE':
                raise ValueError("Native sound requires PCM16 mono/stereo, 8–48 kHz, at most ten seconds.")
            raw = stream.readframes(count)
            if len(raw) != count * channels * width:
                raise ValueError("Native WAV is truncated.")
        samples = torch.from_numpy(np.frombuffer(raw, dtype='<i2').copy()).float().reshape(-1, channels).mean(-1) / 32768.
        if rate != 16000:
            from torchaudio.functional import resample
            samples = resample(samples, rate, 16000)
        return {'audio': samples.numpy()}, digest

    def encode(self, path, modality, acquired_at, sequence, origin='environment'):
        signal, digest = self.read_signal(path, modality)
        latent = self.encode_signal(signal)
        result = NativeObservation(modality, latent, acquired_at, sequence, digest, origin=origin)
        result.validate()
        return result

    def encode_word_audio(self, path, acquired_at, sequence, origin):
        from .spoken_pattern import describe
        signal, digest = self.read_signal(path, 'audio')
        packet = NativeObservation('audio', self.encode_signal(signal), acquired_at, sequence, digest, origin=origin)
        packet.validate()
        return packet, describe(signal['audio'])

    def encode_image_regions(self, path, acquired_at, sequence, origin, boxes):
        from .native_regions import validate_boxes
        validate_boxes(boxes)
        signal, digest = self.read_signal(path, 'image')
        return self.encode_image(signal, digest, acquired_at, sequence, origin, boxes)

    def encode_detected_regions(self, path, acquired_at, sequence, origin, detector):
        signal, digest = self.read_signal(path, 'image')
        self.admit()
        try:
            boxes = detector(signal['image'])
            status = 'detected' if boxes else 'no_useful_box'
        except (OSError, RuntimeError, ValueError):
            boxes, status = None, 'detector_error'
        self.admit()
        packet, regions = self.encode_image(signal, digest, acquired_at, sequence, origin, boxes)
        return packet, regions, status

    def encode_image(self, signal, digest, acquired_at, sequence, origin, boxes):
        from .native_regions import validate_regions
        image = signal['image']
        if boxes and any(right > image.width or bottom > image.height for _, _, right, bottom in boxes):
            raise ValueError('A visual region extends beyond its source image.')
        packet = NativeObservation('image', self.encode_signal(signal), acquired_at, sequence, digest, origin=origin)
        packet.validate()
        if not boxes:
            return packet, None
        routes = torch.stack([self.encode_signal({'image': image.crop(box)}) for box in boxes])
        regions = {'source_sha256': digest, 'boxes': boxes, 'routes': routes}
        validate_regions(regions, digest)
        return packet, regions

    def encode_signal(self, signal):
        self.load()
        self.admit()
        with torch.inference_mode():
            latent = self.model.encode(signal, convert_to_tensor=True, normalize_embeddings=True, truncate_dim=128,
                                       processing_kwargs={'image': {'max_soft_tokens': 70}})
        self.admit()
        return F.normalize(latent.detach().cpu().float(), dim=0)
