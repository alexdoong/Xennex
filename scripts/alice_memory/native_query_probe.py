"""Finite real-media/name/query curriculum on a copy of an existing runtime.

Uses a supplied local language host, cached native model and public input files.
Never mutates the source runtime/inbox or starts a camera/microphone/service.
"""
from __future__ import annotations

import argparse
import copy
import json
import shutil
from pathlib import Path
from uuid import uuid4

import torch

from .continuous_experiment import load_scheduler
from .native_inbox import NativeInbox
from .persistent_runtime import close_agent, run
from .reactivation_index import source_digest
from .runtime_store import RuntimeStore, RuntimeLease, atomic_json


def collect_answers(root):
    with RuntimeStore(root) as store:
        agent, mind, _ = load_scheduler(store.candidates()[0][0])
        try:
            results = []
            for number in list(agent.native_queries.jobs):
                answer = agent.take_native_answer(number)
                if answer is None:
                    raise ValueError('Finite native query remains pending; resume this runtime.')
                if answer['status'] != 'completed':
                    raise ValueError('Native query failed: ' + str(answer['error']))
                results.append(answer)
            for _ in range(2):
                store.submit(store.capture(agent), agent.clock)
                if store.finish()['status'] != 'committed':
                    raise ValueError('Could not persist native question acknowledgement.')
            return results
        finally:
            close_agent(agent, mind)


