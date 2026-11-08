"""Finite installed-model teaching probe; caller owns the loopback model host."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import torch

from .conceptual_mind import ConceptualMind, save
from .continuous_experiment import load_scheduler
from .language_process import LanguageProcess
from .persistent_runtime import advance, close_agent, configure_language
from .process_metrics import physical_memory
from .reactivation_index import source_digest
from .runtime_store import atomic_json


def run(checkpoint, output, endpoint, model, ram_fraction=.75):
    from .language import LocalLanguage
    LocalLanguage(endpoint, model, ram_fraction=ram_fraction)
    output.mkdir(parents=True, exist_ok=False)
    workers = []
    samples = []

    def factory(operation):
        if any(worker.process.poll() is None for worker in workers):
            raise ValueError("Real teaching attempted concurrent language workers.")
        worker = LanguageProcess(operation, output / 'workers', 120.,
                                 environment={'ALICE_EXPERIMENT_RAM_FRACTION': str(ram_fraction)}, retain_files=True)
        workers.append(worker)
        return worker

    base, mind, _ = load_scheduler(checkpoint, output / 'workers', factory)
    agent = base if isinstance(base, ConceptualMind) else ConceptualMind(base)
    report = {'completed': False, 'accepted': False, 'model': model, 'ram_fraction': ram_fraction,
              'backend': 'installed', 'live_sensors': False, 'cpu_only': True, 'cases': [], 'free_text_verified': False,
              'scope': 'three literal Portuguese lessons parsed by a pretrained model, one negative control'}
    atomic_json(output / 'report.json', report)
    started, previous = time.monotonic(), time.monotonic()
    try:
        configure_language(agent, endpoint, model)
        memory = mind.actor.session.memory
        original = [source_digest(block) for block in memory.blocks]
        observations = agent.temporal.observations
        previous = time.monotonic()
        texts = [('zero', 'Alice, vou te ensinar: em "nivo", (0, 0) vira (0, 0).'),
                 ('first_axis', 'No conceito "nivo", a entrada (1, 0) passa para (2, 0).'),
                 ('second_axis', 'Porra, olha esse exemplo de "nivo": (0, 1) vira (0, 3).'),
                 ('negated', 'No conceito "nivo", (1, 0) não vira (2, 0).')]
        ticks = 0
        for name, text in texts:
            number = agent.submit_lesson(text, ttl=300.)
            while agent.teaching.jobs[number]['status'] not in ('completed', 'uncertain', 'failed', 'cancelled'):
                now = time.monotonic()
                if now - started > 360:
                    raise TimeoutError("Teaching probe exceeded its finite six-minute deadline.")
                ram = physical_memory()
                samples.append(ram['used_bytes'])
                if ram['used_bytes'] > ram['total_bytes'] * ram_fraction:
                    raise RuntimeError("Actual RAM crossed the authorized experimental limit.")
                advance(agent, now - previous, 2.)
                previous = now
                ticks += 1
                time.sleep(.05)
            job = agent.take_lesson(number)
            report['cases'].append({'case': name, 'text': text, 'job': job})
            atomic_json(output / 'report.json', report)
        prediction = agent.concepts.predict('nivo', [.3, .7])
        error = None if not prediction['supported'] else float((torch.tensor(prediction['value']) - torch.tensor([.6, 2.1])).abs().max())
        intact = all(torch.equal(value, source_digest(memory.blocks[index])) for index, value in enumerate(original))
        statuses = [item['job']['status'] for item in report['cases']]
        report.update(completed=True, ticks=ticks, held_out=prediction, held_out_max_error=error,
                      lessons=agent.concepts.lessons, old_episode_banks_intact=len(original) if intact else 0,
                      observation_count_unchanged=observations == agent.temporal.observations,
                      peak_sampled_ram_bytes=max(samples, default=physical_memory()['used_bytes']),
                      wall_seconds=time.monotonic() - started,
                      accepted=statuses[:3] == ['completed'] * 3 and statuses[3] in ('uncertain', 'failed')
                      and agent.concepts.lessons == 3 and error is not None and error < .003 and intact
                      and observations == agent.temporal.observations)
        save(output / 'final.pt', agent)
        atomic_json(output / 'report.json', report)
        return report
    except Exception as error:
        report.update(error=type(error).__name__ + ': ' + str(error)[:2048],
                      wall_seconds=time.monotonic() - started, peak_sampled_ram_bytes=max(samples, default=0))
        atomic_json(output / 'report.json', report)
        raise
    finally:
        close_agent(agent, mind)
        report['workers_terminal'] = all(worker.process.poll() is not None for worker in workers)
        atomic_json(output / 'report.json', report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--endpoint', default='http://127.0.0.1:11438')
    parser.add_argument('--model', default='qwen3.5:0.8b-q8_0')
    parser.add_argument('--ram-fraction', type=float, default=.75)
    args = parser.parse_args()
    torch.set_num_threads(1)
    report = run(args.checkpoint, args.output, args.endpoint, args.model, args.ram_fraction)
    print(json.dumps({key: report[key] for key in ('completed', 'accepted', 'lessons', 'ticks', 'held_out_max_error', 'workers_terminal')}))
    raise SystemExit(0 if report['accepted'] and report['workers_terminal'] else 2)


if __name__ == '__main__':
    main()
