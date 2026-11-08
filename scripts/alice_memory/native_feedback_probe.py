"""Finite local pretrained Portuguese reaction benchmark and owner integration."""
import argparse
import copy
import time
from pathlib import Path

import torch
from dataclasses import asdict

from .continuous_experiment import load_scheduler
from .native_feedback_language import FeedbackLanguage
from .language import LocalLanguage
from .language_process import LanguageProcess
from .native_sensor import NativeObservation
from .persistent_runtime import close_agent, configure_language
from .conceptual_mind import save
from .reactivation_index import source_digest
from .runtime_store import RuntimeStore, atomic_json

CASES = (
    ('Porra, gostei muito disso.', 'encouraging'),
    ('Essa interação me deixou satisfeito.', 'encouraging'),
    ('Foi agradável ficar em silêncio com você.', 'encouraging'),
    ('Curti o que aconteceu agora.', 'encouraging'),
    ('Não gostei disso.', 'discouraging'),
    ('Isso me deixou frustrado.', 'discouraging'),
    ('Porra, achei essa interação péssima.', 'discouraging'),
    ('Ficar ouvindo esse som foi desagradável.', 'discouraging'),
    ('Gostei disso?', 'uncertain'),
    ('Ele disse "gostei disso".', 'uncertain'),
    ('Talvez isso seja agradável.', 'uncertain'),
    ('Quero saber de onde vem esse som.', 'uncertain'),
    ('Adorei esse momento.', 'encouraging'),
    ('Me senti confortável nessa interação.', 'encouraging'),
    ('Isso me agradou de verdade.', 'encouraging'),
    ('Essa experiência me desagradou.', 'discouraging'),
    ('Foi chato ficar desse jeito.', 'discouraging'),
    ('Eu detestei o que ocorreu.', 'discouraging'),
)


def probe(checkpoint, output, endpoint, model):
    if output.exists():
        raise ValueError('Feedback trial needs a fresh output.')
    output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(1)
    report = {'accepted': False, 'scope': 'pretrained interpretation of direct Portuguese social feedback; synthetic native cues',
              'cases': [], 'jobs': [], 'live_sensors': False, 'new_model_downloaded': False}
    agent, mind, _ = load_scheduler(checkpoint)
    workers = []
    try:
        configure_language(agent, endpoint=endpoint, model=model)
        language = LocalLanguage(endpoint, model, timeout=90, wait_seconds=0, ram_fraction=.9)
        bridge = FeedbackLanguage(language)
        for message, expected in CASES:
            try:
                plan = asdict(bridge.parse(message))
                report['cases'].append({'message': message, 'expected': expected, 'plan': plan,
                                        'correct': plan['reaction'] == expected})
            except (OSError, RuntimeError, ValueError) as error:
                report['cases'].append({'message': message, 'expected': expected, 'correct': False, 'error': str(error)[:1024]})
        old_banks = [source_digest(block).clone() for block in mind.actor.session.memory.blocks]
        old_names, old_reports = agent.native.names.copy(), copy.deepcopy(agent.native.interpretations.records)
        before = {'feedback': len(agent.native.attention.sources), 'impact': int(agent.native.moments.values.updates.sum()),
                  'observations': agent.native.observations, 'lifetime': agent.native.moments.next_id}
        def factory(operation):
            if any(worker.process.poll() is None for worker in workers):
                raise ValueError('Feedback trial attempted concurrent model workers.')
            worker = LanguageProcess(operation, output / 'workers', 120.,
                environment={'ALICE_EXPERIMENT_RAM_FRACTION': '.9'}, retain_files=True)
            workers.append(worker)
            return worker
        agent.agent.worker_factory = factory
        agent.configure_native_attention('learned')
        messages = ('Porra, gostei do que aconteceu.', 'Não gostei dessa interação.',
                    'Talvez tenha sido bom.', 'Gostei disso?')
        expected_status = ('completed', 'completed', 'uncertain', 'uncertain')
        for index, message in enumerate(messages):
            at = agent.clock + .1
            sequence = max(item['sequence'] for item in agent.native.last.values()) + 1
            signals = [NativeObservation(name, torch.nn.functional.one_hot(torch.tensor(axis), 128).float(), at,
                        sequence, 'a' * 64, origin='environment') for name, axis in (('image', 20), ('audio', 21))]
            event = agent.perceive_native(signals, .1)['native_perception']
            number = agent.submit_native_feedback(message, event['attention']['id'])
            deadline = time.monotonic() + 115.
            while agent.native_feedbacks.jobs[number]['status'] not in agent.native_feedbacks.terminal:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Finite feedback trial expired; pending state retained below.')
                agent.tick(.05)
                time.sleep(.05)
            job = agent.take_native_feedback(number)
            report['jobs'].append(job)
            if job['status'] != expected_status[index]:
                raise ValueError('Real feedback did not match the supplied evaluation: ' + str(job)[:2048])
        if len(agent.native.attention.sources) != before['feedback'] + 2 or int(agent.native.moments.values.updates.sum()) != before['impact'] + 2:
            raise ValueError('Uncertain feedback trained or valid feedback missed its two episodes.')
        if agent.native.names != old_names or agent.native.interpretations.records != old_reports or len(old_banks) != len(mind.actor.session.memory.blocks) or any(not torch.equal(value, source_digest(block)) for value, block in zip(old_banks, mind.actor.session.memory.blocks)):
            raise ValueError('Language feedback changed earlier knowledge or synthetic episodes.')
        for _ in range(2):
            with RuntimeStore(output / 'runtime') as store:
                store.submit(store.capture(agent), agent.clock)
                if store.finish()['status'] != 'committed':
                    raise ValueError('Could not publish feedback sources and learned values.')
        report.update(before=before, correct=sum(case['correct'] for case in report['cases']), total=len(CASES),
            language_sources=[source['language'] for source in agent.native.attention.sources[-2:]],
            feedback_delta=2, impact_delta=2, old_banks_preserved=len(old_banks),
            parent_observations=agent.native.observations, shared_valence=mind.internal.valence,
            workers_terminal=all(worker.process.poll() is not None for worker in workers),
            accepted=all(case['correct'] for case in report['cases']))
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)[:2048]
        raise
    finally:
        save(output / 'final.pt', agent)
        atomic_json(output / 'report.json', report)
        close_agent(agent, mind)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--endpoint', default='http://127.0.0.1:11438')
    parser.add_argument('--model', default='qwen3.5:0.8b-q8_0')
    args = parser.parse_args()
    report = probe(args.checkpoint, args.output, args.endpoint, args.model)
    print({key: report.get(key) for key in ('accepted', 'correct', 'total', 'feedback_delta', 'impact_delta')})
    raise SystemExit(0 if report['accepted'] else 2)


if __name__ == '__main__':
    main()
