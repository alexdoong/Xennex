"""Finite file perception trial across a deliberately small episodic capacity."""
from __future__ import annotations

import argparse
import copy
import shutil
from pathlib import Path

import torch

from .continuous_experiment import load_scheduler
from .native_inbox import NativeInbox
from .persistent_runtime import close_agent, run
from .reactivation_index import source_digest
from .runtime_store import RuntimeStore, RuntimeLease, atomic_json


def probe(source_runtime, source_inbox, output, image, audio, models, interpreter, seconds=120.):
    destination = output.resolve()
    if output.exists() or not 30 <= seconds <= 240:
        raise ValueError('Retention trial needs a fresh output and finite duration.')
    for path in (source_runtime, source_inbox):
        if destination == path.resolve() or path.resolve() in destination.parents:
            raise ValueError('Retention trial cannot overwrite or nest in its source.')
    torch.set_num_threads(1)
    with RuntimeStore(source_runtime) as source:
        output.mkdir(parents=True, exist_ok=False)
        shutil.copytree(source.root, output / 'runtime', ignore=shutil.ignore_patterns('lease.lock', 'stop.request'))
    with RuntimeLease(source_inbox.resolve() / 'producer'):
        shutil.copytree(source_inbox, output / 'inbox', ignore=shutil.ignore_patterns('lease.lock', 'stop.request'))
    with RuntimeStore(output / 'runtime') as store:
        agent, mind, _ = load_scheduler(store.candidates()[0][0])
        try:
            native, memory = agent.native, agent.native.moments
            count = len(memory.traces)
            if count < 4 or native_stream_pending(agent):
                raise ValueError('Retention trial needs retained history and no pending frames.')
            before = {'retained': count, 'lifetime': memory.next_id, 'observations': native.observations,
                      'received': native.received_observations, 'predicted_frames': native.dynamics.frames,
                      'names': native.names.copy(), 'versions': len(native.interpretations.records),
                      'attention_sources': len(native.attention.sources)}
            old_ids = {trace['id'] for trace in memory.traces}
            old_banks = [source_digest(block).clone() for block in mind.actor.session.memory.blocks]
            statements = copy.deepcopy(native.interpretations.records)
            memory.capacity = count
            memory.hot_limit = min(memory.hot_limit, count)
            memory.routes = memory.routes[:count].clone()
            store.submit(store.capture(agent), agent.clock)
            if store.finish()['status'] != 'committed':
                raise ValueError('Could not publish bounded trial archive.')
        finally:
            close_agent(agent, mind)
    inbox = NativeInbox(output / 'inbox')
    published = [inbox.publish({'image': image, 'audio': audio}, None, 'environment') for _ in range(4)]
    report = {'accepted': False, 'scope': 'repeated public files; supplied retention heuristic, reduced capacity only in copied trial',
              'before': before, 'published': published}
    try:
        report['runtime'] = run(output / 'runtime', seconds=seconds, native_inbox=inbox.root,
            native_models=models, native_interpreter=interpreter, native_ram_fraction=.9, native_attention='full')
        with RuntimeStore(output / 'runtime') as store:
            agent, mind, _ = load_scheduler(store.candidates()[0][0])
            try:
                native, memory = agent.native, agent.native.moments
                if native_stream_pending(agent) or memory.next_id != before['lifetime'] + 4 or len(memory.traces) != before['retained']:
                    raise ValueError('Finite trial did not acquire every new frame at bounded capacity.')
                if native.received_observations != before['received'] + 8 or native.observations != before['observations'] + 8 or native.dynamics.frames != before['predicted_frames'] + 4:
                    raise ValueError('Retention stopped perception or predictive learning.')
                if native.names != before['names'] or native.interpretations.records != statements or len(native.attention.sources) != before['attention_sources']:
                    raise ValueError('Retention invented a lesson, report or attention feedback.')
                if len(old_banks) != len(mind.actor.session.memory.blocks) or any(not torch.equal(value, source_digest(block)) for value, block in zip(old_banks, mind.actor.session.memory.blocks)):
                    raise ValueError('Retention changed older synthetic learned weights.')
                kept = {trace['id'] for trace in memory.traces}
                forgotten = sorted(old_ids - kept)
                if not forgotten or any(memory.get(moment) is not None for moment in forgotten):
                    raise ValueError('Trial did not retire an old episode or reused its identity.')
                if statements:
                    moment = statements[0]['moment']
                    report['first_report'] = {'moment': moment, 'sensory_retained': memory.get(moment) is not None,
                        'initial': native.interpret(moment, 'autor', 'initial')['subject'],
                        'current': native.interpret(moment, 'autor')['subject']}
                for _ in range(2):
                    store.submit(store.capture(agent), agent.clock)
                    if store.finish()['status'] != 'committed':
                        raise ValueError('Could not commit final retained history.')
                report.update(retained=len(memory.traces), lifetime=memory.next_id, forgotten=forgotten,
                    received_delta=8, attended_delta=8, old_banks_preserved=len(old_banks),
                    predicted_frames=native.dynamics.frames, predicted_pairs=native.dynamics.pairs,
                    native_format=native.snapshot()['format'], moment_format=memory.snapshot()['format'])
            finally:
                close_agent(agent, mind)
        report['accepted'] = True
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)[:2048]
        raise
    finally:
        atomic_json(output / 'report.json', report)
    return report


def native_stream_pending(agent):
    return any(job['status'] not in ('completed', 'ignored', 'failed') for job in agent.native_stream.jobs.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-runtime', 'source-inbox', 'output', 'image', 'audio', 'models', 'interpreter'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=120.)
    args = parser.parse_args()
    result = probe(args.source_runtime, args.source_inbox, args.output, args.image, args.audio, args.models, args.interpreter, args.seconds)
    print({key: result[key] for key in ('accepted', 'retained', 'lifetime', 'forgotten')})


if __name__ == '__main__':
    main()
