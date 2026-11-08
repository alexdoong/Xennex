"""Owned local frame inbox: producers copy signals, consumers commit then release.

Original files are never changed. This is a local transport, not a camera or
microphone service, and a name is explicit external teaching, not model output.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from pathlib import Path
from uuid import uuid4

from .concept_memory import scalar
from .native_encoder import file_digest
from .native_regions import validate_boxes
from .runtime_store import RuntimeLease, atomic_json
from .written_symbols import symbol

FRAME = re.compile(r'frame-([0-9]{7})-([0-9a-f]{32})\Z')
MAX_BYTES = 8_000_000
MANIFEST_FIELDS = {'format', 'stream_id', 'sequence', 'captured_wall', 'name', 'origin', 'files'}


def manifest_fields(value):
    if not isinstance(value, dict) or type(value.get('format')) is not int:
        return False
    return ((value['format'] == 1 and set(value) == MANIFEST_FIELDS)
            or (value['format'] == 2 and set(value) == MANIFEST_FIELDS | {'image_regions'})
            or (value['format'] == 3 and set(value) == MANIFEST_FIELDS | {'word_audio'}))


def validate_frame_details(value, modalities):
    if 'image_regions' in value:
        if 'image' not in modalities:
            raise ValueError('Visual regions require an image in the same frame.')
        validate_boxes(value['image_regions'])
    if 'word_audio' in value and (value['word_audio'] is not True or set(modalities) != {'audio'}
                                  or (value['name'] is not None and value['origin'] != 'person')):
        raise ValueError('An acoustic word frame needs only audio and an external teacher for a lesson.')


def read_json(path, limit=16384):
    if path.is_symlink() or path.stat().st_size > limit:
        raise ValueError("Invalid native inbox metadata path/size.")
    return json.loads(path.read_text(encoding='utf-8'))


class NativeInbox:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        if not (self.root / 'stream.json').exists() and any(path.name not in ('producer', 'lease.lock') for path in self.root.iterdir()):
            raise ValueError("Native inbox requires an empty dedicated directory.")
        with RuntimeLease(self.root / 'producer'):
            marker = self.root / 'stream.json'
            if not marker.exists():
                if any(path.name not in ('producer', 'lease.lock') for path in self.root.iterdir()):
                    raise ValueError("Native inbox requires an empty dedicated directory.")
                atomic_json(marker, {'format': 1, 'kind': 'alice-native-inbox', 'stream_id': uuid4().hex})
            value = read_json(marker, 1024)
            if not isinstance(value, dict) or set(value) != {'format', 'kind', 'stream_id'} or type(value['format']) is not int or value['format'] != 1 or value['kind'] != 'alice-native-inbox' or not isinstance(value['stream_id'], str) or re.fullmatch(r'[0-9a-f]{32}', value['stream_id']) is None:
                raise ValueError("Invalid native inbox ownership marker.")
            self.stream_id = value['stream_id']
            for name in ('frames', 'receipts'):
                path = self.root / name
                if path.is_symlink() or path.resolve().parent != self.root:
                    raise ValueError("Native inbox subdirectory escapes its owner.")
                path.mkdir(exist_ok=True)

    def frame_path(self, name):
        if not isinstance(name, str) or FRAME.fullmatch(name) is None:
            raise ValueError("Invalid native frame folder.")
        frames = self.root / 'frames'
        if frames.is_symlink() or frames.resolve().parent != self.root:
            raise ValueError("Native frames directory changed its owner.")
        path = frames / name
        if path.is_symlink() or path.resolve().parent != (self.root / 'frames').resolve():
            raise ValueError("Native frame escapes its inbox.")
        return path

    def read(self, folder):
        path = self.frame_path(folder)
        value = read_json(path / 'frame.json')
        match = FRAME.fullmatch(folder)
        if not manifest_fields(value) or value['stream_id'] != self.stream_id or type(value['sequence']) is not int or value['sequence'] != int(match[1]):
            raise ValueError("Native frame source identity changed.")
        scalar(value['captured_wall'], 0, 1e12)
        if value['name'] is not None and symbol(value['name']) != value['name']:
            raise ValueError("Native frame teaching name must be canonical.")
        if value['origin'] not in ('person', 'environment') or not isinstance(value['files'], list) or not 1 <= len(value['files']) <= 3:
            raise ValueError("Invalid native frame origin/modalities.")
        modalities = []
        for item in value['files']:
            if not isinstance(item, dict) or set(item) != {'modality', 'file', 'size', 'sha256'} or item['modality'] not in ('image', 'audio', 'text'):
                raise ValueError("Invalid native frame signal fields.")
            filename = item['file']
            if not isinstance(filename, str) or re.fullmatch(r'[0-9a-f]{32}\.(png|wav|txt)', filename) is None:
                raise ValueError("Invalid native signal filename.")
            if type(item['size']) is not int or not 1 <= item['size'] <= MAX_BYTES or not isinstance(item['sha256'], str) or re.fullmatch(r'[0-9a-f]{64}', item['sha256']) is None:
                raise ValueError("Invalid native signal size/digest.")
            file = path / filename
            if file.is_symlink() or file.resolve().parent != path.resolve() or file.stat().st_size != item['size']:
                raise ValueError("Native signal source is missing or changed.")
            modalities.append(item['modality'])
        if len(set(modalities)) != len(modalities):
            raise ValueError("Native frame repeats a modality.")
        validate_frame_details(value, modalities)
        return value

    def available(self, after):
        result = []
        for path in (self.root / 'frames').iterdir():
            match = FRAME.fullmatch(path.name)
            if match is None or int(match[1]) <= after:
                continue
            result.append(path.name)
            if len(result) > 128:
                raise ValueError("Native inbox backlog exceeds 128 frames.")
        return sorted(result)

    def publish(self, files, name=None, origin='person', captured_wall=None, *, image_regions=None, mirage_result=None,
                word_audio=False):
        if not isinstance(files, dict) or not 1 <= len(files) <= 3 or any(key not in ('image', 'audio', 'text') for key in files) or origin not in ('person', 'environment'):
            raise ValueError("Native publication requires one to three local modalities.")
        name = None if name is None else symbol(name)
        captured_wall = time.time() if captured_wall is None else scalar(captured_wall, 0, time.time())
        visual = {} if image_regions is None else {'image_regions': image_regions}
        if type(word_audio) is not bool or (word_audio and (visual or mirage_result is not None)):
            raise ValueError('An acoustic word frame cannot request visual processing.')
        acoustic = {'word_audio': True} if word_audio else {}
        validate_frame_details({**visual, **acoustic, 'name': name, 'origin': origin}, files)
        if mirage_result is not None and (visual or 'image' not in files):
            raise ValueError('Mirage regions require an image and no manually selected boxes.')
        with RuntimeLease(self.root / 'producer'):
            if len(list((self.root / 'frames').iterdir())) >= 128:
                raise ValueError("Native inbox is full; await durable processing.")
            counter = self.root / 'counter.json'
            value = {'next_sequence': 0} if not counter.exists() else read_json(counter, 1024)
            if not isinstance(value, dict) or set(value) != {'next_sequence'} or type(value['next_sequence']) is not int or not 0 <= value['next_sequence'] < 1000000:
                raise ValueError("Invalid native producer counter.")
            sequence = value['next_sequence']
            atomic_json(counter, {'next_sequence': sequence + 1})
            nonce = uuid4().hex
            temporary = self.root / 'frames' / ('.pending-' + nonce)
            final = self.frame_path('frame-' + format(sequence, '07d') + '-' + nonce)
            temporary.mkdir()
            records = []
            owned = [temporary / 'frame.json']
            try:
                for modality, source in files.items():
                    source = Path(source)
                    if not source.is_file() or not 1 <= source.stat().st_size <= MAX_BYTES:
                        raise ValueError("Native publication requires bounded local files.")
                    target = temporary / (uuid4().hex + {'image': '.png', 'audio': '.wav', 'text': '.txt'}[modality])
                    owned.append(target)
                    shutil.copyfile(source, target)
                    size = target.stat().st_size
                    if not 1 <= size <= MAX_BYTES:
                        raise ValueError("Native signal grew beyond its copy budget.")
                    digest = file_digest(target)
                    records.append({'modality': modality, 'file': target.name, 'size': size, 'sha256': digest})
                    if modality == 'image' and mirage_result is not None:
                        from .mirage_regions import object_boxes
                        boxes = object_boxes(mirage_result, target, digest)
                        if boxes:
                            visual['image_regions'] = boxes
                atomic_json(owned[0], {'format': 3 if acoustic else (2 if visual else 1), 'stream_id': self.stream_id,
                            'sequence': sequence, 'captured_wall': captured_wall, 'name': name, 'origin': origin,
                            'files': records, **visual, **acoustic})
                temporary.rename(final)
            except (OSError, ValueError):
                for path in owned:
                    path.unlink(missing_ok=True)
                temporary.rmdir()
                raise
            return final.name

    def acknowledge(self, job, commit):
        # Called only with a generation that contains this terminal job and its
        # neural update. Repeating after a crash is safe even if the copy is gone.
        receipts = self.root / 'receipts'
        if receipts.is_symlink() or receipts.resolve().parent != self.root:
            raise ValueError("Native receipts directory changed its owner.")
        receipt = receipts / ('frame-' + format(job['source_sequence'], '07d') + '.json')
        value = {'format': 1, 'stream_id': self.stream_id, 'source_sequence': job['source_sequence'],
                 'frame': job['frame'], 'status': job['status'], 'result': job['result'], 'error': job['error'],
                 'commit_file': commit['file'], 'commit_sha256': commit['sha256'],
                 'previous_file': commit['previous_file'], 'previous_sha256': commit['previous_sha256']}
        if receipt.exists():
            old = read_json(receipt)
            if not isinstance(old, dict) or any(old.get(name) != value[name] for name in ('stream_id', 'source_sequence', 'frame', 'status', 'result', 'error')):
                raise ValueError("Native receipt conflicts with its durable job.")
        else:
            atomic_json(receipt, value)
        path = self.frame_path(job['frame'])
        if not path.exists():
            return
        manifest = job['manifest']
        if (path / 'frame.json').exists() and read_json(path / 'frame.json') != manifest:
            raise ValueError("Native frame changed after commitment; preserve its files.")
        expected = {'frame.json', *(item['file'] for item in manifest['files'])}
        if not {item.name for item in path.iterdir()}.issubset(expected):
            raise ValueError("Native frame contains an unrelated file; preserve it.")
        for item in manifest['files']:
            target = path / item['file']
            if target.exists() and (target.is_symlink() or target.stat().st_size != item['size'] or file_digest(target) != item['sha256']):
                raise ValueError("Native frame copy changed; preserve it.")
        for filename in expected:
            (path / filename).unlink(missing_ok=True)
        path.rmdir()
