"""Nonblocking owned native worker; pending raw sources remain in the inbox."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import torch

from .native_batch import validate_receipt
from .native_encoder import file_digest
from .process_metrics import physical_memory
from .runtime_store import atomic_json


class NativeProcess:
    def __init__(self, jobs, inbox, folder, models, interpreter, ram_fraction=.75,
                 module='scripts.alice_memory.native_stream_worker', environment=None, *, mirage_folder=None):
        self.root = Path(folder).resolve()
        self.folder = self.root / uuid4().hex
        self.folder.mkdir(parents=True)
        self.signals = self.folder / 'signals'
        self.signals.mkdir()
        self.token = uuid4().hex
        self.items = []
        self.files = []
        self.process = None
        self.ram_fraction = ram_fraction
        self.deadline = time.monotonic() + 240.
        self.stopping = None
        self.request, self.output, self.outcome = (self.folder / name for name in ('request.json', 'output.pt', 'outcome.json'))
        try:
            for job in jobs:
                source = inbox.frame_path(job['frame'])
                if inbox.read(job['frame']) != job['manifest']:
                    raise ValueError("Native source manifest changed while pending.")
                for item in job['manifest']['files']:
                    filename = uuid4().hex + Path(item['file']).suffix
                    target = self.signals / filename
                    self.files.append(target)
                    shutil.copyfile(source / item['file'], target)
                    if target.stat().st_size != item['size'] or file_digest(target) != item['sha256']:
                        raise ValueError("Native source changed during its worker copy.")
                    self.items.append({'modality': item['modality'], 'file': filename, 'sequence': job['id'],
                                       'acquired_at': job['acquired_at'], 'origin': job['manifest']['origin']})
                    if item['modality'] == 'audio' and job['manifest'].get('word_audio'):
                        self.items[-1]['word_audio'] = True
                    if item['modality'] != 'image':
                        continue
                    if 'image_regions' in job['manifest']:
                        self.items[-1]['image_regions'] = job['manifest']['image_regions']
                    elif mirage_folder is not None:
                        self.items[-1]['auto_regions'] = True
            detector = {'mirage_folder': str(Path(mirage_folder).resolve())} if any(item.get('auto_regions') for item in self.items) else {}
            atomic_json(self.request, {'format': 1, 'token': self.token, 'model_folder': str(Path(models).resolve()),
                                      'mode': 'sequential', 'ram_fraction': ram_fraction, 'items': self.items, **detector})
            env = os.environ.copy()
            env.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', PYTHONIOENCODING='utf-8')
            env.update(environment or {})
            with (self.folder / 'stdout.log').open('wb') as stdout, (self.folder / 'stderr.log').open('wb') as stderr:
                self.process = subprocess.Popen([str(Path(interpreter).resolve()), '-m', module, '--request', str(self.request),
                                                 '--output', str(self.output), '--outcome', str(self.outcome)],
                                                cwd=Path(__file__).resolve().parents[2], stdin=subprocess.DEVNULL,
                                                stdout=stdout, stderr=stderr, env=env,
                                                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        except BaseException:
            self.close()
            raise

    def cancel(self, reason='cancelled'):
        self.stopping = reason
        if self.process is not None and self.process.poll() is None:
            self.process.kill()

    def poll(self):
        if self.process.poll() is None:
            ram = physical_memory()
            if ram['used_bytes'] > ram['total_bytes'] * self.ram_fraction:
                self.cancel('resource_limit_crossed')
            if time.monotonic() >= self.deadline:
                self.cancel('worker_deadline')
            for name in ('stdout.log', 'stderr.log'):
                if (self.folder / name).stat().st_size > 100000:
                    self.cancel('worker_log_budget')
            return None
        if self.stopping is not None:
            return {'status': 'failed', 'error': self.stopping}
        if self.process.returncode != 0 or not self.outcome.is_file() or self.outcome.is_symlink() or self.outcome.stat().st_size > 4096:
            return {'status': 'failed', 'error': 'worker_exited_without_outcome'}
        result = json.loads(self.outcome.read_text(encoding='utf-8'))
        if not isinstance(result, dict) or set(result) != {'format', 'token', 'status', 'error'} or type(result['format']) is not int or result['format'] != 1 or result['token'] != self.token or result['status'] not in ('ready', 'failed', 'deferred') or (result['error'] is not None and (not isinstance(result['error'], str) or len(result['error']) > 1024)):
            raise ValueError("Invalid native stream worker outcome.")
        if result['status'] != 'ready':
            return result
        if not self.output.is_file() or self.output.is_symlink() or self.output.stat().st_size > 200000:
            raise ValueError("Native stream worker has no bounded receipt.")
        payload = torch.load(self.output, weights_only=True, map_location='cpu')
        packets = validate_receipt(payload, self.items, self.folder, self.token)
        regions = {packets[index].sequence: record for index, record in payload.get('regions', {}).items()}
        statuses = {packets[index].sequence: status for index, status in payload.get('region_status', {}).items()}
        acoustic = {packets[index].sequence: pattern for index, pattern in payload.get('acoustic', {}).items()}
        return {**result, 'packets': packets, 'resources': payload['resources'], 'regions': regions,
                'region_status': statuses, 'acoustic': acoustic}

    def close(self):
        self.cancel()
        if self.process is not None:
            self.process.wait(timeout=5)
        if not self.folder.exists():
            return
        if self.folder.resolve().parent != self.root:
            raise ValueError("Native worker directory escapes its owner.")
        for path in (*self.files, self.request, self.output, self.outcome,
                     self.folder / 'stdout.log', self.folder / 'stderr.log'):
            if path.is_symlink() or not path.resolve().is_relative_to(self.folder):
                raise ValueError("Native worker exchange path changed; preserve it.")
            path.unlink(missing_ok=True)
        self.signals.rmdir()
        self.folder.rmdir()
