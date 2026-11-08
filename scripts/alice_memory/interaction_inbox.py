"""Bounded local human requests and receipts; no neural/model imports."""
import hashlib
import json
import math
import os
import re
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from .native_feedback_language import message_valid
from .written_symbols import symbol

REQUEST = re.compile(r'request-([0-9]{7})-([0-9a-f]{32})\.json\Z')
UUID = re.compile(r'[0-9a-f]{32}\Z')
MAX_FILE = 65536


def identity(value):
    if not isinstance(value, str) or UUID.fullmatch(value) is None:
        raise ValueError('Invalid interaction identity.')
    return value


def integer(value, low=0, high=999999):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Invalid interaction integer.')
    return value


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def atomic(path, value):
    temporary = path.with_name('.pending-' + uuid4().hex)
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            stream.write(canonical(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read(path):
    if path.is_symlink() or not path.is_file() or not 1 <= path.stat().st_size <= MAX_FILE:
        raise ValueError('Missing or oversized interaction file.')
    return json.loads(path.read_text(encoding='utf-8'))


@contextmanager
def lease(path):
    if path.is_symlink():
        raise ValueError('Interaction lock cannot be a symbolic link.')
    with path.open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def payload_valid(action, payload):
    fields = {'name': {'text', 'focus', 'moment', 'frame'},
              'reply': {'reply_to', 'word', 'focus'}, 'ask': {'text'},
              'report': {'text'}, 'meaning': {'text'},
              'relate': {'text', 'moment', 'frame'}, 'correct': {'text', 'reply_to'},
              'recall': {'text', 'about'}, 'feedback': {'text', 'action'}, 'talk': {'text', 'frame', 'about'},
              'recall_feedback': {'about', 'relevance'}}
    if not isinstance(action, str) or action not in fields or not isinstance(payload, dict) or set(payload) != fields[action]:
        raise ValueError('Invalid interaction action/payload.')
    if action in ('name', 'ask', 'report', 'meaning', 'relate', 'correct', 'recall', 'feedback', 'talk'):
        message_valid(payload['text'])
    if action in ('name', 'reply') and payload['focus'] is not None and payload['focus'] not in ('image', 'audio', 'text'):
        raise ValueError('Invalid interaction focus.')
    if action == 'reply':
        identity(payload['reply_to'])
        symbol(payload['word'])
    if action == 'correct':
        identity(payload['reply_to'])
    if action == 'recall':
        identity(payload['about'])
    if action == 'feedback':
        integer(payload['action'], 1)
    if action == 'recall_feedback':
        identity(payload['about'])
        from .native_reference import number
        number(payload['relevance'], -1, 1)
    if action == 'talk':
        if payload['about'] is not None:
            identity(payload['about'])
        frame = payload['frame']
        if not isinstance(frame, dict) or set(frame) != {'stream_id', 'sequence'}:
            raise ValueError('Conversation requires its received text frame.')
        identity(frame['stream_id'])
        integer(frame['sequence'])
    if action in ('name', 'relate'):
        if payload['moment'] is not None:
            integer(payload['moment'])
        frame = payload['frame']
        if frame is not None:
            if payload['moment'] is not None or not isinstance(frame, dict) or set(frame) != {'stream_id', 'sequence'}:
                raise ValueError('Interaction cannot select both frame and moment.')
            identity(frame['stream_id'])
            integer(frame['sequence'])
    return payload


def validate(value):
    if not isinstance(value, dict) or set(value) != {'format', 'stream_id', 'sequence', 'id', 'created_wall', 'action', 'payload'} or type(value['format']) is not int or value['format'] not in (1, 2, 3, 4, 5, 6, 7):
        raise ValueError('Invalid interaction request envelope.')
    if value['format'] == 1 and value['action'] not in ('name', 'reply', 'ask'):
        raise ValueError('Legacy interaction cannot assert a new action.')
    if value['format'] == 2 and value['action'] not in ('name', 'reply', 'ask', 'report', 'meaning'):
        raise ValueError('Version-two interaction cannot assert a contextual action.')
    if value['format'] == 3 and value['action'] == 'recall':
        raise ValueError('Version-three interaction cannot assert a referenced query.')
    if value['format'] < 5 and value['action'] == 'feedback':
        raise ValueError('Legacy interaction cannot assert attention feedback.')
    if value['format'] < 6 and value['action'] == 'talk':
        raise ValueError('Legacy interaction cannot assert dialogue.')
    if value['format'] < 7 and value['action'] == 'recall_feedback':
        raise ValueError('Legacy interaction cannot assert recollection feedback.')
    identity(value['stream_id'])
    identity(value['id'])
    integer(value['sequence'])
    if isinstance(value['created_wall'], bool) or not isinstance(value['created_wall'], (float, int)) or not math.isfinite(value['created_wall']) or value['created_wall'] < 0:
        raise ValueError('Invalid interaction publication time.')
    payload_valid(value['action'], value['payload'])
    if len(canonical(value).encode('utf-8')) > 16384:
        raise ValueError('Interaction request exceeds its budget.')
    return value


class InteractionInbox:
    def __init__(self, root):
        root = Path(root)
        if root.is_symlink():
            raise ValueError('Interaction root cannot be a symbolic link.')
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        with lease(self.root / 'producer.lock'):
            config = self.root / 'interaction.json'
            if not config.exists():
                atomic(config, {'format': 1, 'stream_id': uuid4().hex})
            value = read(config)
            if not isinstance(value, dict) or set(value) != {'format', 'stream_id'} or type(value['format']) is not int or value['format'] != 1:
                raise ValueError('Invalid interaction inbox identity.')
            self.stream_id = identity(value['stream_id'])
            for folder in ('requests', 'receipts'):
                path = self.root / folder
                if path.is_symlink() or path.resolve().parent != self.root:
                    raise ValueError('Interaction directory changed ownership.')
                path.mkdir(exist_ok=True)

    def path(self, folder, filename):
        parent = self.root / folder
        if folder not in ('requests', 'receipts') or parent.is_symlink() or parent.resolve().parent != self.root:
            raise ValueError('Invalid interaction directory.')
        valid = REQUEST.fullmatch(filename) if folder == 'requests' else re.fullmatch(r'[0-9a-f]{32}\.json', filename)
        if valid is None:
            raise ValueError('Invalid interaction filename.')
        path = parent / filename
        if path.is_symlink() or path.resolve().parent != parent.resolve():
            raise ValueError('Interaction file escaped its inbox.')
        return path

    def available(self):
        result = sorted(path.name for path in (self.root / 'requests').iterdir() if REQUEST.fullmatch(path.name))
        if len(result) > 128:
            raise ValueError('Interaction backlog exceeds128 requests.')
        return result

    def request(self, filename):
        value = validate(read(self.path('requests', filename)))
        match = REQUEST.fullmatch(filename)
        if value['stream_id'] != self.stream_id or int(match[1]) != value['sequence'] or match[2] != value['id']:
            raise ValueError('Interaction file changed its request identity.')
        return value

    def publish(self, action, payload):
        payload_valid(action, payload)
        with lease(self.root / 'producer.lock'):
            if len(self.available()) >= 128:
                raise ValueError('Interaction inbox is full.')
            path = self.root / 'counter.json'
            value = read(path) if path.exists() else {'next': 0}
            if not isinstance(value, dict) or set(value) != {'next'}:
                raise ValueError('Invalid interaction producer counter.')
            sequence = integer(value['next'])
            identifier = uuid4().hex
            request = validate({'format': 7, 'stream_id': self.stream_id, 'sequence': sequence, 'id': identifier,
                                'created_wall': time.time(), 'action': action, 'payload': payload})
            atomic(path, {'next': sequence + 1})
            atomic(self.path('requests', f'request-{sequence:07d}-{identifier}.json'), request)
            return identifier

    def receipt(self, identifier):
        path = self.path('receipts', identity(identifier) + '.json')
        if not path.exists():
            return None
        value = read(path)
        expected = {'format', 'stream_id', 'id', 'sequence', 'request_sha256', 'revision', 'result',
                    'commit_file', 'commit_sha256', 'previous_file', 'previous_sha256'}
        if not isinstance(value, dict) or set(value) != expected or type(value['format']) is not int or value['format'] != 1 or value['stream_id'] != self.stream_id or value['id'] != identifier:
            raise ValueError('Invalid interaction receipt identity.')
        integer(value['sequence'])
        integer(value['revision'], 1, 1000000)
        for name in ('request_sha256', 'commit_sha256', 'previous_sha256'):
            if not isinstance(value[name], str) or re.fullmatch(r'[0-9a-f]{64}', value[name]) is None:
                raise ValueError('Invalid interaction receipt digest.')
        for name in ('commit_file', 'previous_file'):
            if not isinstance(value[name], str) or re.fullmatch(r'alice-[0-9a-f]{32}\.pt', value[name]) is None:
                raise ValueError('Invalid interaction commit filename.')
        if not isinstance(value['result'], dict) or value['result'].get('status') not in ('awaiting_reply', 'completed', 'failed'):
            raise ValueError('Invalid interaction receipt result.')
        return value

    def trim_receipts(self):
        receipts = []
        for path in (self.root / 'receipts').iterdir():
            if re.fullmatch(r'[0-9a-f]{32}\.json', path.name) is None:
                continue
            value = self.receipt(path.stem)
            if value['result']['status'] != 'awaiting_reply':
                receipts.append((value['sequence'], path.stem))
        receipts.sort()
        for _, identifier in receipts[:-512]:
            self.path('receipts', identifier + '.json').unlink()

    def confirm(self, record, commit, previous):
        request = record['request']
        value = {'format': 1, 'stream_id': self.stream_id, 'id': request['id'], 'sequence': request['sequence'],
                 'request_sha256': record['request_sha256'], 'revision': record['revision'], 'result': record['result'],
                 'commit_file': commit['file'], 'commit_sha256': commit['sha256'],
                 'previous_file': previous['file'], 'previous_sha256': previous['sha256']}
        existing = self.receipt(request['id'])
        if existing is not None and (existing['request_sha256'] != value['request_sha256'] or existing['sequence'] != value['sequence'] or existing['revision'] > value['revision'] or (existing['revision'] == value['revision'] and existing['result'] != value['result'])):
            raise ValueError('Interaction receipt conflicts with its durable request.')
        atomic(self.path('receipts', request['id'] + '.json'), value)
        filename = f"request-{request['sequence']:07d}-{request['id']}.json"
        path = self.path('requests', filename)
        if path.exists():
            if self.request(filename) != request:
                raise ValueError('Interaction request changed after commitment.')
            path.unlink()
        self.trim_receipts()
