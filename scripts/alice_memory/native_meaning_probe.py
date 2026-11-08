"""Finite real-language questions on a copy of a corrected native runtime."""
from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path

import torch

from .continuous_experiment import load_scheduler
from .native_interpretation_probe import senses
from .persistent_runtime import close_agent, run
from .reactivation_index import source_digest
from .runtime_store import RuntimeStore, atomic_json


def learned_digest(agent, mind):
    digest = hashlib.sha256(senses(agent.native).encode())
    for block in mind.actor.session.memory.blocks:
        digest.update(source_digest(block).numpy().tobytes())
    for bank in [*agent.native.writers.values(), agent.native.interpretations.bank, *agent.concepts.banks.values()]:
        for key, tensor in sorted(bank.state_dict().items()):
            digest.update(key.encode())
            digest.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return digest.hexdigest()


def probe(source_runtime, output, seconds=30.):
    destination, original = output.resolve(), source_runtime.resolve()
    if output.exists() or not 5 <= seconds <= 120 or destination == original or original in destination.parents:
        raise ValueError('Meaning probe needs a new destination outside its source and finite stages.')
    torch.set_num_threads(1)
    with RuntimeStore(source_runtime) as source:
        agent, mind, _ = load_scheduler(source.candidates()[0][0])
        try:
            if 'maruvi' not in agent.native.names or agent.native.interpret(0, 'autor')['subject'] != 'mae' or agent.native.interpret(0, 'autor', 'initial')['subject'] != 'pai':
                raise ValueError('Probe requires an existing corrected symbolic curriculum.')
            at = agent.native.moments.traces[0]['acquired_at']
            before = learned_digest(agent, mind)
            counts = (agent.native.observations, len(agent.native.moments.traces), len(agent.native.interpretations.records))
        finally:
            close_agent(agent, mind)
        output.mkdir(parents=True, exist_ok=False)
        shutil.copytree(source.root, output / 'runtime', ignore=shutil.ignore_patterns('lease.lock', 'stop.request'))
    window = f' pela imagem no intervalo [{max(0., at-.01):.6f}; {at+.01:.6f}]?'
    questions = [('Qual a informação atual de "maruvi" sobre "autor" pela imagem?', 'ambiguous'),
                 ('Qual a primeira informação de "maruvi" sobre "autor"' + window, 'initial'),
                 ('Qual a informação atual de "maruvi" sobre "autor"' + window, 'current'),
                 ('O que mudou em "maruvi" sobre "autor"' + window, 'comparison'),
                 ('Qual a informação atual de "maruvi" sobre "fenvori"' + window, 'unknown')]
    report = {'accepted': False, 'scope': 'literal questions about learned symbolic reports, not open dialogue or scene-author recognition',
              'stages': [], 'answers': [], 'source_counts': list(counts)}
    try:
        for question, expected in questions:
            report['stages'].append(run(output / 'runtime', seconds=seconds, question=question, question_mode='meaning',
                language_endpoint='http://127.0.0.1:11438', language_model='qwen3.5:0.8b-q8_0'))
            with RuntimeStore(output / 'runtime') as store:
                agent, mind, _ = load_scheduler(store.candidates()[0][0])
                try:
                    jobs = list(agent.native_meaning_queries.jobs)
                    if len(jobs) != 1:
                        raise ValueError('Expected exactly one meaning question.')
                    answer = agent.take_native_meaning_answer(jobs[0])
                    if answer is None or answer['status'] != 'completed':
                        raise ValueError('Preserve this runtime for pending/failed query inspection: ' + str(answer))
                    evidence = answer['evidence']
                    if expected == 'ambiguous':
                        if evidence['sensory']['reason'] != 'ambiguous_moments' or evidence['reports']:
                            raise ValueError('Relation availability selected an ambiguous moment.')
                    elif expected == 'unknown':
                        if evidence['reports']['current']['supported']:
                            raise ValueError('Unknown relation acquired invented meaning.')
                    else:
                        views = ['initial', 'current'] if expected == 'comparison' else [expected]
                        for view in views:
                            result = evidence['reports'][view]
                            if result['subject'] != ('pai' if view == 'initial' else 'mae') or result['directly_observed']:
                                raise ValueError('Initial/current meaning or reported status changed.')
                    if learned_digest(agent, mind) != before or counts != (agent.native.observations, len(agent.native.moments.traces), len(agent.native.interpretations.records)):
                        raise ValueError('Question altered learned state or created experience.')
                    report['answers'].append(answer)
                    for _ in range(2):
                        store.submit(store.capture(agent), agent.clock)
                        if store.finish()['status'] != 'committed':
                            raise ValueError('Answer acknowledgement was not persisted.')
                finally:
                    close_agent(agent, mind)
        report.update(accepted=True, learned_digest_preserved=before)
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)[:2048]
        raise
    finally:
        atomic_json(output / 'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=30.)
    args = parser.parse_args()
    result = probe(args.source_runtime, args.output, args.seconds)
    print({'accepted': result['accepted'], 'answers': len(result['answers']), 'counts': result['source_counts']})


if __name__ == '__main__':
    main()
