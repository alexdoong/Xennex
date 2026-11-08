"""Reclaim registered native weight pages only after proving retained references.

The runtime lease and single writer serialize collection with persistence. An
ownership journal records write intents before a page is created. Legacy pages
are registered only when verified and used; unknown files remain untouched.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import torch

from .native_fast_weights import restore as restore_weights
from .native_page_store import MAX_PAGES, folder, page_path, read_page, validate_record, validate_references, write_bytes

MAX_JOURNAL = 1_000_000


def journal_path(directory):
    path = directory / 'owned.json'
    if path.is_symlink() or path.resolve().parent != directory.resolve():
        raise ValueError('Native page journal escapes its archive.')
    return path


def read_journal(directory):
    path = journal_path(directory)
    if not path.exists():
        return {}
    if path.stat().st_size > MAX_JOURNAL:
        raise ValueError('Native page ownership journal exceeds its limit.')
    with path.open('rb') as stream:
        raw = stream.read(MAX_JOURNAL + 1)
    if len(raw) > MAX_JOURNAL:
        raise ValueError('Native page ownership journal grew beyond its limit.')
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != {'format', 'owned'} or type(value['format']) is not int or value['format'] != 1 or not isinstance(value['owned'], dict) or len(value['owned']) > MAX_PAGES * 3:
        raise ValueError('Invalid native page ownership journal.')
    for sha, size in value['owned'].items():
        validate_record({'sha256': sha, 'size': size})
    return value['owned']


def save_journal(directory, owned):
    if len(owned) > MAX_PAGES * 3:
        raise ValueError('Native page ownership journal is full.')
    raw = json.dumps({'format': 1, 'owned': owned}, sort_keys=True).encode('utf-8')
    if len(raw) > MAX_JOURNAL:
        raise ValueError('Native page ownership journal exceeds its limit.')
    write_bytes(journal_path(directory), raw)


def register(directory, records):
    validate_references(records)
    owned = read_journal(directory)
    before = dict(owned)
    for record in records:
        if record['sha256'] in owned and owned[record['sha256']] != record['size']:
            raise ValueError('Native page ownership size changed.')
        owned[record['sha256']] = record['size']
    if owned != before:
        save_journal(directory, owned)


def checkpoint_references(path, record):
    if path.stat().st_size != record['size'] or not 1 <= record['size'] <= 80_000_000:
        raise ValueError('Retained runtime checkpoint size changed.')
    hashed = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            hashed.update(chunk)
    if hashed.hexdigest() != record['sha256']:
        raise ValueError('Retained runtime checkpoint checksum changed.')
    payload = torch.load(path, weights_only=True, map_location='cpu')
    if not isinstance(payload, dict):
        raise ValueError('Unknown retained runtime checkpoint.')
    native = payload.get('native')
    moments = native.get('moments') if isinstance(native, dict) else None
    if payload.get('format') not in (46, 48, 50, 52, 54, 56, 58):
        if isinstance(moments, dict) and 'pages' in moments:
            raise ValueError('Unknown retained external native checkpoint.')
        return []
    if not isinstance(moments, dict) or type(moments.get('format')) is not int or moments['format'] not in (2, 4, 6, 8, 10) or 'page_source' in moments or 'archive' in moments:
        raise ValueError('Invalid retained native page checkpoint.')
    records = moments.get('pages')
    validate_references(records)
    if not isinstance(moments.get('traces'), list) or len(moments['traces']) != len(records):
        raise ValueError('Retained native references lost their moments.')
    return records


def collect(root, retained, additional=()):
    result = {'status': 'noop', 'removed_pages': 0, 'removed_bytes': 0, 'missing_entries': 0, 'errors': []}
    if not (Path(root) / 'native-pages').exists():
        return result
    try:
        directory = folder(root)
        owned = read_journal(directory)
        additional = list(additional)
        validate_references(additional)
        keep = {record['sha256'] for record in additional}
        # No deletion means no need to read large checkpoints in routine saves.
        if not (set(owned) - keep):
            return result
        expected = {path.name for path, _ in retained}
        if any(path.name not in expected for path in Path(root).glob('*.pt')):
            raise ValueError('Extra runtime checkpoint prevents safe native page collection.')
        references = []
        for path, record in retained:
            references.extend(checkpoint_references(path, record))
        for record in references:
            raw = read_page(directory, record)
            restore_weights(torch.load(io.BytesIO(raw), weights_only=True, map_location='cpu'))
            keep.add(record['sha256'])
    except Exception as error:
        # Cleanup is optional; unreadable dependencies must suspend deletion.
        return {**result, 'status': 'skipped', 'errors': [type(error).__name__ + ': ' + str(error)[:512]]}
    changed = False
    for sha in sorted(set(owned) - keep):
        record = {'sha256': sha, 'size': owned[sha]}
        try:
            path = page_path(directory, record)
            if not path.exists():
                owned.pop(sha)
                result['missing_entries'] += 1
                changed = True
                continue
            raw = read_page(directory, record)
            restore_weights(torch.load(io.BytesIO(raw), weights_only=True, map_location='cpu'))
            # page_path checks the resolved target stays inside the owned archive.
            path.unlink()
            owned.pop(sha)
            result['removed_pages'] += 1
            result['removed_bytes'] += len(raw)
            changed = True
        except Exception as error:
            result['errors'].append(sha + ': ' + type(error).__name__ + ': ' + str(error)[:256])
    if changed:
        try:
            save_journal(directory, owned)
        except Exception as error:
            # A crash/failure leaves stale ownership entries, which are retryable.
            result['errors'].append('journal: ' + type(error).__name__ + ': ' + str(error)[:256])
    result['status'] = 'partial' if result['errors'] else ('collected' if changed else 'noop')
    return result
