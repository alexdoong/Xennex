"""Online nonverbal relevance feedback with held-out environment/topic combinations."""
import argparse
import hashlib
import random
import time
from pathlib import Path

import torch
from torch.nn import functional as F

from .importance import Consequence
from .native_grounding import NativeGrounding, restore
from .native_reactivation import activate
from .native_sensor import NativeObservation
from .runtime_store import atomic_json


def run(output, seed=17):
    output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(1)
    generator = torch.Generator().manual_seed(seed)
    vectors = torch.linalg.qr(torch.randn(128, 8, generator=generator))[0].T.float()
    native = NativeGrounding(implicit_recall=True)
    report = {'accepted': False, 'seed': seed, 'synthetic_perceptual_vectors': True,
              'language_called': False, 'names': False, 'training_feedbacks': 96,
              'held_out_combination': [1, 1], 'cases': []}
    started = time.monotonic()

    def packet(modality, latent, at):
        return NativeObservation(modality, latent, at, native.received_observations,
            hashlib.sha256(latent.numpy().tobytes()).hexdigest(), origin='environment')

    def context(place, topic, noisy=False):
        if time.monotonic() - started > 60:
            raise TimeoutError('Contextual recall exceeded its registered 60-second budget.')
        at = native.clock + 120.
        image, audio = vectors[place], vectors[2 + topic]
        if noisy:
            image = F.normalize(image + .005 * vectors[7], dim=0)
            audio = F.normalize(audio - .005 * vectors[7], dim=0)
        native.observe([packet('image', image, at), packet('audio', audio, at)], at)

    def cue():
        return NativeObservation('image', vectors[4], native.clock, 0, '0'*64, origin='self')

    def query(place, topic):
        context(place, topic, True)
        result = activate(native, [cue()], native.clock, None)
        if not result['supported']:
            raise RuntimeError('No sensory recollection in contextual task.')
        selected = result['moments'][0]
        content = native.moments.read_candidate(selected, [cue()])['representations']['audio']
        correct = float(content @ vectors[5 + topic]) > .99
        return result, correct

    try:
        for index in (0, 1):
            context(index, index)
            at = native.clock + .1
            native.observe([packet('image', vectors[4], at), packet('audio', vectors[5 + index], at)], at)
        train = [(0, 0), (0, 1), (1, 0)] * 32
        random.Random(seed).shuffle(train)
        rewards = []
        for place, topic in train:
            result, correct = query(place, topic)
            token = result['recall_choice']
            if token is None:
                raise RuntimeError('Recollection has no grounded feedback credit.')
            learned = native.learn_recall_preference(Consequence(token, native.clock,
                1. if correct else -1., 0., 0., origin='environment'))
            if not learned['learned']:
                raise RuntimeError('External relevance feedback did not update the preference.')
            rewards.append(correct)
        cases = [(a, b) for a in (0, 1) for b in (0, 1)] * 4
        random.Random(seed + 1).shuffle(cases)
        for place, topic in cases:
            _, correct = query(place, topic)
            report['cases'].append({'place': place, 'topic': topic, 'correct': correct})
        def accuracy(predicate=lambda item: True):
            selected = [item['correct'] for item in report['cases'] if predicate(item)]
            return sum(selected) / len(selected)
        saved = native.recall_preference.bank.weights.clone()
        native.recall_preference.bank.weights.zero_()
        baseline = [query(place, topic)[1] for place, topic in cases]
        native.recall_preference.bank.weights.copy_(saved)
        contexts = native.recall_context.weights.clone()
        native.recall_context.weights.zero_()
        no_context = [query(place, topic)[1] for place, topic in cases]
        native.recall_context.weights.copy_(contexts)
        remembered = native.moments.related([cue()], native.clock)['entries']
        factors = {x['candidate']['id']: native.moments.bank(x['candidate']['id']).outputs.clone() for x in remembered}
        try:
            for number in factors: native.moments.bank(number).outputs.zero_()
            empty = native.moments.related([cue()], native.clock)
            no_content = not empty['entries']
        finally:
            for number, values in factors.items(): native.moments.bank(number).outputs.copy_(values)
        snapshot = native.snapshot()
        torch.save(snapshot, output / 'native.pt')
        fresh = restore(snapshot, native.clock)
        original = native
        try:
            old_order = native.moments.related([cue()], native.clock, preference=native.recall_preference,
                contexts=native.recall_context, context=native.working)['entries']
            new_order = fresh.moments.related([cue()], fresh.clock, preference=fresh.recall_preference,
                contexts=fresh.recall_context, context=fresh.working)['entries']
            restarted = [x['candidate']['id'] for x in old_order] == [x['candidate']['id'] for x in new_order]
            native = fresh
            learned_weights = native.recall_preference.bank.weights.clone()
            after_restart = [query(place, topic)[1] for place, topic in cases]
            restarted = restarted and sum(after_restart) / len(after_restart) >= .9 and torch.equal(
                learned_weights, native.recall_preference.bank.weights)
        finally:
            native = original
            fresh.moments.close()
        rate, old_rate = accuracy(), sum(baseline) / len(baseline)
        held_out = accuracy(lambda x: x['place'] == 1 and x['topic'] == 1)
        conflict = accuracy(lambda x: x['place'] == 1 and x['topic'] == 0)
        report.update(accuracy=rate, held_out_accuracy=held_out, conflict_accuracy=conflict,
            no_learning_accuracy=old_rate, no_context_accuracy=sum(no_context) / len(no_context),
            no_content_from_metadata=no_content, restarted=restarted, writes=int(native.recall_preference.bank.writes),
            restart_accuracy=sum(after_restart) / len(after_restart),
            training_accuracy=sum(rewards) / len(rewards), wall_seconds=time.monotonic() - started,
            accepted=rate >= .9 and held_out >= .9 and conflict >= .9 and rate - old_rate >= .25
                and rate - sum(no_context) / len(no_context) >= .25 and no_content and restarted)
    finally:
        native.moments.close()
        atomic_json(output / 'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=17)
    args = parser.parse_args()
    report = run(args.output, args.seed)
    print({key: report[key] for key in ('accepted', 'accuracy', 'held_out_accuracy', 'conflict_accuracy', 'wall_seconds')})


if __name__ == '__main__':
    main()
