"""Finite live report/correction trial with installed perception and language."""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import torch

from .conceptual_mind import save
from .continuous_experiment import load_scheduler
from .interaction_inbox import InteractionInbox
from .native_inbox import NativeInbox
from .native_stream import NativeStream
from .persistent_runtime import close_agent
from .reactivation_index import source_digest
from .runtime_store import atomic_json, digest


def run(checkpoint, output, endpoint, model):
    root = Path.cwd()
    output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(1)
    model_folder = root / 'bin/AliceMemory/EmbeddingGemma2/914f7f89142e33e77833254d9c9b90c3cef7303b'
    interpreter = root / 'bin/AliceMemory/perception-venv/Scripts/python.exe'
    files = {kind: root / 'bin/AliceMemory/native-stream-source-v1' / filename
             for kind, filename in (('image', 'bridge.png'), ('audio', 'speech.wav'))}
    expected = {'image': 'ff6b23c20b29e03631d5b27590abb7fd89f2998f08227aee21d58a491346b85b',
                'audio': '9e42e31cbc41cb3c31dc4ddb1dc05fef322c61b98cc03a38c06749b2db94f6b2'}
    if not interpreter.is_file() or any(digest(files[key]) != value for key, value in expected.items()):
        raise ValueError('Installed interpreter/public probe files are unavailable or changed.')
    source_hash = digest(checkpoint)
    core, mind, _ = load_scheduler(checkpoint)
    before = {'observations': core.native.observations, 'lifetime': core.native.moments.next_id,
              'sources': len(core.native.sources), 'reports': len(core.native.interpretations.records)}
    old_banks = [source_digest(block).clone() for block in mind.actor.session.memory.blocks]
    try:
        if core.native_stream.jobs or core.interactions.records or 'hami' in core.native.names:
            raise ValueError('Probe requires a copied source without pending inputs or the new word.')
        core.native_stream = NativeStream(core)
        core.configure_native_attention('full')
        core.agent.endpoint, core.agent.model = endpoint, model
        save(output / 'seed.pt', core)
    finally:
        close_agent(core, mind)
    sensory = NativeInbox(output / 'sensory')
    human = InteractionInbox(output / 'human')
    runtime = output / 'runtime'
    environment = os.environ.copy()
    environment.update(PYTHONIOENCODING='utf-8', ALICE_EXPERIMENT_RAM_FRACTION='.9')
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    command = [sys.executable, '-m', 'scripts.alice_memory.persistent_runtime', '--store', str(runtime),
        '--checkpoint', str(output / 'seed.pt'), '--seconds', '240', '--save-every', '1',
        '--native-inbox', str(sensory.root), '--native-backend', 'installed', '--native-models', str(model_folder),
        '--native-interpreter', str(interpreter), '--native-ram-fraction', '.9',
        '--interaction-inbox', str(human.root), '--native-attention', 'full']
    stdout = (output / 'runtime.stdout.log').open('wb')
    stderr = (output / 'runtime.stderr.log').open('wb')
    process = None
    report = {'integration_passed': False, 'live_sensors': False, 'sensory_encoder_is_fixture': False,
              'language_backend_is_real': True, 'public_file_sha256': expected, 'before': before,
              'free_chat': False, 'report_protocol_is_literal': True}
    def wait_for(predicate, timeout=100.):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('Interactive owner exited before responding.')
            value = predicate()
            if value:
                return value
            time.sleep(.05)
        raise TimeoutError('Interactive owner response deadline exceeded.')
    client = [sys.executable, '-m', 'scripts.alice_memory.send_alice_message', '--inbox', str(human.root)]
    def send(action, text, *options):
        sent = subprocess.run(client + [action, text, *options], cwd=root, env=environment,
            capture_output=True, text=True, timeout=20, creationflags=flags, check=True)
        identifier = sent.stdout.strip()
        receipt = wait_for(lambda: human.receipt(identifier))
        if receipt['result']['status'] != 'completed':
            raise ValueError('Live interaction was not understood: ' + json.dumps(receipt['result'], ensure_ascii=False))
        return identifier, receipt['result']
    question = 'Qual é a informação atual de "hami" sobre "autor", pela imagem?'
    try:
        process = subprocess.Popen(command, cwd=root, env=environment, stdout=stdout, stderr=stderr,
                                   stdin=subprocess.DEVNULL, creationflags=flags)
        wait_for(lambda: (runtime / 'status.json').exists() and
            json.loads((runtime / 'status.json').read_text(encoding='utf-8')).get('phase') == 'running')
        unknown_id, unknown = send('meaning', question)
        assert not unknown['data']['evidence']['sensory']['supported']
        assert not unknown['data']['evidence']['reports']
        # Separate perception workers release each modality's model before the
        # next. Keep the failed combined-frame trial as a budget diagnostic.
        frame = sensory.publish({'image': files['image']})
        sequence = int(frame.split('-')[1])
        captured_wall = sensory.read(frame)['captured_wall']
        name_id, named = send('name', 'Essa imagem se chama hami.', '--frame-stream', sensory.stream_id,
                              '--frame-sequence', str(sequence), '--focus', 'image')
        moment = named['learning']['retained_moment']
        assert moment == before['lifetime']
        first_id, initial = send('report', f'No momento {moment}, associe "autor" a "pai".')
        version = initial['learning']['version']
        ambiguity_id, ambiguous = send('meaning', question)
        assert ambiguous['data']['evidence']['sensory']['reason'] == 'ambiguous_moments'
        assert not ambiguous['data']['evidence']['reports']
        window = f' em UTC [{captured_wall-.01:.6f}; {captured_wall+.01:.6f}]'
        timed_question = question[:-1] + window + '?'
        answer_id, answer = send('meaning', timed_question)
        assert answer['data']['evidence']['reports']['current']['subject'] == 'pai'
        audio_frame = sensory.publish({'audio': files['audio']})
        audio_sequence = int(audio_frame.split('-')[1])
        audio_receipt_path = sensory.root / 'receipts' / f'frame-{audio_sequence:07d}.json'
        audio_receipt = wait_for(lambda: json.loads(audio_receipt_path.read_text(encoding='utf-8')) if audio_receipt_path.exists() else None)
        assert audio_receipt['status'] == 'completed' and audio_receipt['result']['encoded'] == 1
        correction_id, corrected = send('report', f'Corrija o momento {moment}: "autor" passa a ser "mae"; substitua [{version}].')
        assert corrected['learning']['corrected'] == [version]
        comparison_id, comparison = send('meaning', 'O que mudou em "hami" sobre "autor", pela imagem' + window + '?')
        evidence = comparison['data']['evidence']
        assert evidence['reports']['initial']['subject'] == 'pai'
        assert evidence['reports']['current']['subject'] == 'mae'
        assert not evidence['reports']['current']['directly_observed']
        assert '"pai"' in comparison['data']['proposal']['text'] and '"mae"' in comparison['data']['proposal']['text']
        (runtime / 'stop.request').write_text('stop', encoding='utf-8')
        process.wait(timeout=30)
        assert process.returncode == 0
        status = json.loads((runtime / 'status.json').read_text(encoding='utf-8'))
        assert status['phase'] == 'stopped' and status['workers_terminal'] and status['native_workers_terminal']
        pointer = json.loads((runtime / 'current.json').read_text(encoding='utf-8'))
        fresh, fresh_mind, _ = load_scheduler(runtime / pointer['current']['file'])
        try:
            native = fresh.native
            assert native.observations == before['observations'] + 2 and native.moments.next_id == before['lifetime'] + 2
            assert len(native.sources) == before['sources'] + 1
            assert len(native.interpretations.records) == before['reports'] + 2
            assert native.interpret(moment, 'autor', 'initial')['subject'] == 'pai'
            assert native.interpret(moment, 'autor')['subject'] == 'mae'
            assert all(torch.equal(old, source_digest(block)) for old, block in zip(old_banks, fresh_mind.actor.session.memory.blocks))
            proof = native.naming_proofs[-1]
            assert proof['moment_ref']['source_context']['source_sequence'] == sequence
            assert native.sources[-1]['samples']['image'] == expected['image']
            assert not fresh.native_statements.jobs and not fresh.native_meaning_queries.jobs
            assert digest(checkpoint) == source_hash
            save(output / 'final.pt', fresh)
            report.update(integration_passed=True, moment=moment, initial_version=version,
                observations=native.observations, lifetime=native.moments.next_id,
                old_banks_preserved=len(old_banks), source_checkpoint_unchanged=True,
                writer_commits=status['writer_commits'], workers_terminal=True,
                modality_workers_are_sequential=True, source_frames=2,
                unqualified_query_is_ambiguous=True, temporal_cue_basis='utc',
                request_ids={'unknown': unknown_id, 'name': name_id, 'initial': first_id,
                    'ambiguous': ambiguity_id, 'before_correction': answer_id,
                    'correction': correction_id, 'comparison': comparison_id},
                initial_answer=answer['data']['proposal']['text'], comparison_answer=comparison['data']['proposal']['text'])
        finally:
            close_agent(fresh, fresh_mind)
    except (OSError, RuntimeError, ValueError, KeyError, AssertionError, subprocess.SubprocessError) as error:
        report['error'] = type(error).__name__ + ': ' + str(error)[:4096]
        raise
    finally:
        if process is not None and process.poll() is None:
            (runtime / 'stop.request').write_text('stop', encoding='utf-8')
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        stdout.close()
        stderr.close()
        atomic_json(output / 'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--model', default='qwen3.5:0.8b-q8_0')
    args = parser.parse_args()
    report = run(args.checkpoint, args.output, args.endpoint, args.model)
    print({key: report.get(key) for key in ('integration_passed', 'observations', 'writer_commits')})


if __name__ == '__main__':
    main()
