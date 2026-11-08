"""Controlled model refusal followed by a human word reply to the same memory."""
import argparse
import copy
import time
from pathlib import Path

import torch
from torch.nn import functional as F

from .conceptual_mind import save
from .continuous_experiment import load_scheduler
from .language_process import LanguageProcess
from .native_sensor import NativeObservation
from .persistent_runtime import close_agent, configure_language
from .reactivation_index import source_digest
from .runtime_store import RuntimeStore, atomic_json, digest


def run(checkpoint, output, endpoint, model):
    output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(1)
    original_hash = digest(checkpoint)
    core, mind, _ = load_scheduler(checkpoint)
    report = {'integration_passed': False, 'scope': 'supplied clarification protocol; synthetic perceptions; human single-word reply',
              'live_sensors': False, 'curiosity_is_learned': False, 'new_model_downloaded': False}
    workers = []
    try:
        configure_language(core, endpoint, model)
        def factory(operation):
            worker = LanguageProcess(operation, output / 'workers', 90.,
                environment={'ALICE_EXPERIMENT_RAM_FRACTION': '.9'}, retain_files=True)
            workers.append(worker)
            return worker
        core.agent.worker_factory = factory
        native = core.native
        native.attention.configure('full')
        names, sources, proofs = native.names.copy(), copy.deepcopy(native.sources), copy.deepcopy(native.naming_proofs)
        banks = [source_digest(block).clone() for block in mind.actor.session.memory.blocks]
        old_writers = {modality: bank.weights[:, :len(names)].clone() for modality, bank in native.writers.items()}
        before = {'observations': native.observations, 'lifetime': native.moments.next_id, 'sources': len(sources)}
        def perceive(axis):
            core.tick(.1)
            sequence = max((item['sequence'] for item in native.last.values()), default=-1) + 1
            packets = [NativeObservation(modality, F.one_hot(torch.tensor(axis + offset), 128).float(),
                core.clock, sequence, 'c' * 64) for offset, modality in enumerate(('image', 'audio'))]
            core.observe_native(packets)
            return packets
        original = perceive(90)
        number = core.submit_native_name('Esse barulho é chuva.')
        deadline = time.monotonic() + 120.
        while core.native_namings.jobs[number]['status'] not in core.native_namings.terminal:
            if time.monotonic() > deadline:
                raise TimeoutError('Clarification probe deadline exceeded.')
            core.tick(.05)
            time.sleep(.01)
        refusal = copy.deepcopy(core.native_namings.jobs[number])
        assert refusal['status'] == 'failed' and len(native.sources) == len(sources)
        clarification = core.native_name_clarification(number)
        assert clarification is not None and clarification['focus'] == 'audio'
        core.tick(31.)
        current = perceive(92)
        reply_at = core.clock
        worker_count = len(workers)
        learning = core.reply_native_name(number, 'Chuva')
        assert len(workers) == worker_count
        assert native.recognize(original[1])['name'] == 'chuva'
        assert native.recognize(current[1])['supported'] is False
        assert native.evoke('chuva', 'image')['supported'] is False
        assert native.sources[-1]['acquired_at'] == reply_at
        assert native.naming_proofs[-1]['moment_ref'] == refusal['moment_ref']
        assert native.naming_proofs[-1]['language']['kind'] == 'external_word_reply'
        assert native.names[:len(names)] == names and native.sources[:-1] == sources and native.naming_proofs[:-1] == proofs
        assert all(torch.equal(old_writers[modality], bank.weights[:, :len(names)]) for modality, bank in native.writers.items())
        assert all(torch.equal(old, source_digest(block)) for old, block in zip(banks, mind.actor.session.memory.blocks))
        assert native.observations == before['observations'] + 4 and native.moments.next_id == before['lifetime'] + 2
        with RuntimeStore(output / 'runtime') as store:
            for _ in range(2):
                store.submit(store.capture(core), core.clock)
                assert store.finish()['status'] == 'committed'
        assert digest(checkpoint) == original_hash
        report.update(integration_passed=True, refusal=refusal, clarification=clarification,
            learning=learning, reply_word='Chuva', reply_at=reply_at, before=before,
            observations=native.observations, lifetime=native.moments.next_id,
            old_banks_preserved=len(banks), model_calls_for_reply=0,
            workers_terminal=all(worker.process.poll() is not None for worker in workers))
    finally:
        save(output / 'final.pt', core)
        close_agent(core, mind)
        atomic_json(output / 'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--model', default='qwen3.5:0.8b-q8_0')
    args = parser.parse_args()
    report = run(args.checkpoint, args.output, args.endpoint, args.model)
    print({key: report.get(key) for key in ('integration_passed', 'observations', 'old_banks_preserved', 'model_calls_for_reply')})
    raise SystemExit(0 if report['integration_passed'] else 1)


if __name__ == '__main__':
    main()
