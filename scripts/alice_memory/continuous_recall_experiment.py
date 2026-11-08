"""Acquire every cue through observe while context and recall remain active."""
import argparse
import hashlib
import random
import time
from pathlib import Path

import torch
from torch.nn import functional as F

from .importance import Consequence
from .native_grounding import NativeGrounding, restore
from .native_sensor import NativeObservation
from .runtime_store import atomic_json


def run(output, seed=17):
    output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(1)
    generator = torch.Generator().manual_seed(seed)
    vectors = torch.linalg.qr(torch.randn(128, 8, generator=generator))[0].T.float()
    native = NativeGrounding(implicit_recall=True)
    started = time.monotonic()
    report = {'accepted': False, 'seed': seed, 'synthetic_perceptual_vectors': True,
              'external_cues_acquired': True, 'language_called': False,
              'training_feedbacks': 96, 'situation_interval': .2, 'cue_interval': .1}

    def observe(owner, pairs, elapsed):
        if time.monotonic() - started > 90:
            raise TimeoutError('Continuous recall exceeded its registered 90-second budget.')
        at = owner.clock + elapsed
        packets = [NativeObservation(modality, latent, at, owner.received_observations,
            hashlib.sha256(latent.numpy().tobytes()).hexdigest(), origin='environment')
            for modality, latent in pairs]
        return owner.observe(packets, at), packets

    def context(owner, place, topic, noisy=False):
        image, audio = vectors[place], vectors[2 + topic]
        if noisy:
            image = F.normalize(image + .005 * vectors[7], dim=0)
            audio = F.normalize(audio - .005 * vectors[7], dim=0)
        return observe(owner, [('image', image), ('audio', audio)], .2)

    def query(owner, place, topic):
        context(owner, place, topic, True)
        event, packets = observe(owner, [('image', vectors[4])], .1)
        recall = event['implicit_reactivation']
        remembered = None
        if recall.get('supported'):
            selected = owner.moments.read_candidate(recall['moments'][0], packets)
            remembered = selected['representations'].get('audio') if selected['supported'] else None
        trace = owner.moments.get(event['moment'])
        if trace['known'] != [True, False, False]:
            raise RuntimeError('Recalled audio became a fabricated sensory observation.')
        return {'place': place, 'topic': topic,
                'correct': remembered is not None and float(remembered @ vectors[5 + topic]) > .99,
                'recalled_audio': remembered is not None, 'choice': recall.get('recall_choice'),
                'candidates': recall.get('candidate_count', 0), 'moment': event['moment']}

    def evaluate(owner, cases):
        before = int(owner.recall_preference.bank.writes)
        rows = [query(owner, place, topic) for place, topic in cases]
        if int(owner.recall_preference.bank.writes) != before:
            raise RuntimeError('Evaluation replayed feedback.')
        return rows

    def accuracy(rows, predicate=lambda row: True):
        values = [row['correct'] for row in rows if predicate(row)]
        return sum(values) / len(values)

    try:
        originals = {}
        for index in (0, 1):
            context(native, index, index)
            event, _ = observe(native, [('image', vectors[4]), ('audio', vectors[5 + index])], .1)
            originals[event['moment']] = native.moments.bank(event['moment']).outputs.clone()
        training = [(0, 0), (0, 1), (1, 0)] * 32
        random.Random(seed).shuffle(training)
        train_rows = []
        for place, topic in training:
            row = query(native, place, topic)
            train_rows.append(row)
            if row['choice'] is None:
                raise RuntimeError('No credit for actually executed recollection.')
            result = native.learn_recall_preference(Consequence(row['choice'], native.clock,
                1. if row['correct'] else -1., 0., 0., origin='environment'))
            if not result['learned']:
                raise RuntimeError('External consequence did not update relevance.')
        snapshot = native.snapshot()
        torch.save(snapshot, output / 'native.pt')
        cases = [(a, b) for a in (0, 1) for b in (0, 1)] * 4
        random.Random(seed + 1).shuffle(cases)
        outcomes = {}
        for mode in ('learned', 'no_policy', 'restarted'):
            owner = restore(snapshot, native.clock)
            try:
                if mode == 'no_policy':
                    owner.recall_preference.bank.weights.zero_()
                outcomes[mode] = evaluate(owner, cases)
                if any(not torch.equal(owner.moments.bank(number).outputs, value)
                       for number, value in originals.items()):
                    raise RuntimeError('Context preference rewrote an original sensory fact.')
                if owner.moments.next_id != snapshot['moments']['next_id'] + 2 * len(cases):
                    raise RuntimeError('Continuous input was discarded from episodic memory.')
            finally:
                owner.moments.close()
        rows = outcomes['learned']
        rate, baseline = accuracy(rows), accuracy(outcomes['no_policy'])
        conflict = accuracy(rows, lambda row: row['place'] == 1 and row['topic'] == 0)
        held_out = accuracy(rows, lambda row: row['place'] == 1 and row['topic'] == 1)
        restarted = [row['correct'] for row in rows] == [row['correct'] for row in outcomes['restarted']]
        report.update(cases=outcomes, training_accuracy=accuracy(train_rows), accuracy=rate,
            no_policy_accuracy=baseline, conflict_accuracy=conflict, held_out_accuracy=held_out,
            restarted=restarted, writes=int(native.recall_preference.bank.writes),
            original_facts_unchanged=True, new_cues_have_no_audio=True,
            accepted=rate >= .9 and conflict >= .9 and held_out >= .9 and rate - baseline >= .25 and restarted)
    finally:
        native.moments.close()
        report['wall_seconds'] = time.monotonic() - started
        atomic_json(output / 'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=17)
    args = parser.parse_args()
    report = run(args.output, args.seed)
    print({key: report.get(key) for key in ('accepted', 'accuracy', 'no_policy_accuracy', 'wall_seconds')})
    raise SystemExit(0 if report['accepted'] else 1)


if __name__ == '__main__':
    main()
