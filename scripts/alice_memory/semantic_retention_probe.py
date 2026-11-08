"""Finite synthetic retention trial plus optional real checkpoint migration.

Reserved directions are graded externally. The curriculum, retention rule and
accelerated virtual time are supplied; this is not everyday conceptual learning.
"""
import argparse
import copy
from pathlib import Path

import torch
from torch.nn import functional as F

from .native_links import NativeLinks, restore as restore_links
from .native_sensor import NativeObservation
from .runtime_store import atomic_json, digest


def observation(modality, basis, detail, now, sequence):
    return NativeObservation(modality, F.normalize(basis[:, 0] + detail * basis[:, 1], dim=0),
                             now, sequence, 'a' * 64)


def trial(seed, output):
    generator = torch.Generator().manual_seed(seed)
    image, audio = (torch.linalg.qr(torch.randn(128, 128, generator=generator)).Q for _ in range(2))
    fading = NativeLinks(retention_seconds=10.)
    control = NativeLinks(retention_seconds=1e12)
    for index, detail in enumerate([.3, -.3] + [0.] * 32):
        now = 1. + index * .001
        inputs = [observation('image', image, detail, now, index), observation('audio', audio, detail, now, index)]
        fading.observe(inputs, now)
        control.observe(inputs, now)
    cue = observation('image', image, .1, fading.clock, 0)
    before = fading.predict(cue, 'audio')
    initial = fading.snapshot()
    fading.advance(301.033)
    control.advance(301.033)
    partial = fading.predict(cue, 'audio')
    unfaded = control.predict(cue, 'audio')
    inaccessible = fading.predict(observation('image', image, .3, fading.clock, 0), 'audio')
    resumed = restore_links(fading.snapshot(), fading.clock, fading.frames)
    restart_equal = torch.equal(resumed.predict(cue, 'audio')['latent'], partial['latent'])
    idle_writes = int(fading.banks['image:audio'].writes) == int(initial['banks']['image:audio']['writes'])
    lesson = [observation('image', image, .3, 302., 34), observation('audio', audio, .3, 302., 34)]
    fading.observe(lesson, 302.)
    cold = NativeLinks(retention_seconds=10.)
    cold.observe(lesson, 302.)
    reserved = observation('image', image, -.2, 302., 0)
    target = observation('audio', audio, -.2, 302., 0).latent
    warm = fading.predict(reserved, 'audio')
    cold_result = cold.predict(reserved, 'audio')
    result = {'seed': seed, 'initial_detail': float(before['latent'] @ audio[:, 1]),
        'remaining_detail': float(partial['latent'] @ audio[:, 1]),
        'reinforced_component': float(partial['latent'] @ audio[:, 0]),
        'control_detail': float(unfaded['latent'] @ audio[:, 1]),
        'inaccessible_supported': inaccessible['supported'], 'inaccessible_familiarity': inaccessible['familiarity'],
        'warm_reserved_cosine': float(warm['latent'] @ target) if warm['supported'] else None,
        'cold_reserved_supported': cold_result['supported'], 'restart_equal': restart_equal, 'idle_no_training': idle_writes,
        'reserved_detail': -.2, 'reserved_detail_ever_taught': False}
    result['accepted'] = (result['initial_detail'] > .09 and abs(result['remaining_detail']) < .001
        and result['reinforced_component'] > .999 and result['control_detail'] > .09
        and not inaccessible['supported'] and inaccessible['familiarity'] > .9
        and warm['supported'] and result['warm_reserved_cosine'] > .999 and not cold_result['supported']
        and restart_equal and idle_writes)
    torch.save({'format': 1, 'links': fading.snapshot(), 'image_basis': image, 'audio_basis': audio}, output / f'seed{seed}.pt')
    return result


def migrate(checkpoint, output):
    from .conceptual_mind import save
    from .continuous_experiment import load_scheduler
    from .persistent_runtime import close_agent
    from .reactivation_index import source_digest
    from .runtime_store import RuntimeStore
    source_hash = digest(checkpoint)
    def forbidden(operation):
        raise AssertionError('Checkpoint retention audit must not start a model worker.')
    core, mind, _ = load_scheduler(checkpoint, worker_factory=forbidden)
    try:
        native = core.native
        original = copy.deepcopy(native.links.snapshot())
        anchors = copy.deepcopy(native.links.updated_at)
        names, sources = native.names.copy(), copy.deepcopy(native.sources)
        reports = copy.deepcopy(native.interpretations.records)
        banks = [source_digest(block).clone() for block in mind.actor.session.memory.blocks]
        for _ in range(50):
            core.tick(.1)
        assert native.names == names and native.sources == sources and native.interpretations.records == reports
        assert native.links.updated_at == anchors and native.links.frames == original['frames']
        assert all(torch.equal(value, source_digest(block)) for value, block in zip(banks, mind.actor.session.memory.blocks))
        save(output / 'portable.pt', core)
        with RuntimeStore(output / 'runtime') as store:
            for _ in range(2):
                store.submit(store.capture(core), core.clock)
                if store.finish()['status'] != 'committed':
                    raise ValueError('Could not commit semantic retention anchors.')
            paged = [store.path(store.manifest[version]['file']) for version in ('current', 'previous')]
        reopened = []
        try:
            for path in (output / 'portable.pt', *paged):
                restored, restored_mind, _ = load_scheduler(path, worker_factory=forbidden)
                reopened.append((restored, restored_mind))
                assert restored.native.links.snapshot()['format'] == 3
                assert restored.native.links.updated_at == anchors
                assert restored.native.links.frames == original['frames']
                for group in ('banks', 'contextual_banks'):
                    for pair, state in original[group].items():
                        for name, tensor in state.items():
                            assert torch.equal(tensor, getattr(restored.native.links, group)[pair].state_dict()[name])
            assert digest(checkpoint) == source_hash
            return {'accepted': True, 'checkpoint_restarts': 3, 'legacy_weights_preserved': True,
                    'synthetic_banks_preserved': len(banks), 'native_observations': native.observations,
                    'retention_anchor_reheating': False, 'source_sha256': source_hash}
        finally:
            for restored, restored_mind in reopened:
                close_agent(restored, restored_mind)
    finally:
        close_agent(core, mind)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--checkpoint', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(1)
    report = {'accepted': False, 'scope': 'supplied retention law; synthetic unnamed associations; accelerated virtual time',
              'live_sensors': False, 'model_loaded': False, 'retention_seconds_trial': 10., 'virtual_gap_seconds': 300.}
    try:
        report['trials'] = [trial(seed, args.output) for seed in (17, 29, 71)]
        report['checkpoint_migration'] = migrate(args.checkpoint, args.output) if args.checkpoint else None
        report['accepted'] = all(result['accepted'] for result in report['trials'])
    finally:
        atomic_json(args.output / 'report.json', report)
    print(report)
    raise SystemExit(0 if report['accepted'] else 1)


if __name__ == '__main__':
    main()
