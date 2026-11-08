"""Finite comparison of concurrent events in resident and paged neural memory."""
from __future__ import annotations

import argparse
import json
import random
import time
from contextlib import ExitStack
from pathlib import Path

import torch

from .episodic_language import write_report
from .episodic_session import EpisodicSession
from .event_scene_experiment import create
from .paged_memory import PagedMemory
from .process_metrics import Budget, memory_usage
from .scene_memory import ConcurrentEventSession, load, save
from .scene_signals import packets, scene


def equal_weights(resident, paged):
    if resident.memory.metadata()['traces'] != paged.memory.metadata()['traces']:
        return False
    return all(torch.equal(value, paged.memory.block(index).state_dict()[name])
               for index, block in enumerate(resident.memory.blocks)
               for name, value in block.state_dict().items())


def run(checkpoint: Path, output: Path, seed: int) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    report = {'completed': False, 'accepted': False, 'seed': seed, 'hot_limit': 2,
              'scope': 'localized synthetic scenes; episodic subsystem only',
              'criteria': 'exact frames and weights; <=2 hot pages; cold recall; exact resume; erased weights remove facts'}
    write_report(output / 'report.json', report)
    started = time.perf_counter()
    try:
        torch.set_num_threads(1)
        rng, budget = random.Random(seed), Budget(1000, 120)
        with ExitStack() as cleanup:
            source = load(checkpoint)
            if hasattr(source.memory, 'close'):
                cleanup.callback(source.memory.close)
            if type(source) is not ConcurrentEventSession:
                raise ValueError('Expected learned format-34 event correspondence.')
            resident = create(source.base.perception, source.base.boundary, source.binding, 128)
            memory = PagedMemory(128, 2)
            cleanup.callback(memory.close)
            paged = ConcurrentEventSession(EpisodicSession(source.base.perception, source.base.boundary, memory),
                                           source.binding, source.binding_source)
            maximum_hot, matched = 0, 0
            for cycle in range(3):
                for actor in range(4):
                    for context in range(4):
                        values = ((0, context, actor, context), (2, (context + 1) % 4, actor, context))
                        if cycle % 2:
                            values = tuple(reversed(values))
                        image, audio = scene(values, rng)
                        observations = packets(image, audio, paged.clock + .1, paged.base.steps * 2)
                        left, right = resident.step(observations, .1), paged.step(observations, .1)
                        matched += int(left == right and len(right['events']) == 2)
                        maximum_hot = max(maximum_hot, len(memory.cache))
                        budget.check(paged.base.steps)
            weights_equal = equal_weights(resident, paged)
            recovered = 0
            for index, trace in enumerate(memory.traces):
                cue = resident.memory.blocks[index].addresses[1].flatten().clone()
                cue.reshape(4, 4)[1].zero_()
                window = (trace.started, trace.ended)
                left = resident.memory.read(cue, resident.clock, window=window)
                right = memory.read(cue, paged.clock, window=window)
                recovered += int(left == right and right['known'][1])
            save(output / 'session.pt', paged)
            resumed = load(output / 'session.pt')
            cleanup.callback(resumed.memory.close)
            image, audio = scene(((2, 1, 0, 0), (0, 0, 0, 0)), rng)
            observations = packets(image, audio, paged.clock + .1, paged.base.steps * 2)
            resumed_equal = paged.step(observations, .1) == resumed.step(observations, .1)
            resumed_equal &= all(
                torch.equal(value, resumed.memory.block(index).state_dict()[name])
                for index in range(memory.count) for name, value in memory.block(index).state_dict().items())
            trace = memory.traces[0]
            cue = memory.pool['addresses'][0, 1].flatten().clone()
            cue.reshape(4, 4)[1].zero_()
            for bank in memory.block(0).banks:
                bank.weights.zero_()
            erased = memory.read(cue, paged.clock, window=(trace.started, trace.ended))
            report.update(completed=True, frames_equal=matched, frames=48, tracks=len(paged.tracks),
                          episodes=memory.count, archived_recalls=recovered, recalls_tested=len(resident.memory.traces),
                          max_hot_pages=maximum_hot, cold_loads=memory.loads, weights_equal=weights_equal,
                          resume_next_frame_equal=resumed_equal, erased_weights_remove_facts=erased['recall'] is None,
                          seconds=time.perf_counter() - started, process=memory_usage())
            report['accepted'] = matched == 48 and len(paged.tracks) == 32 and weights_equal and recovered == len(resident.memory.traces) and maximum_hot <= 2 and resumed_equal and erased['recall'] is None
        return report
    except (Exception, KeyboardInterrupt) as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        write_report(output / 'report.json', report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=17)
    args = parser.parse_args()
    report = run(args.checkpoint, args.output, args.seed)
    print(json.dumps({'accepted': report['accepted'], 'output': str(args.output.resolve())}))
    if not report['accepted']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
