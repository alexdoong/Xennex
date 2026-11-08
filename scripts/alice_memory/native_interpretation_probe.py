"""Finite real-language revision curriculum on a copy of a native runtime.

The father/mother words are supplied symbolic reports about a moment. They are
not asserted as actual authors of the public image/audio recorded there.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import shutil
from pathlib import Path

import torch

from .continuous_experiment import load_scheduler
from .persistent_runtime import close_agent, run
from .reactivation_index import source_digest
from .runtime_store import RuntimeStore, atomic_json

MESSAGES = ('No momento 0, associe "autor" a "pai".',
            'Corrija o momento 0: "autor" passa a ser "mae"; substitua [0].',
            'Não associe no momento 0 "autor" a "tio".')


def senses(native):
    value = hashlib.sha256(native.moments.routes.numpy().tobytes())
    for index, digest in native.moments.connection.execute('SELECT id,digest FROM moments ORDER BY id'):
        value.update(str(index).encode())
        value.update(digest.encode())
    return value.hexdigest()


def probe(source_runtime, output, seconds=30.):
    if output.exists() or not 5 <= seconds <= 120 or source_runtime.resolve() in output.resolve().parents:
        raise ValueError('Interpretation probe requires a new output outside its source and finite stages.')
    torch.set_num_threads(1)
    with RuntimeStore(source_runtime) as source:
        agent, mind, _ = load_scheduler(source.candidates()[0][0])
        try:
            if not agent.native.moments.traces or agent.native.interpretations.records:
                raise ValueError('Probe expects existing perceptions with no interpretation versions.')
            previous = senses(agent.native)
            old_banks = [source_digest(block).clone() for block in mind.actor.session.memory.blocks]
            observed, native_observed = agent.temporal.observations, agent.native.observations
            concepts = copy.deepcopy(agent.concepts.snapshot())
            names = agent.native.names.copy()
        finally:
            close_agent(agent, mind)
        output.mkdir(parents=True, exist_ok=False)
        shutil.copytree(source.root, output / 'runtime', ignore=shutil.ignore_patterns('lease.lock', 'stop.request'))
    runtime = output / 'runtime'
    report = {'accepted': False, 'scope': 'literal externally supplied symbolic reports, not scene-author recognition',
              'stages': [], 'results': [], 'jobs': []}
    try:
        for index, message in enumerate(MESSAGES):
            report['stages'].append(run(runtime, seconds=seconds, native_statement=message,
                language_endpoint='http://127.0.0.1:11438', language_model='qwen3.5:0.8b-q8_0'))
            with RuntimeStore(runtime) as store:
                agent, mind, _ = load_scheduler(store.candidates()[0][0])
                try:
                    jobs = [agent.take_native_statement(number) for number in list(agent.native_statements.jobs)]
                    if not jobs or any(job is None for job in jobs):
                        raise ValueError('Finite statement remains pending; preserve and resume this state.')
                    report['jobs'].extend(jobs)
                    expected = 'completed' if index < 2 else 'uncertain'
                    if any(job['status'] != expected for job in jobs):
                        raise ValueError('Real statement parser failed: ' + str(jobs))
                    current = agent.native.interpret(0, 'autor')
                    initial = agent.native.interpret(0, 'autor', 'initial')
                    wanted = 'pai' if index == 0 else 'mae'
                    if current['subject'] != wanted or initial['subject'] != 'pai' or current['directly_observed']:
                        raise ValueError('Revision lost the reported current/initial distinction.')
                    report['results'].append({'current': current, 'initial': initial})
                    if senses(agent.native) != previous or agent.native.observations != native_observed or agent.native.names != names:
                        raise ValueError('Statement changed sensory state instead of its interpretation.')
                    if agent.temporal.observations != observed or len(old_banks) != len(mind.actor.session.memory.blocks) or any(not torch.equal(value, source_digest(block)) for value, block in zip(old_banks, mind.actor.session.memory.blocks)):
                        raise ValueError('Old episodic state changed during reported interpretation.')
                    if agent.concepts.sources != concepts['sources']:
                        raise ValueError('Concept teaching changed during native statement.')
                    for _ in range(2):
                        store.submit(store.capture(agent), agent.clock)
                        if store.finish()['status'] != 'committed':
                            raise ValueError('Statement acknowledgement persistence failed.')
                    report.update(versions=len(agent.native.interpretations.records), old_banks_preserved=len(old_banks),
                                  native_observations=native_observed, sensory_digest_preserved=previous)
                finally:
                    close_agent(agent, mind)
        if report['versions'] != 2:
            raise ValueError('Negated statement wrote an interpretation.')
        report['accepted'] = True
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
    print({key: result[key] for key in ('accepted', 'versions', 'old_banks_preserved', 'native_observations')})


if __name__ == '__main__':
    main()
