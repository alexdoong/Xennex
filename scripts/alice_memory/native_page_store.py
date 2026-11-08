"""Immutable native weight pages; commit references only after durable writes.

Runtime checkpoints depend on their sibling native-pages directory. Portable
snapshots still embed the SQLite archive. Neither mode serializes live objects.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

MAX_PAGES = 2048
MAX_PAGE = 50000
MAX_BYTES = 128_000_000
OWNER = {'format': 1, 'kind': 'alice-native-weight-pages'}


def folder(root, create=False):
    root = Path(root).resolve()
    path = root / 'native-pages'
    if path.is_symlink() or path.resolve().parent != root:
        raise ValueError('Native page directory escapes its runtime.')
    marker = path / 'owner.json'
    if create and not marker.exists():
        path.mkdir(exist_ok=True)
        if any(path.iterdir()):
            raise ValueError('Refusing to claim an unrelated native page directory.')
        write_bytes(marker, json.dumps(OWNER).encode('utf-8'))
    if marker.is_symlink() or marker.resolve().parent != path.resolve() or not marker.is_file() or marker.stat().st_size > 1024:
        raise ValueError('Missing or invalid native page ownership marker.')
    owner = json.loads(marker.read_text(encoding='utf-8'))
    if not isinstance(owner, dict) or owner != OWNER or type(owner.get('format')) is not int:
        raise ValueError('Invalid native page ownership marker.')
    return path


def validate_record(record):
    if not isinstance(record, dict) or set(record) != {'sha256', 'size'} or not isinstance(record['sha256'], str) or re.fullmatch(r'[0-9a-f]{64}', record['sha256']) is None or type(record['size']) is not int or not 1 <= record['size'] <= MAX_PAGE:
        raise ValueError('Invalid native page reference.')


def page_path(directory, record):
    validate_record(record)
    path = directory / (record['sha256'] + '.page')
    if path.is_symlink() or path.resolve().parent != directory.resolve():
        raise ValueError('Native weight page escapes its archive.')
    return path


def validate_references(records):
    if not isinstance(records, list) or len(records) > MAX_PAGES:
        raise ValueError('Invalid native page reference count.')
    total = 0
    for record in records:
        # Field validation is independent of whether the page already exists.
        validate_record(record)
        total += record['size']
    if total > MAX_BYTES:
        raise ValueError('Native referenced pages exceed the archive budget.')


def read_page(directory, record):
    path = page_path(directory, record)
    if path.stat().st_size != record['size']:
        raise ValueError('Native page size changed.')
    with path.open('rb') as stream:
        raw = stream.read(record['size'] + 1)
    if len(raw) != record['size'] or hashlib.sha256(raw).hexdigest() != record['sha256']:
        raise ValueError('Native page checksum changed.')
    return raw


def write_bytes(path, raw):
    temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class PendingNativeCheckpoint:
    payload: dict
    writes: tuple
    root: str

    def __getitem__(self, key):
        return self.payload[key]


class NativePageSource:
    """Reader capability created by read_checkpoint, never accepted from a file."""
    def __init__(self, root):
        self.directory = folder(root)

    def rows(self, records):
        validate_references(records)
        folder(self.directory.parent)
        for index, record in enumerate(records):
            yield index, read_page(self.directory, record), record['sha256']


def index_pages(root):
    directory = folder(root, create=True)
    index = {}
    for path in directory.glob('*.page'):
        if len(index) >= MAX_PAGES * 3:
            raise ValueError('Native page file index exceeds its bounded capacity.')
        sha = path.stem
        if re.fullmatch(r'[0-9a-f]{64}', sha) is None:
            continue
        record = {'sha256': sha, 'size': path.stat().st_size}
        page_path(directory, record)
        index[sha] = record['size']
    return index


def capture_pages(memory, root, persisted):
    directory = folder(root, create=True)
    records, writes = [], []
    detached = set()
    rows = memory.connection.execute('SELECT id,digest,length(bank) FROM moments ORDER BY id')
    for index, sha, size in rows:
        if len(records) >= len(memory.traces) or index != memory.traces[len(records)]['id']:
            raise ValueError('Native page capture lost its moment order.')
        record = {'sha256': sha, 'size': size}
        records.append(record)
        if persisted.get(sha) != size and sha not in detached:
            raw = memory.connection.execute('SELECT bank FROM moments WHERE id=?', (index,)).fetchone()[0]
            if len(raw) != size or hashlib.sha256(raw).hexdigest() != sha:
                raise ValueError('Native live page is corrupt.')
            writes.append((dict(record), raw))
            detached.add(sha)
    validate_references(records)
    if len(records) != len(memory.traces):
        raise ValueError('Native page capture lost a moment.')
    return memory.snapshot(pages=records), tuple(writes)


def persist(capture, root):
    if capture.root != str(Path(root).resolve()):
        raise ValueError('Native checkpoint belongs to a different runtime.')
    records = capture.payload['native']['moments']['pages']
    validate_references(records)
    directory = folder(root, create=True)
    total = sum(path.stat().st_size for path in directory.glob('*.page'))
    from .native_page_gc import register
    intents = []
    for record, raw in capture.writes:
        path = page_path(directory, record)
        if record not in records or not isinstance(raw, bytes) or len(raw) != record['size'] or hashlib.sha256(raw).hexdigest() != record['sha256']:
            raise ValueError('Invalid detached native page write.')
        if not path.exists():
            intents.append(record)
    register(directory, intents)
    for record, raw in capture.writes:
        path = page_path(directory, record)
        if record not in records or not isinstance(raw, bytes) or len(raw) != record['size'] or hashlib.sha256(raw).hexdigest() != record['sha256']:
            raise ValueError('Invalid detached native page write.')
        if path.exists():
            read_page(directory, record)
            continue
        if total + len(raw) > MAX_BYTES:
            raise ValueError('Native page directory exceeds its disk budget.')
        write_bytes(path, raw)
        total += len(raw)
    # All references must be intact before the generation pointer can commit.
    # Existing immutable pages are hashed one at a time, never copied together.
    for record in records:
        read_page(directory, record)
    register(directory, records)
    return capture.payload


def resolve(payload, checkpoint):
    native = payload.get('native')
    moments = native.get('moments') if isinstance(native, dict) else None
    if not isinstance(moments, dict) or moments.get('format') not in (2, 4, 6, 8, 10) or 'page_source' in moments:
        raise ValueError('Invalid external native checkpoint.')
    validate_references(moments.get('pages'))
    source = NativePageSource(Path(checkpoint).resolve().parent)
    return {**payload, 'native': {**native, 'moments': {**moments, 'page_source': source}}}
