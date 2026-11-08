"""Read multiple real sensory memories without encoder, language calls or new experience."""
import argparse
import hashlib
from pathlib import Path

import torch

from .conceptual_mind import save
from .continuous_experiment import load_scheduler
from .native_sensor import NativeObservation
from .native_reactivation import activate
from .persistent_runtime import close_agent
from .runtime_store import atomic_json, digest


def tensor_digest(value):
    return hashlib.sha256(value.detach().cpu().contiguous().numpy().tobytes()).hexdigest()


def run(source, output, name):
    output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(1)
    checksum = digest(source)
    def forbidden(operation):
        raise AssertionError('Reactivation probe cannot invoke language or perception models.')
    core, mind, _ = load_scheduler(source, output / 'workers', forbidden)
    report = {'accepted': False, 'cue_origin': 'learned_name_weights', 'fresh_sensory_inference': False,
              'new_experience': False, 'model_called': False, 'source_sha256': checksum}
    try:
        native = core.native
        counts = native.observations, native.moments.next_id
        interpretation = native.interpretations.bank.weights.clone()
        names = native.names.copy()
        meaning = native.evoke(name, 'image')
        if not meaning['supported']:
            raise ValueError('Probe requires a previously learned visual cue.')
        cues = [NativeObservation('image', meaning['latent'], native.clock, 0, '0'*64, origin='self')]
        strict = native.moments.recall(cues, native.clock, reactivate=False)
        related = native.moments.related(cues, native.clock)
        entries = related['entries']
        if len(entries) != 2:
            raise ValueError('This probe requires two separately supported sensory recollections.')
        identifiers = [entry['candidate']['id'] for entry in entries]
        before = [native.moments.get(number)['recalls'] for number in identifiers]
        report.update(strict_reason=strict['reason'], recalled_ids=identifiers,
            representations=[{'moment': entry['candidate']['id'],
                'modalities': {key: tensor_digest(value) for key, value in entry['representations'].items()}}
                for entry in entries])
        saved = {number: native.moments.bank(number).outputs.clone() for number in identifiers}
        try:
            for number in identifiers: native.moments.bank(number).outputs.zero_()
            erased = native.moments.related(cues, native.clock)
            if erased['entries']:
                raise RuntimeError('Metadata substituted for erased sensory content.')
            report['no_content_from_metadata'] = True
        finally:
            for number in identifiers: native.moments.bank(number).outputs.copy_(saved[number])
        working = native.working.clone()
        native.configure_implicit_recall(True)
        activation = activate(native, cues, native.clock, None)
        if not activation['supported'] or torch.equal(native.working, working):
            raise RuntimeError('Recollection failed to influence working state.')
        if [native.moments.get(number)['recalls'] for number in identifiers] != [x + 1 for x in before]:
            raise RuntimeError('Recollection warmed sources more than once.')
        if (native.observations, native.moments.next_id) != counts or not torch.equal(native.interpretations.bank.weights, interpretation) or native.names != names:
            raise RuntimeError('Sensory reactivation invented experience or rewrote factual knowledge.')
        save(output / 'final.pt', core)
        fresh, fresh_mind, _ = load_scheduler(output / 'final.pt', output / 'fresh', forbidden)
        try:
            if not fresh.native.implicit_recall or not torch.equal(fresh.native.working, native.working):
                raise RuntimeError('Restore lost implicit mode or nonverbal working state.')
            recalled_counts = [trace['recalls'] for trace in fresh.native.moments.traces]
            fresh.tick(.1)
            if recalled_counts != [trace['recalls'] for trace in fresh.native.moments.traces]:
                raise RuntimeError('Idle tick repeatedly warmed the recollection.')
        finally:
            close_agent(fresh, fresh_mind)
        if digest(source) != checksum:
            raise RuntimeError('Probe rewrote the original source.')
        report.update(accepted=True, neural_working_state_changed=True, observations_unchanged=True,
                      factual_weights_unchanged=True, restart_verified=True, source_unchanged=True)
    finally:
        close_agent(core, mind)
        atomic_json(output / 'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--name', default='hami')
    args = parser.parse_args()
    result = run(args.checkpoint, args.output, args.name)
    print({'accepted': result['accepted'], 'model_called': False, 'new_experience': False})


if __name__ == '__main__':
    main()
