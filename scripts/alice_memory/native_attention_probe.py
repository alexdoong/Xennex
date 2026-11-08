"""Finite real file trial of attention allocation and externally graded feedback."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import torch

from .continuous_experiment import load_scheduler
from .importance import Consequence
from .native_inbox import NativeInbox
from .persistent_runtime import close_agent, run
from .reactivation_index import source_digest
from .runtime_store import RuntimeStore, RuntimeLease, atomic_json


def probe(source_runtime, source_inbox, output, image, audio, models, interpreter, seconds=120.):
    destination = output.resolve()
    if output.exists() or not 30 <= seconds <= 240:
        raise ValueError('Attention trial needs a fresh output and finite duration.')
    for path in (source_runtime, source_inbox):
        if destination == path.resolve() or path.resolve() in destination.parents:
            raise ValueError('Attention trial cannot overwrite or nest in its source.')
    torch.set_num_threads(1)
    with RuntimeStore(source_runtime) as source:
        agent, mind, _ = load_scheduler(source.candidates()[0][0])
        try:
            if agent.native.attention.sources or agent.native_stream.jobs:
                raise ValueError('Attention trial needs a new policy and empty frame queue.')
            before = {'frames': len(agent.native.moments.traces), 'observations': agent.native.observations,
                      'received': agent.native.received_observations, 'predicted_frames': agent.native.dynamics.frames,
                      'names': agent.native.names.copy(), 'versions': len(agent.native.interpretations.records)}
            old_banks = [source_digest(block).clone() for block in mind.actor.session.memory.blocks]
        finally:
            close_agent(agent, mind)
        output.mkdir(parents=True, exist_ok=False)
        shutil.copytree(source.root, output / 'runtime', ignore=shutil.ignore_patterns('lease.lock', 'stop.request'))
    with RuntimeLease(source_inbox.resolve() / 'producer'):
        shutil.copytree(source_inbox, output / 'inbox', ignore=shutil.ignore_patterns('lease.lock', 'stop.request'))
    inbox = NativeInbox(output / 'inbox')
    published = [inbox.publish({'image': image, 'audio': audio}, None, 'environment') for _ in range(4)]
    choices = []
    def feedback(event, now):
        # This curriculum supplies consequences; it is not an assertion of
        # true usefulness, personality or subjective preference.
        choice = event['attention']
        choices.append(event)
        benefit, effort = {'image': (.8, .1), 'audio': (.6, .1), 'all': (.4, .8), 'quiet': (.3, 0.)}[choice['action']]
        return Consequence(choice['id'], now, benefit, 0., effort)
    report = {'accepted': False, 'scope': 'repeated public files, supplied exploration/actions/utility and scripted external consequences',
              'before': before, 'published': published}
    try:
        report['runtime'] = run(output / 'runtime', seconds=seconds, native_inbox=inbox.root,
            native_models=models, native_interpreter=interpreter, native_ram_fraction=.9,
            native_attention='learned', native_feedback=feedback)
        if [event['attention']['action'] for event in choices] != ['image', 'audio', 'all', 'quiet']:
            raise ValueError('Keep the copied runtime/inbox for inspection; finite attention trial is incomplete.')
        with RuntimeStore(output / 'runtime') as store:
            agent, mind, _ = load_scheduler(store.candidates()[0][0])
            try:
                native = agent.native
                if native.received_observations != before['received'] + 8 or native.observations != before['observations'] + 4 or len(native.moments.traces) != before['frames'] + 3 or native.dynamics.frames != before['predicted_frames'] + 3:
                    raise ValueError('Unattended modalities entered acquisition or predictions.')
                if native.names != before['names'] or len(native.interpretations.records) != before['versions']:
                    raise ValueError('Attention trial invented names or interpretation reports.')
                if len(native.attention.sources) != 4 or native.attention.pending or sum(int(bank.writes) for bank in native.attention.banks.values()) != 4:
                    raise ValueError('Actual externally sourced consequences did not train their attention actions.')
                expected = ([True, False, False], [False, True, False], [True, True, False])
                for trace, known in zip(native.moments.traces[before['frames']:], expected):
                    if trace['known'] != known:
                        raise ValueError('Available channels were confused with attended memory.')
                if len(old_banks) != len(mind.actor.session.memory.blocks) or any(not torch.equal(value, source_digest(block)) for value, block in zip(old_banks, mind.actor.session.memory.blocks)):
                    raise ValueError('Attention acquisition changed older episodic weights.')
                before_feedback = len(native.attention.sources)
                agent.tick(5.)
                if len(native.attention.sources) != before_feedback:
                    raise ValueError('Quiet time generated fictitious attention feedback.')
                for _ in range(2):
                    store.submit(store.capture(agent), agent.clock)
                    if store.finish()['status'] != 'committed':
                        raise ValueError('Attention state could not be durably published.')
                report.update(choices=choices, received_delta=8, attended_delta=4, moments_delta=3,
                    feedback_sources=len(native.attention.sources), old_banks_preserved=len(old_banks),
                    native_format=native.snapshot()['format'], idle_feedback_preserved=True)
            finally:
                close_agent(agent, mind)
        report['accepted'] = True
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)[:2048]
        raise
    finally:
        atomic_json(output / 'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-runtime', 'source-inbox', 'output', 'image', 'audio', 'models', 'interpreter'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=120.)
    args = parser.parse_args()
    result = probe(args.source_runtime, args.source_inbox, args.output, args.image, args.audio, args.models, args.interpreter, args.seconds)
    print({key: result[key] for key in ('accepted', 'received_delta', 'attended_delta', 'feedback_sources')})


if __name__ == '__main__':
    main()
