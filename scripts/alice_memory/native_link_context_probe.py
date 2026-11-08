"""Conditioned correspondence from sensory history, with cached native files.

An external controlled curriculum changes the sound paired with each shape after
two visual primers. No context label or expected sound enters the prediction.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

import torch
from torch.nn import functional as F

from .conceptual_mind import save
from .continuous_experiment import load_scheduler
from .native_batch import validate_receipt
from .native_sensor import NativeObservation
from .persistent_runtime import close_agent
from .reactivation_index import source_digest
from .runtime_store import atomic_json


def run(checkpoint, encoded_folder, output):
    if output.exists():
        raise ValueError('Contextual trial needs a fresh output.')
    requests, receipts = list(encoded_folder.glob('encode-*.json')), list(encoded_folder.glob('encode-*.pt'))
    if len(requests) != 1 or len(receipts) != 1:
        raise ValueError('Contextual trial needs an unambiguous encoder receipt.')
    request = json.loads(requests[0].read_text(encoding='utf-8'))
    packets = validate_receipt(torch.load(receipts[0], weights_only=True, map_location='cpu'),
                               request['items'], encoded_folder, request['token'])
    frames = {index: {packet.modality: packet for packet in packets if packet.sequence == index} for index in range(18)}
    if len(packets) != 36 or any(set(frame) != {'image', 'audio'} for frame in frames.values()):
        raise ValueError('Controlled receipt lost one of its18 matched frames.')
    torch.set_num_threads(1)
    agent, mind, _ = load_scheduler(checkpoint)
    output.mkdir(parents=True, exist_ok=False)
    report = {'accepted': False, 'scope': 'controlled context-dependent image/audio links from verified frozen native features',
              'live_sensors': False, 'encoder_reloaded': False, 'cases': [],
              'receipt_sha256': hashlib.sha256(receipts[0].read_bytes()).hexdigest()}
    try:
        native = agent.native
        if native.links.frames or not native.moments.traces or len(native.moments.traces) > 12:
            raise ValueError('Trial needs untrained links and a small source archive.')
        old_banks = [source_digest(block).clone() for block in mind.actor.session.memory.blocks]
        original_names, original_sources = native.names.copy(), copy.deepcopy(native.sources)
        original_reports = copy.deepcopy(native.interpretations.records)
        original_writers = {name: bank.weights.clone() for name, bank in native.writers.items()}
        native.attention.configure('full')
        memory = native.moments
        memory.capacity = len(memory.traces)
        memory.routes = memory.routes[:memory.capacity].clone()
        memory.hot_limit = min(memory.hot_limit, memory.capacity)
        sequence = max(record['sequence'] for record in native.last.values()) + 1
        training_ids = []
        def expose(items):
            nonlocal sequence
            now = agent.clock + .1
            signals = [NativeObservation(item.modality, item.latent, now, sequence, item.sample_sha256) for item in items]
            sequence += 1
            return agent.perceive_native(signals, .1)['native_perception']
        def prime(context, variant):
            marker = frames[(context + 1) * 6 + variant]['image']
            for _ in range(8):
                expose([marker])
        for variant in range(4):
            for context in (0, 1):
                for category in (0, 1):
                    prime(context, variant)
                    image = frames[category * 6 + variant]['image']
                    sound = frames[(category ^ context) * 6 + variant]['audio']
                    training_ids.append(expose([image, sound])['moment'])
        # Retire remaining training frames by spaced single-channel exposures.
        for _ in range(memory.capacity):
            for _ in range(5):
                agent.tick(60.)
            expose([frames[12]['image']])
        if any(memory.get(number) is not None for number in training_ids):
            raise ValueError('Training episodes remain; contextual retention trial incomplete.')
        prototypes = [F.normalize(torch.stack([frames[category * 6 + variant]['audio'].latent for variant in range(4)]).mean(0), dim=0)
                      for category in (0, 1)]
        fixtures = []
        supported = correct = unconditioned_correct = 0
        minimum = 1.
        for variant in (4, 5):
            for context in (0, 1):
                prime(context, variant)
                prior = native.working.clone()
                for category in (0, 1):
                    cue = frames[category * 6 + variant]['image']
                    expected_category = category ^ context
                    expected = frames[expected_category * 6 + variant]['audio'].latent
                    result = agent.associate_native(cue, 'audio', contextual=True)
                    general = agent.associate_native(cue, 'audio')
                    selected = None if not result['supported'] else int(torch.stack([result['latent'] @ value for value in prototypes]).argmax())
                    general_selected = None if not general['supported'] else int(torch.stack([general['latent'] @ value for value in prototypes]).argmax())
                    cosine = None if not result['supported'] else float(result['latent'] @ expected)
                    supported += int(result['supported'])
                    correct += int(selected == expected_category)
                    unconditioned_correct += int(general_selected == expected_category)
                    if cosine is not None:
                        minimum = min(minimum, cosine)
                    report['cases'].append({'variant': variant, 'context': context, 'source_family': category,
                        'expected_sound_family': expected_category, 'supported': result['supported'], 'selected': selected,
                        'general_selected': general_selected, 'cosine': cosine, 'reason': result['reason']})
                    fixtures.append({'cue': vars(cue).copy(), 'context': prior.clone(), 'target': 'audio', 'expected': expected})
                    if not torch.equal(native.working, prior):
                        raise ValueError('Prediction changed context or received its expected target.')
        learned_bank = native.links.contextual_banks['image:audio'].weights.clone()
        native.links.contextual_banks['image:audio'].weights.zero_()
        erased_supported = sum(native.links.predict(NativeObservation(**item['cue']), item['target'], item['context'])['supported'] for item in fixtures)
        native.links.contextual_banks['image:audio'].weights.copy_(learned_bank)
        if native.names != original_names or native.sources != original_sources or native.interpretations.records != original_reports or any(not torch.equal(original_writers[name], bank.weights) for name, bank in native.writers.items()):
            raise ValueError('Context learning changed earlier named knowledge or reports.')
        if len(old_banks) != len(mind.actor.session.memory.blocks) or any(not torch.equal(value, source_digest(block)) for value, block in zip(old_banks, mind.actor.session.memory.blocks)):
            raise ValueError('Context learning changed earlier synthetic episodes.')
        report.update(total=8, supported=supported, correct=correct, unconditioned_correct=unconditioned_correct,
            erased_supported=erased_supported, minimum_cosine=minimum, all_training_episodes_forgotten=True,
            old_banks_preserved=len(old_banks), retained=len(memory.traces), lifetime=memory.next_id,
            observations=native.observations, received=native.received_observations,
            context_frames=native.links.context_frames, simulated_washout_interval=300.,
            accepted=supported == 8 and correct == 8 and unconditioned_correct <= 4 and erased_supported == 0 and minimum > .95)
        save(output / 'final.pt', agent)
        torch.save({'fixtures': fixtures}, output / 'reserved.pt')
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)[:2048]
        raise
    finally:
        atomic_json(output / 'report.json', report)
        close_agent(agent, mind)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('checkpoint', 'encoded-folder', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = run(args.checkpoint, args.encoded_folder, args.output)
    print({name: result[name] for name in ('accepted', 'correct', 'total', 'unconditioned_correct', 'minimum_cosine')})
    raise SystemExit(0 if result['accepted'] else 2)


if __name__ == '__main__':
    main()
