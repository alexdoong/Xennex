"""Explicit pinned public model download; no inference, personal data or login."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from pathlib import Path

from .native_encoder import verify_model
from .native_sensor import REVISION

BASE = 'https://huggingface.co/google/embeddinggemma-2/'


def fetch(folder):
    folder = folder.resolve()
    if folder.exists() and any(folder.iterdir()):
        return {'verified_existing_bytes': verify_model(folder), 'revision': REVISION}
    folder.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen('https://huggingface.co/api/models/google/embeddinggemma-2/revision/' + REVISION + '?blobs=true', timeout=30) as response:
        metadata = json.loads(response.read(2000000))
    if metadata.get('sha') != REVISION or metadata.get('gated') is not False:
        raise ValueError("Model metadata does not match the public pinned revision.")
    records = []
    started = time.monotonic()
    for item in metadata['siblings']:
        name = item['rfilename']
        if not name.endswith(('.json', '.safetensors', '.model', '.jinja')) and name != 'README.md':
            continue
        path = folder / name
        size = item['size']
        if not path.resolve().is_relative_to(folder) or type(size) is not int or not 1 <= size < 1600000000:
            raise ValueError("Invalid upstream model path/size.")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + '.download')
        digest, length = hashlib.sha256(), 0
        with urllib.request.urlopen(BASE + 'resolve/' + REVISION + '/' + name, timeout=60) as response, temporary.open('xb') as output:
            while chunk := response.read(1048576):
                length += len(chunk)
                if length > size:
                    raise ValueError("Model download exceeded its declared size.")
                digest.update(chunk)
                output.write(chunk)
        if length != size:
            raise ValueError("Model download is truncated.")
        if item.get('lfs'):
            valid = digest.hexdigest() == item['lfs']['sha256']
        else:
            valid = hashlib.sha1(b'blob ' + str(size).encode() + b'\0' + temporary.read_bytes()).hexdigest() == item['blobId']
        if not valid:
            raise ValueError("Model download checksum mismatch.")
        temporary.replace(path)
        records.append({'file': name, 'size': size, 'sha256': digest.hexdigest()})
        print(json.dumps(records[-1]), flush=True)
    result = {'revision': REVISION, 'files': records, 'total_bytes': sum(item['size'] for item in records),
              'wall_seconds': time.monotonic() - started}
    (folder / 'download-manifest.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    verify_model(folder)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(fetch(args.folder)))


if __name__ == '__main__':
    main()
