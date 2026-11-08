"""Live short questions reference learned reports; no numeric window in text."""
import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

import torch

from .conceptual_mind import save
from .continuous_experiment import load_scheduler
from .interaction_inbox import InteractionInbox, atomic
from .language import LocalLanguage
from .reference_language import ReferenceLanguage
from .persistent_runtime import close_agent
from .runtime_store import atomic_json, digest

CASES = (
    ('Quem era antes?', 'initial'), ('E antes?', 'initial'), ('Quem foi?', 'initial'),
    ('Qual era a informação original?', 'initial'),
    ('E agora?', 'current'), ('Quem é?', 'current'), ('Quem é agora?', 'current'),
    ('Qual é a informação atual?', 'current'),
    ('O que mudou?', 'comparison'), ('Compare antes e agora.', 'comparison'),
    ('Compare as versões.', 'comparison'), ('Quem era agora?', 'uncertain'),
    ('Qual é a capital do Japão?', 'uncertain'), ('Por que ela agiu assim?', 'uncertain'),
)


def run(checkpoint, output, endpoint, model):
    output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(1)
    report = {'integration_passed': False, 'live_sensors': False, 'fresh_sensory_inference': False,
              'language_backend_is_real': True, 'free_chat': False, 'message_reference_is_supplied': True}
    process = stdout = stderr = None
    try:
        bridge = ReferenceLanguage(LocalLanguage(endpoint, model, timeout=90, wait_seconds=0, ram_fraction=.9))
        cases = []
        for question, expected in CASES:
            item = {'question': question, 'expected': expected, 'correct': False}
            try:
                plan = asdict(bridge.parse(question))
                item.update(correct=plan['view'] == expected, plan=plan)
            except (OSError, RuntimeError, ValueError) as error:
                item['error'] = type(error).__name__ + ': ' + str(error)[:2048]
            cases.append(item)
        report['benchmark'] = {'accepted': all(item['correct'] for item in cases),
            'correct': sum(item['correct'] for item in cases), 'total': len(cases),
            'guarded_questions_are_constrained': 3, 'cases': cases}
        atomic_json(output / 'benchmark.json', report['benchmark'])
        original_hash = digest(checkpoint)
        core, mind, _ = load_scheduler(checkpoint)
        try:
            parents = [item for item in core.interactions.records.values() if item['request']['action'] == 'relate'
                       and item['status'] == 'completed' and item['result']['learning']['kind'] == 'reported_interpretation']
            if len(parents) != 1 or any(item['status'] not in ('completed', 'failed') for item in core.interactions.records.values()):
                raise ValueError('Probe requires one resolved contextual report in the copied conversation.')
            parent = parents[0]['request']['id']
            version = parents[0]['result']['learning']['version']
            source = core.native.interpretations.records[version]
            relation = core.native.interpretations.relations[source['relation']]
            if core.native.interpret(source['moment'], relation, 'initial')['subject'] != 'pai' or core.native.interpret(source['moment'], relation)['subject'] != 'mãe':
                raise ValueError('Probe source lacks the contextual father/mother revision.')
            report['before'] = {'observations': core.native.observations, 'lifetime': core.native.moments.next_id,
                              'reports': len(core.native.interpretations.records)}
            core.agent.endpoint, core.agent.model = endpoint, model
            save(output / 'seed.pt', core)
            human_folder = output / 'human'
            human_folder.mkdir()
            atomic(human_folder / 'interaction.json', {'format': 1, 'stream_id': core.interactions.stream_id})
            atomic(human_folder / 'counter.json', {'next': core.interactions.last_sequence + 1})
        finally:
            close_agent(core, mind)
        human = InteractionInbox(human_folder)
        runtime = output / 'runtime'
        env = os.environ.copy()
        env.update(PYTHONIOENCODING='utf-8', ALICE_EXPERIMENT_RAM_FRACTION='.9')
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        stdout, stderr = (output / 'runtime.stdout.log').open('wb'), (output / 'runtime.stderr.log').open('wb')
        process = subprocess.Popen([sys.executable, '-m', 'scripts.alice_memory.persistent_runtime',
            '--store', str(runtime), '--checkpoint', str(output / 'seed.pt'), '--seconds', '120', '--save-every', '1',
            '--interaction-inbox', str(human.root)], cwd=Path.cwd(), env=env, stdout=stdout, stderr=stderr,
            stdin=subprocess.DEVNULL, creationflags=flags)
        def wait_for(predicate, timeout=90.):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('Referenced owner exited before responding.')
                value = predicate()
                if value:
                    return value
                time.sleep(.05)
            raise TimeoutError('Referenced response deadline exceeded.')
        wait_for(lambda: (runtime / 'status.json').exists() and
            json.loads((runtime / 'status.json').read_text(encoding='utf-8')).get('phase') == 'running')
        requests, answers = [], []
        client = [sys.executable, '-m', 'scripts.alice_memory.send_alice_message', '--inbox', str(human.root), 'recall', parent]
        for question in ('Quem era antes?', 'E agora?', 'O que mudou?'):
            sent = subprocess.run(client + [question], cwd=Path.cwd(), env=env, capture_output=True,
                                  text=True, timeout=20, creationflags=flags, check=True)
            identifier = sent.stdout.strip()
            receipt = wait_for(lambda: human.receipt(identifier))
            if receipt['result']['status'] != 'completed':
                raise ValueError('Referenced question was not understood: ' + json.dumps(receipt['result'], ensure_ascii=False))
            answer = receipt['result']['data']
            requests.append(identifier)
            answers.append(answer)
        assert answers[0]['evidence']['reports']['initial']['subject'] == 'pai'
        assert answers[1]['evidence']['reports']['current']['subject'] == 'mãe'
        assert answers[2]['evidence']['reports']['initial']['subject'] == 'pai' and answers[2]['evidence']['reports']['current']['subject'] == 'mãe'
        assert all(answer['evidence']['moment_ref'] == source['moment_ref'] for answer in answers)
        (runtime / 'stop.request').write_text('stop', encoding='utf-8')
        process.wait(timeout=30)
        assert process.returncode == 0
        status = json.loads((runtime / 'status.json').read_text(encoding='utf-8'))
        assert status['phase'] == 'stopped' and status['workers_terminal'] and status['native_workers_terminal']
        pointer = json.loads((runtime / 'current.json').read_text(encoding='utf-8'))
        fresh, fresh_mind, _ = load_scheduler(runtime / pointer['current']['file'])
        try:
            assert fresh.native.observations == report['before']['observations']
            assert fresh.native.moments.next_id == report['before']['lifetime']
            assert len(fresh.native.interpretations.records) == report['before']['reports']
            assert digest(checkpoint) == original_hash
            save(output / 'final.pt', fresh)
            report.update(integration_passed=True, parent_id=parent, request_ids=requests,
                observations=fresh.native.observations, lifetime=fresh.native.moments.next_id,
                reports=len(fresh.native.interpretations.records), source_checkpoint_unchanged=True,
                writer_commits=status['writer_commits'], workers_terminal=True,
                answers=[answer['proposal']['text'] for answer in answers], moment=source['moment'])
        finally:
            close_agent(fresh, fresh_mind)
    except (OSError, RuntimeError, ValueError, KeyError, AssertionError, subprocess.SubprocessError) as error:
        report['error'] = type(error).__name__ + ': ' + str(error)[:4096]
        raise
    finally:
        if process is not None and process.poll() is None:
            (output / 'runtime/stop.request').write_text('stop', encoding='utf-8')
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if stdout is not None:
            stdout.close()
        if stderr is not None:
            stderr.close()
        atomic_json(output / 'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--model', default='qwen3.5:0.8b-q8_0')
    a = parser.parse_args()
    r = run(a.checkpoint, a.output, a.endpoint, a.model)
    print({'integration_passed': r['integration_passed'], 'benchmark': f"{r['benchmark']['correct']}/{r['benchmark']['total']}"})


if __name__ == '__main__':
    main()
