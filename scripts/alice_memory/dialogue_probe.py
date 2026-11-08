"""Finite installed text encoder + pretrained conversation on the persistent owner."""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import torch

from .continuous_experiment import load_scheduler
from .conceptual_mind import save
from .interaction_inbox import InteractionInbox
from .persistent_runtime import close_agent
from .runtime_store import atomic_json, digest
from .ui_gateway import prepare, execute


def run(checkpoint, output, endpoint, model, native_models, native_python, *, automatic_name=None):
    output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(1)
    checksum = digest(checkpoint)
    old, old_mind, _ = load_scheduler(checkpoint)
    try:
        names = old.native.names.copy()
        weights = old.native.interpretations.bank.weights.clone()
        before = {'observations': old.native.observations, 'moments': old.native.moments.next_id}
        parents = [item['request']['id'] for item in old.interactions.records.values() if item['request']['action'] == 'relate' and item['status'] == 'completed']
        if len(parents) != 1:
            raise ValueError('Dialogue probe needs one resolved contextual report.')
        parent = parents[0]
        parser_model = model if automatic_name is None else old.agent.model
        expected = None
        if automatic_name is not None:
            from .written_symbols import symbol
            if symbol(automatic_name) != automatic_name or automatic_name not in names:
                raise ValueError('Automatic dialogue requires a previously learned name.')
            source = old.interactions.report_source(parent)
            relation = old.native.interpretations.relations[source['relation']]
            expected = {view: old.native.interpret(source['moment'], relation, view)['subject'] for view in ('initial', 'current')}
            if any(value is None for value in expected.values()):
                raise ValueError('Automatic dialogue requires supported source interpretations.')
        questions = ((f'Quem é o dono de {automatic_name} atualmente?', None),) if automatic_name is not None else (
            ('Oi!\nPorra, tudo bem?', None), ('Quero conversar sobre formigas. O que você sabe sobre elas?', None),
            ('Quem é o dono dessa imagem atualmente?', parent))
    finally:
        close_agent(old, old_mind)
    root = output / 'session'
    prepare(root, checkpoint)
    inbox = InteractionInbox(root / 'human')
    runtime = root / 'runtime'
    report = {'integration_passed': False, 'language_backend_is_real': True, 'native_encoder_is_real': True,
              'live_sensors': False, 'speech_audio_emitted': False, 'free_text_semantics_verified': False,
              'source_sha256': checksum, 'before': before, 'turns': [],
              'automatic_name': automatic_name, 'parser_model': parser_model,
              'expression_model': model, 'explicit_topic_selected': automatic_name is None}
    process = None
    stdout = (output / 'stdout.log').open('w', encoding='utf-8')
    stderr = (output / 'stderr.log').open('w', encoding='utf-8')
    try:
        process = subprocess.Popen([sys.executable, '-m', 'scripts.alice_memory.persistent_runtime',
            '--store', str(runtime), '--checkpoint', str(root / 'seed.pt'), '--seconds', '240', '--save-every', '1',
            '--interaction-inbox', str(root / 'human'), '--endpoint', endpoint, '--model', parser_model,
            *(['--dialogue-model', model] if automatic_name is not None else []),
            '--native-inbox', str(root / 'sensory'), '--native-models', str(native_models),
            '--native-interpreter', str(native_python), '--native-ram-fraction', '.9', '--native-attention', 'full'],
            stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL,
            env={**os.environ, 'PYTHONIOENCODING': 'utf-8', 'ALICE_EXPERIMENT_RAM_FRACTION': '.9'},
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)

        def wait_for(read):
            deadline = time.monotonic() + 100.
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('Owned runtime stopped before dialogue delivery.')
                value = read()
                if value:
                    return value
                time.sleep(.1)
            raise TimeoutError('Dialogue input/response did not finish in the finite probe.')

        def state():
            path = runtime / 'status.json'
            return None if not path.exists() else json.loads(path.read_text(encoding='utf-8'))

        wait_for(lambda: (value if value and value['phase'] == 'running' else None) if (value := state()) else None)
        for question, about in questions:
            frame = execute(root, {'action': 'text', 'text': question})
            selected = {key: frame[key] for key in ('stream_id', 'sequence')}
            identifier = inbox.publish('talk', {'text': question, 'frame': selected, 'about': about})
            receipt = wait_for(lambda: inbox.receipt(identifier))
            if receipt['result']['status'] != 'completed':
                raise RuntimeError('Dialogue failed: ' + json.dumps(receipt, ensure_ascii=False))
            data = receipt['result']['data']
            if not data['evidence']['input']['acquired'] or data['evidence']['input']['frame'] != selected or data['proposal']['factual_text_verified'] is not False:
                raise RuntimeError('Dialogue changed its acquired input or promoted generated speech.')
            if about is not None and data['evidence']['memory']['reports']['current']['subject'] != 'mãe':
                raise RuntimeError('Owner context lost the corrected interpretation.')
            if automatic_name is not None:
                association = data['evidence']['association']
                if data['evidence']['about'] is not None or data['evidence']['memory'] is not None or association['reason'] != 'recalled_topic':
                    raise RuntimeError('Automatic dialogue did not retrieve a topic without manual selection.')
                actual = {view: value['subject'] for view, value in association['memory']['reports'].items()}
                if actual != expected or data['proposal']['model'] != model:
                    raise RuntimeError('Automatic dialogue changed source interpretations or expression model.')
            report['turns'].append({'id': identifier, 'question': question, 'receipt': receipt})
            atomic_json(output / 'partial.json', report)
        (runtime / 'stop.request').write_text('stop', encoding='utf-8')
        process.wait(timeout=30)
        if process.returncode != 0:
            raise RuntimeError('Dialogue runtime did not stop normally.')
        pointer = json.loads((runtime / 'current.json').read_text(encoding='utf-8'))
        fresh, fresh_mind, _ = load_scheduler(runtime / pointer['current']['file'])
        try:
            after = {'observations': fresh.native.observations, 'moments': fresh.native.moments.next_id}
            if after != {'observations': before['observations'] + len(questions), 'moments': before['moments'] + len(questions)}:
                raise RuntimeError('Text dialogue changed its experience counts.')
            if fresh.native.names != names or not torch.equal(fresh.native.interpretations.bank.weights, weights):
                raise RuntimeError('Generated speech rewrote earlier learned facts or names.')
            if any(fresh.interactions.records[turn['id']]['status'] != 'completed' for turn in report['turns']):
                raise RuntimeError('Restore lost a completed dialogue turn.')
            if fresh.agent.model != parser_model:
                raise RuntimeError('Expression replaced the source parser model.')
            save(output / 'final.pt', fresh)
            report.update(after=after, restart_verified=True, interpretation_weights_preserved=True, names_preserved=True,
                          source_unchanged=digest(checkpoint) == checksum, integration_passed=True)
        finally:
            close_agent(fresh, fresh_mind)
        if not report['source_unchanged']:
            raise RuntimeError('Dialogue modified the source state.')
        atomic_json(output / 'report.json', report)
        return report
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        report['error'] = type(error).__name__ + ': ' + str(error)[:4096]
        raise
    finally:
        if process is not None and process.poll() is None:
            (runtime / 'stop.request').write_text('stop', encoding='utf-8')
            try: process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=10)
        stdout.close(); stderr.close()
        atomic_json(output / 'report.json', report)


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--model', default='qwen3.5:0.8b-q8_0')
    parser.add_argument('--native-models', type=Path, default=root / 'bin/AliceMemory/EmbeddingGemma2/914f7f89142e33e77833254d9c9b90c3cef7303b')
    parser.add_argument('--native-python', type=Path, default=root / 'bin/AliceMemory/perception-venv/Scripts/python.exe')
    args = parser.parse_args()
    result = run(args.checkpoint, args.output, args.endpoint, args.model, args.native_models, args.native_python)
    print({'integration_passed': result['integration_passed'], 'turns': len(result['turns']), 'free_text_semantics_verified': False})


if __name__ == '__main__': main()
