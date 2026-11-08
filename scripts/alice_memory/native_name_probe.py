"""Small installed LLM names externally perceived synthetic cues; finite copy."""
import argparse
import copy
import time
from dataclasses import asdict
from pathlib import Path

import torch
from torch.nn import functional as F

from .conceptual_mind import save
from .continuous_experiment import load_scheduler
from .language import LocalLanguage
from .language_process import LanguageProcess
from .native_name_language import NativeNameLanguage
from .native_sensor import NativeObservation
from .persistent_runtime import close_agent, configure_language
from .reactivation_index import source_digest
from .runtime_store import RuntimeStore, atomic_json, digest

CASES = (
    ('Isso se chama lumo.', 'lumo', 'unspecified'),
    ('Essa imagem é uma caneca.', 'caneca', 'image'),
    ('Essa foto se chama zuno.', 'zuno', 'image'),
    ('Porra, esse som se chama tavi.', 'tavi', 'audio'),
    ('Esse barulho é chuva.', 'chuva', 'audio'),
    ('Esse texto é lumo.', 'lumo', 'text'),
    ('A palavra escrita é caneca.', 'caneca', 'text'),
    ('O que você está vendo se chama zuno.', 'zuno', 'image'),
    ('O que você está ouvindo se chama tavi.', 'tavi', 'audio'),
    ('Essa imagem é uma caneca?', None, 'unspecified'),
    ('Essa imagem não é uma caneca.', None, 'unspecified'),
    ('Ele disse que essa imagem é uma caneca.', None, 'unspecified'),
    ('Talvez essa imagem seja uma caneca.', None, 'unspecified'),
    ('Essa imagem é caneca ou prato.', None, 'unspecified'),
    ('Gostei dessa imagem.', None, 'unspecified'),
)


class RecordingLanguage(LocalLanguage):
    """Capture public synthetic benchmark proposals, including rejected ones."""
    last_chat = None

    def _request(self, path, body=None):
        result = super()._request(path, body)
        if path == '/api/chat':
            self.last_chat = result.get('message', {}).get('content', '')[:2048]
        return result


def probe(checkpoint, output, endpoint, model):
    output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(1)
    backend = RecordingLanguage(endpoint, model, ram_fraction=.9, wait_seconds=15)
    language = NativeNameLanguage(backend)
    source_hash = digest(checkpoint)
    report = {'accepted': False, 'scope': 'direct naming in Portuguese; synthetic perceived cues, not daily objects',
              'cases': [], 'jobs': [], 'live_sensors': False, 'new_model_downloaded': False}
    core = mind = None
    workers = []
    try:
        for message, expected, modality in CASES:
            backend.last_chat = None
            case = {'message': message, 'expected_name': expected, 'expected_modality': modality, 'correct': False}
            try:
                plan = asdict(language.parse(message))
                case['plan'] = plan
                case['correct'] = plan['name_fragment'] == expected and plan['modality'] == modality and plan['uncertain'] == (expected is None)
            except (OSError, RuntimeError, ValueError) as error:
                case['error'] = str(error)
            case['raw_proposal'] = backend.last_chat
            report['cases'].append(case)
            atomic_json(output / 'report.json', report)
        core, mind, _ = load_scheduler(checkpoint)
        configure_language(core, endpoint=endpoint, model=model)
        def factory(operation):
            worker = LanguageProcess(operation, output / 'workers', 90.,
                environment={'ALICE_EXPERIMENT_RAM_FRACTION': '.9'}, retain_files=True)
            workers.append(worker)
            return worker
        core.agent.worker_factory = factory
        native = core.native
        native.attention.configure('full')
        names, sources = native.names.copy(), copy.deepcopy(native.sources)
        old_writers = {modality: bank.weights[:, :len(names)].clone() for modality, bank in native.writers.items()}
        old_banks = [source_digest(block).clone() for block in mind.actor.session.memory.blocks]
        reports = copy.deepcopy(native.interpretations.records)
        before = {'observations': native.observations, 'sources': len(native.sources), 'lifetime': native.moments.next_id}
        trials = [(('image', 'audio'), 80, 'Porra, essa imagem se chama lumo.', 'completed', 'image', 'lumo'),
                  (('image', 'audio'), 82, 'Esse som se chama tavi.', 'completed', 'audio', 'tavi'),
                  (('image',), 84, 'Isso se chama zuno.', 'completed', 'image', 'zuno'),
                  (('image', 'audio'), 85, 'Isso se chama feno.', 'failed', None, None),
                  (('image', 'audio'), 87, 'Essa imagem se chama feno?', 'uncertain', None, None)]
        for modalities, axis, message, expected, target, name in trials:
            core.tick(.1)
            sequence = max((record['sequence'] for record in native.last.values()), default=-1) + 1
            packets = [NativeObservation(modality, F.one_hot(torch.tensor(axis+offset),128).float(),core.clock,
                sequence, 'a'*64) for offset, modality in enumerate(modalities)]
            core.observe_native(packets)
            perception_count = native.observations
            number = core.submit_native_name(message)
            deadline = time.monotonic() + 120.
            while core.native_namings.jobs[number]['status'] not in core.native_namings.terminal:
                if time.monotonic() > deadline:
                    raise TimeoutError('Naming trial deadline exceeded.')
                core.tick(.05)
                time.sleep(.01)
            job = core.take_native_name(number)
            report['jobs'].append(job)
            assert job['status'] == expected, job
            assert native.observations == perception_count
            if target:
                cue = next(packet for packet in packets if packet.modality == target)
                assert native.recognize(cue)['name'] == name
                perturbed = F.normalize(cue.latent + .01*F.one_hot(torch.tensor(95),128).float(),dim=0)
                held = NativeObservation(target,perturbed,core.clock,0,'b'*64,origin='self')
                assert native.recognize(held)['name'] == name
                for other in modalities:
                    if other != target:
                        assert native.evoke(name, other)['supported'] is False
            atomic_json(output / 'report.json',report)
        assert native.names[:len(names)] == names and native.sources[:len(sources)] == sources
        assert native.interpretations.records == reports
        assert all(torch.equal(old_writers[modality],bank.weights[:,:len(names)]) for modality,bank in native.writers.items())
        assert all(torch.equal(old,source_digest(block)) for old,block in zip(old_banks,mind.actor.session.memory.blocks))
        assert len(native.sources)==len(sources)+3 and len(native.naming_proofs)==3
        with RuntimeStore(output/'runtime') as store:
            for _ in range(2):
                store.submit(store.capture(core),core.clock)
                assert store.finish()['status']=='committed'
        assert digest(checkpoint)==source_hash
        report.update(correct=sum(case['correct'] for case in report['cases']),total=len(CASES),before=before,
            new_named_sources=3, new_naming_proofs=3,old_banks_preserved=len(old_banks),source_checkpoint_unchanged=True,
            native_observations=native.observations,native_lifetime=native.moments.next_id,
            workers_terminal=all(worker.process.poll() is not None for worker in workers),
            accepted=all(case['correct'] for case in report['cases']))
    finally:
        if core is not None:
            save(output/'final.pt',core)
            close_agent(core,mind)
        atomic_json(output/'report.json',report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--endpoint',required=True)
    parser.add_argument('--model',default='qwen3.5:0.8b-q8_0')
    args=parser.parse_args()
    report=probe(args.checkpoint,args.output,args.endpoint,args.model)
    print({key:report.get(key) for key in ('accepted','correct','total','new_named_sources')})
    raise SystemExit(0 if report['accepted'] else 1)


if __name__=='__main__':
    main()
