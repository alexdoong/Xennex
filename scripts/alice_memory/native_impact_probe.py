"""Finite live file-pipeline trial of consequence values, memory impact and affect."""
from __future__ import annotations

import argparse
import copy
import math
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
        raise ValueError('Impact trial needs a fresh output and finite duration.')
    for path in (source_runtime, source_inbox):
        if destination == path.resolve() or path.resolve() in destination.parents:
            raise ValueError('Impact trial cannot overwrite or nest in its source.')
    torch.set_num_threads(1)
    with RuntimeStore(source_runtime) as source:
        agent, mind, _ = load_scheduler(source.candidates()[0][0])
        try:
            if agent.native_stream.jobs or agent.native.attention.pending:
                raise ValueError('Impact trial needs an idle frame queue and no pending feedback.')
            native = agent.native
            before = {'lifetime': native.moments.next_id, 'observations': native.observations,
                      'received': native.received_observations, 'names': native.names.copy(),
                      'versions': len(native.interpretations.records), 'feedback': len(native.attention.sources),
                      'progress': mind.internal.progress, 'social': mind.internal.social}
            original_reports = copy.deepcopy(native.interpretations.records)
            old_banks = [source_digest(block).clone() for block in mind.actor.session.memory.blocks]
        finally:
            close_agent(agent, mind)
        output.mkdir(parents=True, exist_ok=False)
        shutil.copytree(source.root, output / 'runtime', ignore=shutil.ignore_patterns('lease.lock', 'stop.request'))
    with RuntimeLease(source_inbox.resolve() / 'producer'):
        shutil.copytree(source_inbox, output / 'inbox', ignore=shutil.ignore_patterns('lease.lock', 'stop.request'))
    inbox = NativeInbox(output / 'inbox')
    published = [inbox.publish({'image': image, 'audio': audio}, None, 'environment') for _ in range(4)]
    rewards = {'image': (.8, .2, .1), 'audio': (-.6, -.2, .1), 'all': (.4, .1, .4), 'quiet': (.3, 0., 0.)}
    choices = []
    def feedback(event, now):
        choice = event['attention']
        choices.append(copy.deepcopy(choice))
        benefit, social, effort = rewards[choice['action']]
        return Consequence(choice['id'], now, benefit, social, effort)
    report = {'accepted': False, 'scope': 'repeated public files and scripted external consequences; supplied salience/utility/decay',
              'before': before, 'published': published}
    try:
        report['runtime'] = run(output / 'runtime', seconds=seconds, native_inbox=inbox.root,
            native_models=models, native_interpreter=interpreter, native_ram_fraction=.9,
            native_attention='learned', native_feedback=feedback)
        if [choice['action'] for choice in choices] != ['image', 'audio', 'all', 'quiet']:
            raise ValueError('Finite impact trial is incomplete; preserve copied files for inspection.')
        with RuntimeStore(output / 'runtime') as store:
            agent, mind, _ = load_scheduler(store.candidates()[0][0])
            try:
                native, memory = agent.native, agent.native.moments
                if native.observations != before['observations'] + 4 or native.received_observations != before['received'] + 8 or memory.next_id != before['lifetime'] + 3:
                    raise ValueError('Feedback created extra perceptions or missed attended channels.')
                if native.names != before['names'] or native.interpretations.records != original_reports:
                    raise ValueError('Consequence feedback changed names or reported facts.')
                if native.attention.pending or len(native.attention.sources) != before['feedback'] + 4:
                    raise ValueError('Feedback was not credited exactly once per decision.')
                learned = []
                for source in native.attention.sources[-4:]:
                    if source['action'] == 'quiet':
                        if source['moment_ref'] is not None:
                            raise ValueError('Quiet consequence invented a sensory moment.')
                        continue
                    trace = memory.get(source['moment_ref']['id'])
                    if trace is None or trace['impact'] is None or trace['impact']['id'] != source['id']:
                        raise ValueError('Actual consequence lost its attended episode.')
                    slot = memory.slot(trace['id'])
                    value = memory.values.read(slot)
                    benefit, social, effort = rewards[source['action']]
                    expected = (benefit + .5 * social - .25 * effort) * (1000. / 1000.1)
                    if abs(value['value'] - expected) > 1e-8:
                        raise ValueError('Episode value did not come from its actual consequence.')
                    learned.append({'moment': trace['id'], 'action': source['action'], 'value': value['value'],
                                    'impact': value['impact'], 'known': trace['known']})
                if len(learned) != 3 or int(memory.values.updates.sum()) != 3:
                    raise ValueError('Impact trial wrote a missing, duplicate or historical value.')
                progress, social = before['progress'], before['social']
                for choice in choices:
                    benefit, contact, effort = rewards[choice['action']]
                    progress, social = .8 * progress + .2 * benefit, .8 * social + .2 * contact
                expected_valence = math.tanh(progress + .5 * social)
                if abs(mind.internal.progress - progress) > 1e-9 or abs(mind.internal.social - social) > 1e-9 or abs(mind.internal.valence - expected_valence) > 1e-9:
                    raise ValueError('Native consequences did not reach shared functional state.')
                if len(old_banks) != len(mind.actor.session.memory.blocks) or any(not torch.equal(value, source_digest(block)) for value, block in zip(old_banks, mind.actor.session.memory.blocks)):
                    raise ValueError('Consequence learning changed older synthetic episode weights.')
                weights = memory.values.weights.clone()
                agent.tick(5.)
                if not torch.equal(weights, memory.values.weights):
                    raise ValueError('Idle time generated fictitious consequence training.')
                for _ in range(2):
                    store.submit(store.capture(agent), agent.clock)
                    if store.finish()['status'] != 'committed':
                        raise ValueError('Could not publish impact values and their sources.')
                report.update(choices=choices, learned=learned, quiet_has_no_episode=True,
                    attended_delta=4, received_delta=8, feedback_delta=4, impact_writes=3,
                    old_banks_preserved=len(old_banks), shared_valence=mind.internal.valence,
                    shared_progress=mind.internal.progress, shared_social=mind.internal.social,
                    lifetime=memory.next_id, retained=len(memory.traces), moment_format=memory.snapshot()['format'])
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
    print({name: result[name] for name in ('accepted', 'impact_writes', 'shared_valence')})


if __name__ == '__main__':
    main()