def probe(source_runtime, source_inbox, output, image, audio, models, interpreter, *, name='maruvi',
          endpoint='http://127.0.0.1:11438', model='qwen3.5:0.8b-q8_0', seconds=45., encoder_seconds=120., ram_fraction=.75,
          resume=False):
    if type(resume) is not bool or (output.exists() and not resume) or (resume and not output.exists()) or not 5 <= seconds <= 120 or not 10 <= encoder_seconds <= 240:
        raise ValueError('Probe requires a new output and bounded stages.')
    destination = output.resolve()
    for original in (source_runtime.resolve(), source_inbox.resolve()):
        if destination == original or original in destination.parents:
            raise ValueError('Probe output cannot be nested inside its source.')
    torch.set_num_threads(1)
    # Hold the source runtime lease through the copy; an active owner is rejected.
    with RuntimeStore(source_runtime) as source:
        path = source.candidates()[0][0]
        agent, mind, _ = load_scheduler(path)
        try:
            if name in agent.native.names or len(agent.native.moments.traces) != 2:
                raise ValueError('Curriculum expects two existing unnamed matching moments.')
            first_at = agent.native.moments.traces[0]['acquired_at']
            old_banks = [source_digest(block).clone() for block in mind.actor.session.memory.blocks]
            old_observations = agent.temporal.observations
            old_concepts = copy.deepcopy(agent.concepts.snapshot())
        finally:
            close_agent(agent, mind)
        if not resume:
            output.mkdir(parents=True, exist_ok=False)
            shutil.copytree(source.root, output / 'runtime', ignore=shutil.ignore_patterns('lease.lock', 'stop.request'))
    # Preserve provider UUID/counters so relocation doesn't invent a new stream.
    if not resume:
        with RuntimeLease(source_inbox.resolve() / 'producer'):
            shutil.copytree(source_inbox, output / 'inbox', ignore=shutil.ignore_patterns('lease.lock', 'stop.request'))
    runtime, inbox = output / 'runtime', NativeInbox(output / 'inbox')
    question = 'Alice, você lembra de "' + name + '" pela imagem?'
    reports, answers = [], []
    prior_failures = []
    if resume:
        with RuntimeStore(runtime) as store:
            agent, mind, _ = load_scheduler(store.candidates()[0][0])
            try:
                if agent.native.names or len(agent.native.moments.traces) != 2 or agent.native_stream.jobs:
                    raise ValueError('Resume currently accepts a failed baseline before publishing new inputs.')
                if any(job['status'] not in ('failed', 'uncertain') for job in agent.native_queries.jobs.values()):
                    raise ValueError('Preserve pending/completed queries; this resume only acknowledges baseline failures.')
                for number in list(agent.native_queries.jobs):
                    prior_failures.append(agent.take_native_answer(number))
                for _ in range(2):
                    store.submit(store.capture(agent), agent.clock)
                    if store.finish()['status'] != 'committed':
                        raise ValueError('Failed to preserve baseline acknowledgement.')
            finally:
                close_agent(agent, mind)
    report_path = output / ('report-resume-' + uuid4().hex + '.json' if resume else 'report.json')
    report = {'accepted': False, 'stages': reports, 'answers': answers,
              'resumed': resume, 'prior_failures': prior_failures,
              'scope': 'same public photo/audio repeated; bounded factual phrasing, not open Portuguese scene understanding'}
    try:
        reports.append(run(runtime, seconds=seconds, question=question, question_mode='native',
                           language_endpoint=endpoint, language_model=model))
        answers.extend(collect_answers(runtime))
        if answers[-1]['evidence']['reason'] != 'unlearned_native_meaning':
            raise ValueError('Pretrained language must not invent the unseen name association.')
        published = inbox.publish({'image': image, 'audio': audio}, name, 'person')
        report['published'] = published
        reports.append(run(runtime, seconds=encoder_seconds, native_inbox=inbox.root, native_models=models,
                           native_interpreter=interpreter, native_ram_fraction=ram_fraction))
        if reports[-1]['native_state']['names'] != [name] or reports[-1]['native_state']['moments'] != 3:
            raise ValueError('Finite native encoding/name lesson incomplete; resume this same copied state.')
        reports.append(run(runtime, seconds=seconds, question=question, question_mode='native'))
        answers.extend(collect_answers(runtime))
        if answers[-1]['evidence']['reason'] != 'ambiguous_moments' or answers[-1]['evidence']['candidate_count'] != 3:
            raise ValueError('Repeated content cannot silently select the newest memory.')
        timed = question[:-1] + f' no intervalo [{max(0., first_at-.01):.6f}; {first_at+.01:.6f}]?'
        reports.append(run(runtime, seconds=seconds, question=timed, question_mode='native'))
        answers.extend(collect_answers(runtime))
        if not answers[-1]['evidence']['supported'] or answers[-1]['evidence']['moment_id'] != 0 or answers[-1]['evidence']['modalities'] != ['image', 'audio']:
            raise ValueError('New name association failed to evoke the older unnamed moment.')
        unknown = 'Lembra de "fenvori" pela imagem?'
        reports.append(run(runtime, seconds=seconds, question=unknown, question_mode='native'))
        answers.extend(collect_answers(runtime))
        if answers[-1]['evidence']['reason'] != 'unlearned_native_meaning':
            raise ValueError('Unknown native name acquired unsupported meaning.')
        with RuntimeStore(runtime) as store:
            agent, mind, _ = load_scheduler(store.candidates()[0][0])
            try:
                assert len(old_banks) == len(mind.actor.session.memory.blocks) == 384
                assert all(torch.equal(value, source_digest(block)) for value, block in zip(old_banks, mind.actor.session.memory.blocks))
                assert agent.temporal.observations == old_observations
                assert agent.concepts.sources == old_concepts['sources']
                report.update(accepted=True, old_banks_preserved=384, observations=agent.native.observations,
                              names=agent.native.names, moments=len(agent.native.moments.traces))
            finally:
                close_agent(agent, mind)
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)[:2048]
        raise
    finally:
        atomic_json(report_path, report)
        atomic_json(output / 'latest-probe.json', {'format': 1, 'file': report_path.name, 'accepted': report['accepted']})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('source-runtime', 'source-inbox', 'output', 'image', 'audio', 'models', 'interpreter'):
        parser.add_argument('--' + field, type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=45.)
    parser.add_argument('--encoder-seconds', type=float, default=120.)
    parser.add_argument('--ram-fraction', type=float, default=.75)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    result = probe(args.source_runtime, args.source_inbox, args.output, args.image, args.audio, args.models, args.interpreter,
                   seconds=args.seconds, encoder_seconds=args.encoder_seconds, ram_fraction=args.ram_fraction, resume=args.resume)
    print({key: result[key] for key in ('accepted', 'old_banks_preserved', 'observations', 'moments', 'names')})


if __name__ == '__main__':
    main()
