"""Publish an explicit local sensory frame to Alice's running file inbox."""
import argparse
from pathlib import Path

from .native_inbox import NativeInbox, read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inbox', type=Path, required=True)
    parser.add_argument('--image', type=Path)
    parser.add_argument('--audio', type=Path)
    parser.add_argument('--text', type=Path)
    parser.add_argument('--name')
    parser.add_argument('--origin', choices=('person', 'environment'), default='person')
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--region', action='append', type=int, nargs=4, metavar=('LEFT', 'TOP', 'RIGHT', 'BOTTOM'),
                           help='Image region in source pixels. Repeat up to four times.')
    selection.add_argument('--mirage-result', type=Path, help='Local JSON with image_sha256 and result fields.')
    selection.add_argument('--word-audio', action='store_true',
                           help='Experimental isolated word clip. Add --name to teach its written form.')
    args = parser.parse_args()
    files = {name: getattr(args, name) for name in ('image', 'audio', 'text') if getattr(args, name) is not None}
    mirage = None if args.mirage_result is None else read_json(args.mirage_result, 262144)
    if args.mirage_result is not None and not isinstance(mirage, dict):
        parser.error('Mirage JSON requires an object envelope.')
    print(NativeInbox(args.inbox).publish(files, args.name, args.origin, image_regions=args.region,
                                        mirage_result=mirage, word_audio=args.word_audio))


if __name__ == '__main__':
    main()
