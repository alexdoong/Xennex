"""Installed expression selection through the persistent owner; replay one acquired text."""
import argparse
import copy
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import torch

from .conceptual_mind import save
from .continuous_experiment import load_scheduler
from .interaction_inbox import InteractionInbox, atomic
from .persistent_runtime import close_agent, configure_language
from .runtime_store import atomic_json, digest


def run(checkpoint, output, endpoint, model):
    output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(1)
    checksum = digest(checkpoint)
    report = {'integration_passed': False, 'quality_approved': False, 'replayed_acquired_text': True,
              'fresh_sensory_inference': False, 'live_sensors': False, 'new_model_downloaded': False}
    process = None
    streams = []
    runtime = output / 'runtime'
    try:
        core, mind, _ = load_scheduler(checkpoint)
        try:
            turns = [r for r in core.interactions.records.values() if r['request']['action'] == 'talk'
                     and r['status'] == 'completed' and r['request']['payload']['about'] is not None]
            if not turns:
                raise ValueError('Probe requires an acquired dialogue with a selected memory topic.')
            turn = max(turns, key=lambda r: r['request']['sequence'])
            payload = copy.deepcopy(turn['request']['payload'])
            before = core.native.observations, core.native.moments.next_id
            weights = core.native.interpretations.bank.weights.clone()
            names = core.native.names.copy()
            parser_model = core.agent.model
            configure_language(core, endpoint, parser_model)
            save(output / 'seed.pt', core)
            human_folder = output / 'human'
            human_folder.mkdir()
            atomic(human_folder / 'interaction.json', {'format': 1, 'stream_id': core.interactions.stream_id})
            atomic(human_folder / 'counter.json', {'next': core.interactions.last_sequence + 1})
        finally:
            close_agent(core, mind)
        human = InteractionInbox(human_folder)
        environment = os.environ.copy()
        environment.update(PYTHONIOENCODING='utf-8', ALICE_EXPERIMENT_RAM_FRACTION='.9')
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

        def start(selection):
            stdout, stderr = (output / ('runtime-' + str(len(streams)) + '.stdout.log')).open('wb'), (output / ('runtime-' + str(len(streams)) + '.stderr.log')).open('wb')
            streams.extend((stdout, stderr))
            return subprocess.Popen([sys.executable, '-m', 'scripts.alice_memory.persistent_runtime',
                '--store', str(runtime), '--checkpoint', str(output / 'seed.pt'), '--seconds', '180',
                '--save-every', '1', '--interaction-inbox', str(human.root), '--dialogue-model', selection],
                cwd=Path.cwd(), env=environment, stdout=stdout, stderr=stderr,
                stdin=subprocess.DEVNULL, creationflags=flags)

        def wait_for(predicate):
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('Owned dialogue runtime stopped; inspect retained stderr.')
                value = predicate()
                if value:
                    return value
                time.sleep(.05)
            raise TimeoutError('Dialogue selection deadline exceeded.')

        def stop():
            (runtime / 'stop.request').write_text('stop', encoding='utf-8')
            process.wait(timeout=30)
            if process.returncode != 0:
                raise RuntimeError('Owned dialogue runtime did not stop normally.')

        process = start(model)
        wait_for(lambda: (runtime / 'status.json').exists() and json.loads((runtime / 'status.json').read_text(encoding='utf-8')).get('phase') == 'running')
        identifier = human.publish('talk', payload)
        receipt = wait_for(lambda: human.receipt(identifier))
        if receipt['result']['status'] != 'completed' or receipt['result']['data']['proposal']['model'] != model:
            raise ValueError('Dialogue selection did not produce the requested model response.')
        report.update(request_id=identifier, question=payload['text'], receipt=receipt)
        atomic_json(output / 'report.json', report)
        stop()
        (runtime / 'stop.request').unlink()
        process = start('')
        wait_for(lambda: json.loads((runtime / 'status.json').read_text(encoding='utf-8')).get('phase') == 'running')
        stop()
        pointer = json.loads((runtime / 'current.json').read_text(encoding='utf-8'))
        fresh, fresh_mind, _ = load_scheduler(runtime / pointer['current']['file'])
        try:
            if (fresh.native.observations, fresh.native.moments.next_id) != before or not torch.equal(weights, fresh.native.interpretations.bank.weights) or fresh.native.names != names:
                raise RuntimeError('Expression selection changed source learning or experiences.')
            if fresh.agent.model != parser_model or fresh.dialogues.model is not None:
                raise RuntimeError('Expression selection changed parser or failed to reset.')
            if fresh.interactions.records[identifier]['result']['data']['proposal']['model'] != model:
                raise RuntimeError('Restart lost historical expression provenance.')
            if digest(checkpoint) != checksum:
                raise RuntimeError('Expression selection rewrote source checkpoint.')
            save(output / 'final.pt', fresh)
            report.update(integration_passed=True, parser_model=parser_model, expression_model=model,
                reset_to_shared_model=True, historical_model_retained=True, source_unchanged=True,
                observations=before[0], lifetime_moments=before[1], interpretation_weights_unchanged=True)
        finally:
            close_agent(fresh, fresh_mind)
    finally:
        if process is not None and process.poll() is None:
            (runtime / 'stop.request').write_text('stop', encoding='utf-8')
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for stream in streams:
            stream.close()
        atomic_json(output / 'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--model', default='qwen3.5:4b')
    args = parser.parse_args()
    result = run(args.checkpoint, args.output, args.endpoint, args.model)
    print({'integration_passed': result['integration_passed'], 'quality_approved': False})


if __name__ == '__main__':
    main()
