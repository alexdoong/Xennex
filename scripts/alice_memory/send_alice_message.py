"""Send an explicit teaching/reply/memory question to a running local owner."""
import argparse
import json
from pathlib import Path

from .interaction_inbox import InteractionInbox


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inbox', type=Path, required=True)
    actions = parser.add_subparsers(dest='action', required=True)
    teach = actions.add_parser('name')
    teach.add_argument('text')
    teach.add_argument('--focus', choices=('image', 'audio', 'text'))
    teach.add_argument('--moment', type=int)
    teach.add_argument('--frame-stream')
    teach.add_argument('--frame-sequence', type=int)
    relate = actions.add_parser('relate')
    relate.add_argument('text')
    relate.add_argument('--moment', type=int)
    relate.add_argument('--frame-stream')
    relate.add_argument('--frame-sequence', type=int)
    correction = actions.add_parser('correct')
    correction.add_argument('reply_to')
    correction.add_argument('text')
    recall = actions.add_parser('recall')
    recall.add_argument('about')
    recall.add_argument('text')
    reply = actions.add_parser('reply')
    reply.add_argument('reply_to')
    reply.add_argument('word')
    reply.add_argument('--focus', choices=('image', 'audio', 'text'))
    for action in ('ask', 'report', 'meaning'):
        text = actions.add_parser(action)
        text.add_argument('text')
    response = actions.add_parser('response')
    response.add_argument('request_id')
    args = parser.parse_args()
    inbox = InteractionInbox(args.inbox)
    if args.action == 'response':
        print(json.dumps(inbox.receipt(args.request_id), ensure_ascii=False))
        return
    if args.action in ('name', 'relate'):
        if (args.frame_stream is None) != (args.frame_sequence is None):
            parser.error('Frame stream and sequence must be selected together.')
        frame = None if args.frame_stream is None else {'stream_id': args.frame_stream, 'sequence': args.frame_sequence}
        payload = {'text': args.text, 'moment': args.moment, 'frame': frame}
        if args.action == 'name':
            payload['focus'] = args.focus
    elif args.action == 'reply':
        payload = {'reply_to': args.reply_to, 'word': args.word, 'focus': args.focus}
    elif args.action == 'correct':
        payload = {'reply_to': args.reply_to, 'text': args.text}
    elif args.action == 'recall':
        payload = {'about': args.about, 'text': args.text}
    else:
        payload = {'text': args.text}
    print(inbox.publish(args.action, payload))


if __name__ == '__main__':
    main()
