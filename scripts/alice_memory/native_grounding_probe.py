"""Finite native-pixel/PCM association probe using pretrained features.

Media are generated controlled signals, not human photographs or real speech.
Names/correspondences are external teaching. Held-out variants test acquired
associations separately from the encoder's inherited perceptual capabilities.
"""
from __future__ import annotations

import argparse
import json
import random
import time
import wave
from pathlib import Path
from uuid import uuid4

import torch
from PIL import Image, ImageDraw

from .conceptual_mind import ConceptualMind, save
from .continuous_experiment import load_scheduler
from .grounded_mind import WrittenName
from .native_batch import encode_batch
from .native_grounding import restore as restore_native
from .native_sensor import NativeObservation
from .persistent_runtime import advance, close_agent
from .process_metrics import memory_usage, physical_memory
from .reactivation_index import source_digest
from .runtime_store import atomic_json


def media(folder, category, rng):
    image = Image.new('RGB', (224, 224), 'white')
    draw = ImageDraw.Draw(image)
    center = (rng.randint(98, 126), rng.randint(98, 126))
    size = rng.randint(62, 80)
    box = (center[0] - size, center[1] - size, center[0] + size, center[1] + size)
    if category == 0:
        draw.ellipse(box, fill=(220, rng.randint(10, 40), 25))
    elif category == 1:
        draw.rectangle(box, fill=(25, 30, rng.randint(200, 240)))
    else:
        draw.polygon([(center[0], box[1]), (box[0], box[3]), (box[2], box[3])], fill=(240, 200, 20))
    path = folder / (uuid4().hex + '.png')
    image.save(path)
    sample_rate = 16000
    length = 32000
    times = torch.arange(length, dtype=torch.float32) / sample_rate
    amplitude = rng.uniform(.22, .35)
    if category == 0:
        samples = amplitude * torch.sin(times * 2 * torch.pi * rng.uniform(430, 450))
    elif category == 1:
        generator = torch.Generator().manual_seed(rng.randrange(1000000))
        samples = torch.randn(length, generator=generator).clamp(-3, 3) * amplitude / 3
    else:
        period = rng.uniform(.18, .22)
        envelope = torch.exp(-torch.remainder(times, period) * 80.)
        samples = amplitude * envelope * torch.sin(times * 2 * torch.pi * 1500.)
    audio = folder / (uuid4().hex + '.wav')
    with wave.open(str(audio), 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes((samples.clamp(-1, 1) * 32767).short().numpy().astype('<i2').tobytes())
    return path, audio


def run(checkpoint, model_folder, output, interpreter, seed=17, ram_fraction=.75):
    if type(seed) is not int or not 0 <= seed <= 100000:
        raise ValueError("Invalid native association seed.")
    output.mkdir(parents=True, exist_ok=False)
    folder = output / 'signals'
    folder.mkdir()
    agent, mind, _ = load_scheduler(checkpoint)
    if not isinstance(agent, ConceptualMind):
        agent = ConceptualMind(agent)
    report = {'completed': False, 'accepted': False, 'seed': seed, 'ram_fraction': ram_fraction,
              'generated_media': True, 'real_human_media': False, 'pretrained_encoder': True,
              'live_sensors': False, 'cases': [], 'scope': 'new names and cross-modal associations of controlled native files'}
    atomic_json(output / 'report.json', report)
    started = time.monotonic()
    original = [source_digest(block) for block in mind.actor.session.memory.blocks]
    old_observations = agent.temporal.observations
    labels = ['nivo', 'tazi', 'lendo']
    random.Random(seed).shuffle(labels)
    rng = random.Random(seed + 100)
    training, reserved = [], []
    items = []
    try:
        if agent.native.names:
            raise ValueError("Probe requires native associations not yet taught.")
        for category in range(3):
            for variant in range(6):
                if time.monotonic() - started > 240:
                    raise TimeoutError("Native grounding probe exceeded four minutes.")
                image, audio = media(folder, category, rng)
                sequence = category * 6 + variant
                items.extend({'modality': modality, 'file': path.name, 'acquired_at': agent.clock,
                              'sequence': sequence, 'origin': 'environment'} for modality, path in (('image', image), ('audio', audio)))
                record = {'category': category, 'name': labels[category], 'sequence': sequence, 'packets': []}
                (training if variant < 4 else reserved).append(record)
        encoded, worker = encode_batch(output, model_folder, interpreter, items, ram_fraction,
                                       on_tick=lambda elapsed: advance(agent, elapsed, 2.))
        report['worker'] = worker
        for record in (*training, *reserved):
            record['packets'] = [packet for packet in encoded if packet.sequence == record['sequence']]
        report['before_supported'] = sum(agent.native.recognize(packet)['supported'] for item in reserved for packet in item['packets'])
        for sequence, item in enumerate(training):
            now = agent.clock + .1
            packets = [NativeObservation(packet.modality, packet.latent, now, sequence, packet.sample_sha256) for packet in item['packets']]
            agent.perceive_native(packets, .1)
            result = agent.teach_native_name(WrittenName(item['name'], now, sequence))
            if not result['learned']:
                raise ValueError("Synchronized native teaching was not committed.")
        saved = agent.native.snapshot()
        controls = {label: restore_native(saved, agent.clock) for label in ('erased', 'swapped')}
        for bank in controls['erased'].readers.values():
            bank.weights.zero_()
        for bank in controls['swapped'].readers.values():
            bank.weights[:3].copy_(bank.weights[:3].roll(1, 0))
        correct, control_correct = 0, {name: 0 for name in controls}
        cross_similarities = []
        for item in reserved:
            for packet in item['packets']:
                result = agent.native.recognize(packet)
                correct += int(result['supported'] and result['name'] == item['name'])
                for name, shadow in controls.items():
                    control = shadow.recognize(packet)
                    control_correct[name] += int(control['supported'] and control['name'] == item['name'])
                other = 'audio' if packet.modality == 'image' else 'image'
                association = agent.native.cross(packet, other)
                target = next(value for value in item['packets'] if value.modality == other)
                similarity = None if not association['supported'] else float(association['latent'] @ target.latent)
                if similarity is not None:
                    cross_similarities.append(similarity)
                report['cases'].append({'expected_name': item['name'], 'modality': packet.modality,
                                        'recognized': result, 'cross_supported': association['supported'], 'cross_cosine': similarity})
        intact = all(torch.equal(old, source_digest(mind.actor.session.memory.blocks[index])) for index, old in enumerate(original))
        report.update(completed=True, correct=correct, total=12, control_correct=control_correct,
                      cross_supported=len(cross_similarities), minimum_cross_cosine=min(cross_similarities, default=None),
                      native_observations=agent.native.observations, native_lessons=len(agent.native.sources),
                      old_episode_banks_intact=len(original) if intact else 0,
                      old_observations_unchanged=agent.temporal.observations == old_observations,
                      peak_sampled_pc_ram_bytes=worker['peak_sampled_pc_ram_bytes'], resources=memory_usage(),
                      wall_seconds=time.monotonic() - started,
                      accepted=correct == 12 and control_correct == {'erased': 0, 'swapped': 0}
                      and len(cross_similarities) == 12 and min(cross_similarities) > .9 and intact
                      and agent.temporal.observations == old_observations)
        save(output / 'final.pt', agent)
        torch.save({'reserved': [{**item, 'packets': [vars(packet).copy() for packet in item['packets']]} for item in reserved],
                    'labels': labels}, output / 'reserved.pt')
        # No native model weights or raw media are embedded in the mind checkpoint.
        atomic_json(output / 'report.json', report)
        return report
    except Exception as error:
        report.update(error=type(error).__name__ + ': ' + str(error)[:2048], wall_seconds=time.monotonic() - started)
        atomic_json(output / 'report.json', report)
        raise
    finally:
        close_agent(agent, mind)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--interpreter', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=17)
    parser.add_argument('--ram-fraction', type=float, default=.75)
    args = parser.parse_args()
    report = run(args.checkpoint, args.models, args.output, args.interpreter, args.seed, args.ram_fraction)
    print(json.dumps({key: report[key] for key in ('completed', 'accepted', 'correct', 'total', 'cross_supported')}))
    raise SystemExit(0 if report['accepted'] else 2)


if __name__ == '__main__':
    main()
