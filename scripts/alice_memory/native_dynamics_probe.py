"""Finite file-perception trial; old history is retained without replay training."""
from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path

import torch
from torch.nn import functional as F

from .continuous_experiment import load_scheduler
from .native_inbox import NativeInbox
from .persistent_runtime import close_agent, run
from .reactivation_index import source_digest
from .runtime_store import RuntimeStore, RuntimeLease, atomic_json


def probe(source_runtime, source_inbox, output, image, audio, models, interpreter, seconds=180.):
    destination = output.resolve()
    if output.exists() or not 30 <= seconds <= 240:
        raise ValueError('Native dynamics trial needs a fresh destination and finite duration.')
    for path in (source_runtime, source_inbox):
        if destination == path.resolve() or path.resolve() in destination.parents:
            raise ValueError('Trial cannot overwrite or nest in its source.')
    torch.set_num_threads(1)
    with RuntimeStore(source_runtime) as source:
        agent, mind, _ = load_scheduler(source.candidates()[0][0])
        try:
            if agent.native.dynamics.frames or agent.native_stream.jobs:
                raise ValueError('Trial needs old history with a newly initialized predictor and empty sensor queue.')
            old_frames = len(agent.native.moments.traces)
            old_observations = agent.native.observations
            old_banks = [source_digest(block).clone() for block in mind.actor.session.memory.blocks]
            old_names = agent.native.names.copy()
            old_versions = len(agent.native.interpretations.records)
        finally:
            close_agent(agent, mind)
        output.mkdir(parents=True, exist_ok=False)
        shutil.copytree(source.root, output / 'runtime', ignore=shutil.ignore_patterns('lease.lock', 'stop.request'))
    with RuntimeLease(source_inbox.resolve() / 'producer'):
        shutil.copytree(source_inbox, output / 'inbox', ignore=shutil.ignore_patterns('lease.lock', 'stop.request'))
    inbox = NativeInbox(output / 'inbox')
    published = [inbox.publish({'image': image, 'audio': audio}, None, 'environment') for _ in range(6)]
    report = {'accepted': False, 'scope': 'six new captures of repeated public files, not new scenes or general world understanding',
              'published': published, 'old_frames': old_frames}
    try:
        report['runtime'] = run(output / 'runtime', seconds=seconds, native_inbox=inbox.root,
            native_models=models, native_interpreter=interpreter, native_ram_fraction=.9)
        with RuntimeStore(output / 'runtime') as store:
            agent, mind, _ = load_scheduler(store.candidates()[0][0])
            try:
                dynamics = agent.native.dynamics
                if agent.native_stream.jobs or dynamics.frames != 6 or dynamics.pairs != 5:
                    raise ValueError('Keep this runtime/inbox for inspection and resume; the finite trial is incomplete.')
                if agent.native.observations != old_observations + 12 or len(agent.native.moments.traces) != old_frames + 6 or agent.native.names != old_names or len(agent.native.interpretations.records) != old_versions:
                    raise ValueError('Unlabeled experience changed names/reports or lost perceptions.')
                if len(old_banks) != len(mind.actor.session.memory.blocks) or any(not torch.equal(previous, source_digest(block)) for previous, block in zip(old_banks, mind.actor.session.memory.blocks)):
                    raise ValueError('Native prediction altered earlier episodic weights.')
                errors = dynamics.last_error
                if set(errors) != {'image', 'audio'} or max(errors.values()) > .01:
                    raise ValueError('Repeated actual percepts did not improve next-observation prediction.')
                key = dynamics.key()
                for slot, name in enumerate(('image', 'audio')):
                    predicted = F.normalize((dynamics.banks[name].weights @ key).float(), dim=0)
                    if float(predicted @ dynamics.last['values'][slot].float()) < .99:
                        raise ValueError('Freshly restored prediction disagrees with the repeated actual features.')
                before = {name: hashlib.sha256(bank.weights.numpy().tobytes()).hexdigest() for name, bank in dynamics.banks.items()}
                agent.tick(5.)
                if before != {name: hashlib.sha256(bank.weights.numpy().tobytes()).hexdigest() for name, bank in dynamics.banks.items()} or dynamics.frames != 6:
                    raise ValueError('Idle time created fictitious training.')
                for _ in range(2):
                    store.submit(store.capture(agent), agent.clock)
                    if store.finish()['status'] != 'committed':
                        raise ValueError('Restored temporal state could not be persisted.')
                report.update(frames=dynamics.frames, pairs=dynamics.pairs, errors=errors,
                    historical_frames=dynamics.historical_frames, old_banks_preserved=len(old_banks),
                    idle_weights_preserved=True, prediction_kind=dynamics.predict()['kind'],
                    context_age_reason=dynamics.predict()['reason'], native_format=agent.native.snapshot()['format'])
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
    parser.add_argument('--seconds', type=float, default=180.)
    args = parser.parse_args()
    result = probe(args.source_runtime, args.source_inbox, args.output, args.image, args.audio, args.models, args.interpreter, args.seconds)
    print({key: result[key] for key in ('accepted', 'frames', 'pairs', 'errors', 'idle_weights_preserved')})


if __name__ == '__main__':
    main()
