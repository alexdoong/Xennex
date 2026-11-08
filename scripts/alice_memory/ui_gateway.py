"""Finite JSON bridge for the Xennex panel; the cognitive owner stays separate."""
import argparse
import json
import os
from uuid import uuid4
from pathlib import Path

from .interaction_inbox import InteractionInbox, atomic, identity


def directory(root, name):
    if Path(root).is_symlink():
        raise ValueError('Alice session cannot be a symbolic link.')
    root = Path(root).resolve()
    path = root / name
    if path.is_symlink() or path.resolve().parent != root:
        raise ValueError('Alice panel path changed its owner.')
    return path


def prepare(root, checkpoint):
    root = Path(root)
    if root.is_symlink():
        raise ValueError('Alice session cannot be a symbolic link.')
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    from .runtime_store import RuntimeStore
    with RuntimeStore(directory(root, 'runtime')) as store:
        if store.manifest is not None:
            return {'resumed': True}
        return prepare_seed(root, checkpoint)


def prepare_seed(root, checkpoint):
    seed = directory(root, 'seed.pt')
    if seed.exists():
        return {'resumed': False}
    if any(root.glob('prepare-*')):
        raise ValueError('An interrupted preparation was preserved. Inspect the session folder before trying again.')
    for name in ('human', 'sensory'):
        folder = directory(root, name)
        if folder.exists():
            raise ValueError('Incomplete session preparation; existing inboxes were preserved. Select another session directory.')
    from .continuous_experiment import load_scheduler
    from .conceptual_mind import save
    from .persistent_runtime import close_agent
    core, mind, _ = load_scheduler(Path(checkpoint))
    staging = root / ('prepare-' + uuid4().hex)
    try:
        if not hasattr(core, 'interactions') or not hasattr(core, 'native_stream'):
            raise ValueError('Selected state does not support Alice interactions and perceptual memory.')
        if core.native_stream.jobs:
            raise ValueError('Starting copy cannot relocate pending sensory input files.')
        staging.mkdir()
        human = directory(staging, 'human')
        human.mkdir(exist_ok=True)
        if core.interactions.stream_id is not None:
            atomic(human / 'interaction.json', {'format': 1, 'stream_id': identity(core.interactions.stream_id)})
        atomic(human / 'counter.json', {'next': core.interactions.last_sequence + 1})
        InteractionInbox(human)
        from .native_inbox import NativeInbox
        sensory = directory(staging, 'sensory')
        sensory.mkdir(exist_ok=True)
        if core.native_stream.stream_id is not None:
            atomic(sensory / 'stream.json', {'format': 1, 'kind': 'alice-native-inbox',
                                           'stream_id': identity(core.native_stream.stream_id)})
        atomic(sensory / 'counter.json', {'next_sequence': core.native_stream.last_source_sequence + 1})
        # A previously unbound NativeInbox requires an empty directory before
        # counter creation, so install the explicit identity first.
        if not (sensory / 'stream.json').exists():
            atomic(sensory / 'stream.json', {'format': 1, 'kind': 'alice-native-inbox', 'stream_id': uuid4().hex})
        NativeInbox(sensory)
        save(staging / 'seed.pt', core)
        for name in ('human', 'sensory', 'seed.pt'):
            os.rename(staging / name, directory(root, name))
        staging.rmdir()
        return {'resumed': False}
    finally:
        close_agent(core, mind)


def publish_selected(root, files, modality, *, word_audio=False, name=None):
    from .native_inbox import NativeInbox
    if not directory(root, 'seed.pt').exists() and not (directory(root, 'runtime') / 'current.json').exists():
        raise ValueError('Prepare the Alice session before publishing input.')
    if any(not isinstance(value, str) or not value or '\0' in value for value in files.values()):
        raise ValueError('Invalid explicitly selected sensory file.')
    sources = {name: Path(value) for name, value in files.items()}
    inbox = NativeInbox(directory(root, 'sensory'))
    frame = inbox.publish(sources, name, word_audio=word_audio)
    return {'stream_id': inbox.stream_id, 'sequence': inbox.read(frame)['sequence'],
            'label': ' + '.join(path.name for path in sources.values()), 'modality': modality}


def execute(root, request):
    if not isinstance(request, dict) or 'action' not in request:
        raise ValueError('Invalid Alice panel request.')
    action = request['action']
    if action == 'prepare' and set(request) == {'action', 'checkpoint'}:
        return prepare(root, request['checkpoint'])
    if action == 'send' and set(request) == {'action', 'kind', 'payload'}:
        if not directory(root, 'seed.pt').exists() and not (directory(root, 'runtime') / 'current.json').exists():
            raise ValueError('Prepare the Alice session before publishing input.')
        inbox = InteractionInbox(directory(root, 'human'))
        return {'id': inbox.publish(request['kind'], request['payload'])}
    if action == 'text' and set(request) == {'action', 'text'}:
        from .native_feedback_language import message_valid
        from .native_inbox import NativeInbox
        message_valid(request['text'])
        if not directory(root, 'seed.pt').exists() and not (directory(root, 'runtime') / 'current.json').exists():
            raise ValueError('Prepare the Alice session before publishing text.')
        inbox = NativeInbox(directory(root, 'sensory'))
        path = directory(root, 'typed-' + uuid4().hex + '.txt')
        try:
            path.write_bytes(request['text'].encode('utf-8'))
            frame = inbox.publish({'text': path}, origin='person')
            return {'stream_id': inbox.stream_id, 'sequence': inbox.read(frame)['sequence'],
                    'label': 'Mensagem digitada', 'modality': 'text'}
        finally:
            path.unlink(missing_ok=True)
    if action == 'perceive' and set(request) == {'action', 'modality', 'path'}:
        if request['modality'] not in ('image', 'audio', 'text'):
            raise ValueError('Invalid explicitly selected modality.')
        return publish_selected(root, {request['modality']: request['path']}, request['modality'])
    if action == 'perceive_pair' and set(request) == {'action', 'image', 'audio'}:
        return publish_selected(root, {'image': request['image'], 'audio': request['audio']}, 'image_audio')
    if action == 'word_audio' and set(request) == {'action', 'path', 'word'}:
        word = request['word']
        if word is not None and not isinstance(word, str):
            raise ValueError('A pronunciation lesson requires a written word.')
        return publish_selected(root, {'audio': request['path']}, 'audio', word_audio=True, name=word)
    raise ValueError('Unknown Alice panel action or fields.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    import sys
    try:
        raw = sys.stdin.buffer.read(32769)
        if not 1 <= len(raw) <= 32768:
            raise ValueError('Alice panel request exceeds its byte budget.')
        request = json.loads(raw.decode('utf-8'))
        result = {'ok': True, 'value': execute(args.root, request)}
    except (OSError, ValueError, RuntimeError) as error:
        result = {'ok': False, 'error': str(error)[:2048]}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
