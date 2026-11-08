"""Finite separate-client ingress trial; real language, fixture sensory encoder."""
import argparse
import copy
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import torch
from PIL import Image

from .conceptual_mind import save
from .continuous_experiment import load_scheduler
from .interaction_inbox import InteractionInbox
from .native_inbox import NativeInbox
from .native_stream import NativeStream
from .persistent_runtime import close_agent
from .runtime_store import atomic_json, digest


def run(checkpoint, output, endpoint, model):
    output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(1)
    original_hash = digest(checkpoint)
    core, mind, _ = load_scheduler(checkpoint)
    before = {'observations': core.native.observations, 'lifetime': core.native.moments.next_id,
              'sources': len(core.native.sources), 'names': core.native.names.copy()}
    try:
        if core.native_stream.jobs or core.interactions.records:
            raise ValueError('Probe source has pending external inputs.')
        # A copied experiment uses its own input device/inbox; learned memories
        # and the source checkpoint are preserved. This is not an owner reset.
        core.native_stream = NativeStream(core)
        core.configure_native_attention('full')
        core.agent.endpoint, core.agent.model = endpoint, model
        save(output / 'seed.pt', core)
    finally:
        close_agent(core, mind)
    sensory = NativeInbox(output / 'sensory')
    human = InteractionInbox(output / 'human')
    runtime = output / 'runtime'
    Image.new('RGB', (64, 64), 'red').save(output / 'red.png')
    Image.new('RGB', (64, 64), 'blue').save(output / 'blue.png')
    stdout = (output / 'runtime.stdout.log').open('wb')
    stderr = (output / 'runtime.stderr.log').open('wb')
    environment = os.environ.copy()
    environment['PYTHONIOENCODING'] = 'utf-8'
    environment['ALICE_EXPERIMENT_RAM_FRACTION'] = '.9'
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    command = [sys.executable, '-m', 'scripts.alice_memory.persistent_runtime', '--store', str(runtime),
        '--checkpoint', str(output / 'seed.pt'), '--seconds', '90', '--save-every', '1',
        '--native-inbox', str(sensory.root), '--native-backend', 'fixture',
        '--interaction-inbox', str(human.root), '--native-attention', 'full']
    process = subprocess.Popen(command, cwd=Path.cwd(), env=environment, stdout=stdout, stderr=stderr,
                               stdin=subprocess.DEVNULL, creationflags=flags)
    report = {'integration_passed': False, 'live_sensors': False, 'sensory_encoder_is_fixture': True,
              'language_backend_is_real': True, 'clients_use_neural_imports': False}
    def wait_for(predicate, timeout=60.):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('Interactive owner exited before responding.')
            value = predicate()
            if value:
                return value
            time.sleep(.05)
        raise TimeoutError('Interactive owner response deadline exceeded.')
    try:
        wait_for(lambda: (runtime / 'status.json').exists() and
            json.loads((runtime / 'status.json').read_text(encoding='utf-8')).get('phase') == 'running')
        # Publish from a separate lightweight process after the owner has started.
        first = sensory.publish({'image': output / 'red.png'})
        frame_sequence = int(first.split('-')[1])
        client = [sys.executable, '-m', 'scripts.alice_memory.send_alice_message', '--inbox', str(human.root)]
        sent = subprocess.run(client + ['name', 'Essa imagem se chama melo?', '--frame-stream', sensory.stream_id,
            '--frame-sequence', str(frame_sequence)], cwd=Path.cwd(), env=environment,
            capture_output=True, text=True, timeout=20, creationflags=flags, check=True)
        identifier = sent.stdout.strip()
        clarification = wait_for(lambda: human.receipt(identifier))
        assert clarification['result']['status'] == 'awaiting_reply', clarification
        saved_request = copy.deepcopy(json.loads((runtime / 'status.json').read_text(encoding='utf-8'))['interaction_state'])
        # A later image must not redirect the pending human response.
        second = sensory.publish({'image': output / 'blue.png'})
        wait_for(lambda: (sensory.root / 'receipts' / f"frame-{int(second.split('-')[1]):07d}.json").exists())
        sent = subprocess.run(client + ['reply', identifier, 'Melo'], cwd=Path.cwd(), env=environment,
            capture_output=True, text=True, timeout=20, creationflags=flags, check=True)
        reply_id = sent.stdout.strip()
        replied = wait_for(lambda: human.receipt(reply_id))
        assert replied['result']['status'] == 'completed'
        parent = wait_for(lambda: (value if value and value['revision'] == 2 else None)
            if (value := human.receipt(identifier)) else None)
        assert parent['result']['learning']['name'] == 'melo'
        (runtime / 'stop.request').write_text('stop', encoding='utf-8')
        process.wait(timeout=30)
        assert process.returncode == 0
        status = json.loads((runtime / 'status.json').read_text(encoding='utf-8'))
        assert status['phase'] == 'stopped' and status['workers_terminal'] and status['native_workers_terminal']
        pointer = json.loads((runtime / 'current.json').read_text(encoding='utf-8'))
        restored, restored_mind, _ = load_scheduler(runtime / pointer['current']['file'])
        try:
            native = restored.native
            assert len(native.sources) == before['sources'] + 1 and native.observations == before['observations'] + 2
            assert native.moments.next_id == before['lifetime'] + 2
            proof = native.naming_proofs[-1]
            assert proof['moment_ref']['source_context']['source_sequence'] == frame_sequence
            assert proof['language']['kind'] == 'external_word_reply'
            assert restored.interactions.records[identifier]['published'] == 2
            assert not restored.native_namings.jobs
            assert digest(checkpoint) == original_hash
            report.update(integration_passed=True, request_id=identifier, reply_id=reply_id,
                clarification=clarification['result']['question'], before=before,
                observations=native.observations, lifetime=native.moments.next_id,
                taught_frame_sequence=frame_sequence, current_frame_sequence=int(second.split('-')[1]),
                writer_commits=status['writer_commits'], worker_handles_terminal=True,
                interaction_state_at_question=saved_request)
        finally:
            close_agent(restored, restored_mind)
    finally:
        if process.poll() is None:
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
    raise SystemExit(0 if report['integration_passed'] else 1)


if __name__ == '__main__':
    main()
