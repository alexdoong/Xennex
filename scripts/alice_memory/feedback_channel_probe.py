"""Finite real-language feedback through live input; sensory cue is synthetic."""
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
from .native_sensor import NativeObservation
from .persistent_runtime import close_agent, configure_language
from .runtime_store import atomic_json, digest
from .ui_gateway import prepare


def run(checkpoint, output, endpoint, model):
    output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(1)
    checksum = digest(checkpoint)
    report = {'passed': False, 'language_backend_is_real': True, 'synthetic_sensory_cue': True,
              'live_sensors': False, 'new_model_downloaded': False}
    process = None
    core, mind, _ = load_scheduler(checkpoint)
    try:
        configure_language(core, endpoint, model)
        core.configure_native_attention('learned')
        sequence = 1 + max([-1, *core.native.label_sequence.values(), *(item['sequence'] for item in core.native.last.values())])
        packet = NativeObservation('image', torch.nn.functional.one_hot(torch.tensor(0), 128).float(),
            core.clock + .1, sequence, 'd' * 64, origin='environment')
        response = core.perceive_native([packet], .1)['native_perception']
        action = response['attention']['id']
        if action is None:
            raise ValueError('The fixture did not yield a learned attention choice.')
        choice = core.native.attention.pending[action]
        key = choice['key'].clone()
        before = {'observations': core.native.observations, 'lifetime': core.native.moments.next_id,
                  'feedbacks': len(core.native.attention.sources),
                  'writes': int(core.native.attention.banks[choice['action']].writes),
                  'action': action, 'allocation': choice['action'], 'moment_ref': choice['moment_ref']}
        names = core.native.names.copy()
        save(output / 'prepared.pt', core)
    finally:
        close_agent(core, mind)
    root = output / 'session'
    prepare(root, output / 'prepared.pt')
    human = InteractionInbox(root / 'human')
    runtime = root / 'runtime'
    stdout = (output / 'stdout.log').open('w', encoding='utf-8')
    stderr = (output / 'stderr.log').open('w', encoding='utf-8')
    try:
        environment = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'ALICE_EXPERIMENT_RAM_FRACTION': '.9'}
        process = subprocess.Popen([sys.executable, '-m', 'scripts.alice_memory.persistent_runtime',
            '--store', str(runtime), '--checkpoint', str(root / 'seed.pt'), '--interaction-inbox', str(root / 'human'),
            '--seconds', '90', '--save-every', '1', '--endpoint', endpoint, '--model', model, '--native-attention', 'learned'],
            stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, env=environment,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)

        def wait_for(read):
            deadline = time.monotonic() + 65.
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('Owned runtime stopped before the feedback receipt.')
                result = read()
                if result:
                    return result
                time.sleep(.1)
            raise TimeoutError('Timed out waiting for the selected feedback action.')

        def ready():
            path = runtime / 'status.json'
            if not path.exists():
                return None
            value = json.loads(path.read_text(encoding='utf-8'))
            return value if value.get('phase') == 'running' and any(item['id'] == action for item in value.get('native_state', {}).get('attention_actions', [])) else None

        wait_for(ready)
        identifier = human.publish('feedback', {'text': 'Porra, gostei muito disso.', 'action': action})
        receipt = wait_for(lambda: human.receipt(identifier))
        if receipt['result']['status'] != 'completed' or not receipt['result']['learning']['learned']:
            raise RuntimeError('Installed language feedback failed: ' + json.dumps(receipt))
        duplicate = human.publish('feedback', {'text': 'Porra, gostei muito disso.', 'action': action})
        refused = wait_for(lambda: human.receipt(duplicate))
        if refused['result']['status'] != 'failed':
            raise RuntimeError('A consumed attention action was learned twice.')
        (runtime / 'stop.request').write_text('stop', encoding='utf-8')
        process.wait(timeout=30)
        if process.returncode != 0:
            raise RuntimeError('Owned runtime did not stop normally.')
        pointer = json.loads((runtime / 'current.json').read_text(encoding='utf-8'))
        restored, restored_mind, _ = load_scheduler(runtime / pointer['current']['file'])
        try:
            source = next(item for item in restored.native.attention.sources if item['id'] == action)
            bank = restored.native.attention.banks[choice['action']]
            after = {'observations': restored.native.observations, 'lifetime': restored.native.moments.next_id,
                     'feedbacks': len(restored.native.attention.sources), 'writes': int(bank.writes)}
            if after != {'observations': before['observations'], 'lifetime': before['lifetime'], 'feedbacks': before['feedbacks'] + 1, 'writes': before['writes'] + 1}:
                raise RuntimeError('The feedback changed its learning/perception counts.')
            if source['moment_ref'] != before['moment_ref'] or source['origin'] != 'person' or restored.native.names != names:
                raise RuntimeError('The feedback changed its selected event or the earlier names.')
            if restored.interactions.records[identifier]['status'] != 'completed' or restored.interactions.records[duplicate]['status'] != 'failed':
                raise RuntimeError('Restart lost a durable interaction outcome.')
            report.update(passed=True, before=before, after=after, receipt=receipt, duplicate=refused,
                          social_prediction=float((bank.weights @ key)[1]), source=source, source_sha256=checksum,
                          source_unchanged=digest(checkpoint) == checksum, restart_verified=True)
            save(output / 'final.pt', restored)
        finally:
            close_agent(restored, restored_mind)
        if not report['source_unchanged']:
            raise RuntimeError('The source checkpoint was changed.')
        atomic_json(output / 'report.json', report)
        return report
    finally:
        if process is not None and process.poll() is None:
            (runtime / 'stop.request').write_text('stop', encoding='utf-8')
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                # This is only the Popen handle created by this trial.
                process.kill()
                process.wait(timeout=10)
        stdout.close()
        stderr.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--model', default='qwen3.5:0.8b-q8_0')
    args = parser.parse_args()
    print({'passed': run(args.checkpoint, args.output, args.endpoint, args.model)['passed']})


if __name__ == '__main__':
    main()
