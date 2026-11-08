"""Unnamed correspondence trial on verified cached native encoder receipts.

Uses controlled shape/sound files from an earlier finite encoder run. No encoder
is retrained or loaded here. This is not daily perception or semantic discovery.
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
from .native_links import NativeLinks
from .native_sensor import NativeObservation
from .persistent_runtime import close_agent
from .reactivation_index import source_digest
from .runtime_store import atomic_json


def run(checkpoint, encoded_folder, output):
    if output.exists():
        raise ValueError('Unnamed link probe requires a fresh output.')
    requests, receipts = list(encoded_folder.glob('encode-*.json')), list(encoded_folder.glob('encode-*.pt'))
    if len(requests) != 1 or len(receipts) != 1:
        raise ValueError('Probe requires one unambiguous earlier encoder receipt.')
    request = json.loads(requests[0].read_text(encoding='utf-8'))
    packets = validate_receipt(torch.load(receipts[0], weights_only=True, map_location='cpu'),
                               request['items'], encoded_folder, request['token'])
    if len(packets) != 36 or {packet.sequence for packet in packets} != set(range(18)):
        raise ValueError('Probe expects the controlled three-family, six-variant curriculum.')
    grouped = {index: {packet.modality: packet for packet in packets if packet.sequence == index} for index in range(18)}
    if any(set(frame) != {'image', 'audio'} for frame in grouped.values()):
        raise ValueError('Earlier receipt lost its matched image/audio frame.')
    training = [index for index in range(18) if index % 6 < 4]
    reserved = [index for index in range(18) if index % 6 >= 4]
    torch.set_num_threads(1)
    agent, mind, _ = load_scheduler(checkpoint)
    output.mkdir(parents=True, exist_ok=False)
    report = {'accepted': False, 'scope': 'unnamed co-occurrences; verified frozen native features of controlled files; reserved variants',
              'encoder_reloaded': False, 'live_sensors': False, 'cases': [],
              'source_receipt_sha256': hashlib.sha256(receipts[0].read_bytes()).hexdigest()}
    try:
        native = agent.native
        if native.links.frames or not native.moments.traces or len(native.moments.traces) > 12:
            raise ValueError('Probe needs untrained links and a small retained source archive.')
        old_banks = [source_digest(block).clone() for block in mind.actor.session.memory.blocks]
        names, sources = native.names.copy(), copy.deepcopy(native.sources)
        old_writers = {name: bank.weights.clone() for name, bank in native.writers.items()}
        original_statements = copy.deepcopy(native.interpretations.records)
        native.attention.configure('full')
        # Bound only this copied experiment to its current archive size.
        memory = native.moments
        memory.capacity = len(memory.traces)
        memory.hot_limit = min(memory.hot_limit, memory.capacity)
        memory.routes = memory.routes[:memory.capacity].clone()
        native.advance(agent.clock)
        latest = memory.traces[-1]
        visual_slot = next(slot for slot, known in enumerate(latest['known']) if known)
        from .native_sensor import MODALITIES
        washout_modality = MODALITIES[visual_slot]
        washout_vector = F.normalize(memory.routes[-1, visual_slot].float(), dim=0)
        washout_hash = latest['sources'][washout_modality]['sha256']
        sequence = max(record['sequence'] for record in native.last.values()) + 1
        shadow = NativeLinks()
        before_supported = sum(native.associate(grouped[index][source], target)['supported']
                               for index in reserved for source, target in (('image', 'audio'), ('audio', 'image')))
        trained_ids = []
        for index in training:
            at = agent.clock + .1
            frame = [NativeObservation(name, item.latent, at, sequence, item.sample_sha256)
                     for name, item in grouped[index].items()]
            event = agent.perceive_native(frame, .1)['native_perception']
            trained_ids.append(event['moment'])
            # A mismatched-pair control sees exactly the same source features.
            other = grouped[(index + 6) % 18]['audio']
            visual = next(item for item in frame if item.modality == 'image')
            shadow.observe([visual, NativeObservation('audio', other.latent, at, sequence, other.sample_sha256)], at)
            sequence += 1
        for _ in range(memory.capacity):
            # Advance the shared clock without writing or replaying a percept.
            # Spaced exposures allow the supplied freshness policy to retire
            # training episodes instead of immediately evicting each washout.
            for _ in range(5):
                agent.tick(60.)
            at = agent.clock + .1
            agent.perceive_native([NativeObservation(washout_modality, washout_vector, at, sequence, washout_hash)], .1)
            sequence += 1
        if any(memory.get(index) is not None for index in trained_ids):
            raise ValueError('Washout did not remove all co-occurrence training episodes.')
        target_prototypes = {name: [F.normalize(torch.stack([grouped[index][name].latent for index in training if index // 6 == category]).mean(0), dim=0)
                                   for category in range(3)] for name in ('image', 'audio')}
        correct = swapped_correct = supported = 0
        cosines = []
        for index in reserved:
            for source, target in (('image', 'audio'), ('audio', 'image')):
                cue = grouped[index][source]
                result = native.associate(cue, target)
                control = shadow.predict(cue, target)
                expected = grouped[index][target].latent
                selected = None
                cosine = None
                if result['supported']:
                    supported += 1
                    cosine = float(result['latent'] @ expected)
                    cosines.append(cosine)
                    selected = int(torch.stack([result['latent'] @ prototype for prototype in target_prototypes[target]]).argmax())
                    correct += int(selected == index // 6)
                control_selected = None if not control['supported'] else int(torch.stack([control['latent'] @ prototype for prototype in target_prototypes[target]]).argmax())
                swapped_correct += int(control_selected == index // 6)
                report['cases'].append({'source_modality': source, 'target_modality': target, 'expected_family': index // 6,
                    'supported': result['supported'], 'cosine': cosine, 'selected_family': selected,
                    'mismatched_selected_family': control_selected, 'reason': result['reason']})
        learned = native.links.snapshot()
        erased_supported = 0
        for bank in native.links.banks.values():
            bank.weights.zero_()
        for index in reserved:
            for source, target in (('image', 'audio'), ('audio', 'image')):
                erased_supported += int(native.associate(grouped[index][source], target)['supported'])
        from .native_links import restore
        native.links = restore(learned, native.clock, memory.next_id)
        if native.names != names or native.sources != sources or native.interpretations.records != original_statements or any(not torch.equal(old_writers[name], bank.weights) for name, bank in native.writers.items()):
            raise ValueError('Unnamed learning changed named knowledge or reports.')
        if len(old_banks) != len(mind.actor.session.memory.blocks) or any(not torch.equal(value, source_digest(block)) for value, block in zip(old_banks, mind.actor.session.memory.blocks)):
            raise ValueError('Unnamed learning changed earlier synthetic episodes.')
        report.update(before_supported=before_supported, supported=supported, correct=correct, total=12,
            mismatched_correct=swapped_correct, erased_supported=erased_supported,
            minimum_cosine=min(cosines, default=None), names_preserved=names, old_banks_preserved=len(old_banks),
            all_training_episodes_forgotten=True, retained=len(memory.traces), lifetime=memory.next_id,
            simulated_washout_interval=300.,
            historical_link_frames=native.links.historical_frames, learned_link_frames=native.links.frames,
            pair_writes={pair: int(bank.writes) for pair, bank in native.links.banks.items()},
            accepted=before_supported == 0 and supported == 12 and correct == 12 and swapped_correct == 0
                and erased_supported == 0 and len(cosines) == 12 and min(cosines) > .9)
        save(output / 'final.pt', agent)
        torch.save({'reserved': [vars(grouped[index][source]).copy() for index in reserved for source in ('image', 'audio')],
                    'expected': [grouped[index][target].latent for index in reserved for target in ('audio', 'image')]}, output / 'reserved.pt')
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
    print({name: result[name] for name in ('accepted', 'correct', 'total', 'mismatched_correct', 'minimum_cosine')})
    raise SystemExit(0 if result['accepted'] else 2)


if __name__ == '__main__':
    main()
