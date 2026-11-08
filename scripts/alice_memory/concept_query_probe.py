"""Finite pretrained query probe from an already taught checkpoint; no reteaching."""
from __future__ import annotations

import argparse
import copy
import json
import time

import torch
from pathlib import Path

from .concept_language import pair
from .concept_memory import restore as restore_concepts
from .continuous_experiment import load_scheduler
from .conceptual_mind import ConceptualMind, save
from .language import LocalLanguage
from .language_process import LanguageProcess
from .persistent_runtime import advance, close_agent, configure_language
from .process_metrics import physical_memory
from .reactivation_index import source_digest
from .runtime_store import atomic_json


def run(checkpoint, output, endpoint, model, ram_fraction=.75):
    LocalLanguage(endpoint, model, ram_fraction=ram_fraction)
    output.mkdir(parents=True, exist_ok=False)
    workers, samples = [], []

    def factory(operation):
        if any(worker.process.poll() is None for worker in workers):
            raise ValueError("Conceptual queries attempted concurrent workers.")
        worker = LanguageProcess(operation, output / 'workers', 120.,
                                 environment={'ALICE_EXPERIMENT_RAM_FRACTION': str(ram_fraction)}, retain_files=True)
        workers.append(worker)
        return worker

    agent, mind, _ = load_scheduler(checkpoint, output / 'workers', factory)
    report = {'completed': False, 'accepted': False, 'model': model, 'ram_fraction': ram_fraction,
              'live_sensors': False, 'cpu_only': True, 'reteaching': False, 'cases': [],
              'free_text_semantics_verified': False, 'scope': 'literal queries of previously taught affine concepts'}
    atomic_json(output / 'report.json', report)
    started = previous = time.monotonic()
    try:
        if not isinstance(agent, ConceptualMind) or agent.concepts.lessons != 3 or 'nivo' not in agent.concepts.banks:
            raise ValueError("This probe requires the three-lesson nivo checkpoint.")
        configure_language(agent, endpoint, model)
        memory = mind.actor.session.memory
        original = [source_digest(block) for block in memory.blocks]
        original_concepts = agent.concepts.snapshot()
        observations = agent.temporal.observations
        numbers = []
        questions = [('first', 'Alice, o que dá aplicar "nivo" à entrada (0.3, 0.7)?'),
                     ('second', 'Porra, e se eu aplicar "nivo" em (0.4, -0.2), que resultado sai?'),
                     ('decimal_comma', 'Qual é o resultado de "nivo" com a entrada (0,25; 0,5)?'),
                     ('unknown', 'Qual resultado sai de "zaru" para (0.3, 0.7)?')]
        ticks = 0
        previous = time.monotonic()
        for case, question in questions:
            number = agent.submit_concept_question(question)
            numbers.append(number)
            while agent.concept_queries.jobs[number]['status'] not in agent.concept_queries.terminal:
                now = time.monotonic()
                if now - started > 360:
                    raise TimeoutError("Concept query probe exceeded its six-minute deadline.")
                ram = physical_memory()
                samples.append(ram['used_bytes'])
                if ram['used_bytes'] > ram['total_bytes'] * ram_fraction:
                    raise RuntimeError("Actual RAM crossed the authorized experimental limit.")
                advance(agent, now - previous, 2.)
                previous = now
                ticks += 1
                time.sleep(.05)
            job = copy.deepcopy(agent.concept_queries.jobs[number])
            error, controls = None, None
            if job['status'] == 'completed':
                x = pair(job['plan']['input_fragment'])
                expected = [2. * x[0], 3. * x[1]]  # External evaluator; never sent to parsing.
                error = max(abs(actual - target) for actual, target in zip(job['evidence']['value'], expected))
                controls = {}
                for label in ('erased', 'swapped_outputs'):
                    shadow = restore_concepts(original_concepts, agent.clock)
                    bank = shadow.banks['nivo']
                    with torch.no_grad():
                        bank.weights.copy_(torch.zeros_like(bank.weights) if label == 'erased' else bank.weights.flip(0))
                    result = shadow.compose(job['plan']['chain'], x)
                    controls[label] = {'value': result['value'], 'max_error': max(abs(a - b) for a, b in zip(result['value'], expected))}
            report['cases'].append({'case': case, 'question': question, 'job': job,
                                    'held_out_max_error': error, 'weight_controls': controls})
            atomic_json(output / 'report.json', report)
        intact = all(torch.equal(old, source_digest(memory.blocks[index])) for index, old in enumerate(original))
        concept_intact = all(torch.equal(old, agent.concepts.banks[name].state_dict()[field])
                             for name, state in original_concepts['banks'].items() for field, old in state.items())
        statuses = [item['job']['status'] for item in report['cases']]
        positives = report['cases'][:3]
        report.update(completed=True, ticks=ticks, lessons=agent.concepts.lessons, old_episode_banks_intact=len(original) if intact else 0,
                      concept_weights_unchanged=concept_intact, observation_count_unchanged=observations == agent.temporal.observations,
                      peak_sampled_ram_bytes=max(samples, default=physical_memory()['used_bytes']),
                      wall_seconds=time.monotonic() - started,
                      accepted=statuses == ['completed', 'completed', 'completed', 'unsupported'] and intact and concept_intact
                      and agent.concepts.lessons == 3 and observations == agent.temporal.observations
                      and all(item['held_out_max_error'] < .003 for item in positives)
                      and all(control['max_error'] > .1 for item in positives for control in item['weight_controls'].values()))
        # Retain answers until a consumer explicitly acknowledges them, including across restart.
        save(output / 'final.pt', agent)
        report['delivered'] = [agent.take_concept_answer(number) for number in numbers]
        atomic_json(output / 'report.json', report)
        return report
    except Exception as error:
        report.update(error=type(error).__name__ + ': ' + str(error)[:2048], wall_seconds=time.monotonic() - started)
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
    print(json.dumps({key: report[key] for key in ('completed', 'accepted', 'ticks', 'lessons', 'workers_terminal')}))
    raise SystemExit(0 if report['accepted'] and report['workers_terminal'] else 2)


if __name__ == '__main__':
    main()
