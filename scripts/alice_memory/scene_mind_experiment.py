"""Finite integration curriculum with trained source weights and parser control.

Tests storage, grounded recall, one-clock continuity and pending language work.
Does not evaluate natural-language quality or concurrent-scene forecasting.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from dataclasses import asdict
from pathlib import Path

import torch

from .checkpoint_io import read_checkpoint
from .experience_signals import WORDS
from .grounded_mind import load as load_grounded
from .language_input import QuestionPlan, references
from .neural_language import NeuralLanguageCoordinator, load, save
from .neural_task_experiment import load_model
from .process_metrics import memory_usage
from .scene_binding import event_source
from .scene_memory import restore_binding
from .scene_mind import SceneGroundedMind
from .scene_signals import packets, scene


class ParserControl:
    """Fixed field parser; expression remains pending, with no language claim."""
    def __init__(self, operation):
        self.operation = operation

    def poll(self):
        item = self.operation
        if item['stage'] != 'parse':
            return None
        plan = QuestionPlan('autor', tuple(references(item['question'])), False, item['model'],
                            'parser-control', hashlib.sha256(item['question'].encode()).hexdigest(), '1' * 64, 0.)
        value = asdict(plan)
        value['names'] = list(value['names'])
        return {'status': 'ready', 'value': value}

    def close(self):
        pass


def tensor_tree_equal(left, right):
    if isinstance(left, torch.Tensor):
        return isinstance(right, torch.Tensor) and torch.equal(left, right)
    if isinstance(left, dict):
        return isinstance(right, dict) and set(left) == set(right) and all(tensor_tree_equal(value, right[name]) for name, value in left.items())
    if isinstance(left, (tuple, list)):
        return type(left) is type(right) and len(left) == len(right) and all(tensor_tree_equal(a, b) for a, b in zip(left, right))
    return left == right


def run(grounded_path, binding_path, task_path, output, seed):
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    torch.set_num_threads(1)
    torch.manual_seed(seed + 990000)
    agent = load_grounded(grounded_path)
    resumed = coordinator = None
    try:
        binding_state = read_checkpoint(binding_path)
        compact = {name: value for name, value in binding_state.items() if name != 'base'}
        compact['tracks'] = []  # New curriculum, retaining only the trained correspondence.
        binding = restore_binding(agent.mind.actor.session, compact)
        agent = SceneGroundedMind(agent, binding.binding, event_source(agent.mind.actor.session.perception))
        coordinator = NeuralLanguageCoordinator(agent, load_model(task_path, agent), 'http://127.0.0.1:11438',
                                                'parser-control', output, ParserControl)
        report = curriculum(coordinator, output, seed, started)
        save(output / 'agent.pt', coordinator)
        resumed = load(output / 'agent.pt', output, ParserControl)
        report['checkpoint_shared_memory'] = resumed.agent.scene.base is resumed.mind.actor.session
        report['checkpoint_pending_latent_equal'] = tensor_tree_equal(resumed.tasks.snapshot(), coordinator.tasks.snapshot())
        values = ((0, 0, 3, 1), (2, 1, 3, 1))
        image, audio = scene(values, random.Random(seed + 991000))
        inputs = packets(image, audio, agent.clock + .1, agent.scene.base.steps * 2)
        coordinator.perceive(inputs, .1, focus_region=1)
        resumed.perceive(inputs, .1, focus_region=1)
        report['checkpoint_continuation_equal'] = tensor_tree_equal(resumed.agent.snapshot(), agent.snapshot())
        selected = next(track['episode'] for track in resumed.agent.scene.tracks
                        if int(track['previous'][:4].argmax()) == 2 and int(track['previous'][8:12].argmax()) == 3
                        and int(track['previous'][12:16].argmax()) == 1)
        for bank in resumed.mind.actor.session.memory.block(selected).banks:
            bank.weights.zero_()
        cue = resumed.agent.scene.tracks[next(i for i, track in enumerate(resumed.agent.scene.tracks) if track['episode'] == selected)]['previous'].double().clone()
        cue.reshape(4, 4)[(1, 2), :] = 0
        recalled = resumed.mind.actor.session.memory.read(cue, resumed.clock, window=(agent.clock, agent.clock))
        report['erased_neural_facts'] = len(recalled['recall'] or {})
        report['elapsed_seconds'] = time.perf_counter() - started
        report['memory_usage'] = memory_usage()
        report['accepted'] = all(report[name] for name in ('checkpoint_shared_memory', 'checkpoint_pending_latent_equal', 'checkpoint_continuation_equal')) and report['frames_correct'] == 24 and report['recalls_correct'] == 16 and report['learned_answers_correct'] == 8 and report['erased_neural_facts'] == 0
        report['source_sha256'] = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in (grounded_path, binding_path, task_path)}
        (output / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        return report
    finally:
        if coordinator is not None:
            coordinator.close()
        if resumed is not None:
            resumed.close()
            resumed.mind.actor.session.memory.close()
        agent.mind.actor.session.memory.close()


def curriculum(coordinator, output, seed, started):
    agent = coordinator.agent
    names = {}
    for word in agent.words.names:
        meaning = agent.words.lookup(word)
        if meaning['supported']:
            names[(meaning['field'], meaning['category'])] = word
    if len(names) != 16:
        raise ValueError('The curriculum requires sixteen trained grounded concepts.')
    rng = random.Random(seed + 992000)
    frames = recalls = answers = 0
    initial_count = agent.scene.memory.count
    for trial in range(8):
        values = ((0, 0, trial % 4, trial // 4), (2, 1, trial % 4, trial // 4))
        for frame in range(3):
            if time.perf_counter() - started > 60:
                raise TimeoutError('Finite scene mind curriculum exceeded sixty seconds.')
            elapsed = 3. if frame == 0 else .1
            image, audio = scene(values if frame % 2 == 0 else tuple(reversed(values)), rng)
            steps, observations = agent.scene.base.steps, agent.temporal.observations
            result = coordinator.perceive(packets(image, audio, agent.clock + elapsed, steps * 2), elapsed, focus_region=frame % 2)
            frames += int(len(result['events']) == 2 and agent.scene.base.steps == steps + 1
                          and agent.temporal.observations == observations + 1 and agent.clock == agent.temporal.clock)
        window = (agent.clock - .2, agent.clock)
        for value in values:
            answer = agent.query_names([names[(0, value[0])], names[(3, value[3])]], window=window)['result']
            facts = None if answer is None else answer['recall']
            recalls += int(facts is not None and facts.get('autor') == WORDS[2][value[2]] and facts.get('impressao') == WORDS[1][value[1]])
        asked = [names[(0, 0)], names[(3, trial // 4)]]
        agent.request_names(asked, 2, window)
        result = coordinator.tick(.1)
        answers += int(result['action'] is not None and result['action']['kind'] == 'emit' and result['action']['signal'] == trial % 4)
        if trial == 0:
            identifier = coordinator.submit(f'Quem estava em "{asked[0]}" em "{asked[1]}"?', window=window)
            coordinator.poll()
            coordinator.poll()
            if not coordinator.capture(coordinator.jobs[identifier]):
                raise ValueError('Trained neural working question did not retrieve source evidence.')
    return {'seed': seed, 'frames_correct': frames, 'frame_cases': 24, 'recalls_correct': recalls,
            'recall_cases': 16, 'learned_answers_correct': answers, 'answer_cases': 8,
            'new_episodes': agent.scene.memory.count - initial_count, 'event_tracks': len(agent.scene.tracks),
            'resident_pages': len(agent.scene.memory.cache), 'pending_language_jobs': len(coordinator.jobs),
            'language_quality_evaluated': False, 'concurrent_forecast_quality_evaluated': False,
            'attention_source': 'explicit_region'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--grounded', type=Path, required=True)
    parser.add_argument('--binding', type=Path, required=True)
    parser.add_argument('--tasks', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=17)
    args = parser.parse_args()
    report = run(args.grounded, args.binding, args.tasks, args.output, args.seed)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report['accepted']:
        raise SystemExit('Concurrent mind integration did not pass its finite acceptance gate.')


if __name__ == '__main__':
    main()
