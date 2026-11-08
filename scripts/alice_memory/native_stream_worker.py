"""Finite encoder batch with explicit admission outcome for the stream owner."""
import argparse
import json
from pathlib import Path

from .language import AdmissionDeferred
from .native_encoder_worker import run
from .runtime_store import atomic_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--outcome', type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding='utf-8'))
    result = {'format': 1, 'token': request['token'], 'status': 'failed', 'error': None}
    try:
        run(args.request, args.output)
        result['status'] = 'ready'
    except AdmissionDeferred as error:
        result.update(status='deferred', error=str(error)[:1024])
    except (OSError, RuntimeError, ValueError) as error:
        result['error'] = type(error).__name__ + ': ' + str(error)[:1024]
    atomic_json(args.outcome, result)


if __name__ == '__main__':
    main()
