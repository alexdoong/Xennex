"""Compare installed expression organs with identical owner evidence; no new sensing."""
import argparse
import copy
import json
from dataclasses import asdict
from pathlib import Path

import torch

from .continuous_experiment import load_scheduler
from .dialogue_language import DialogueLanguage
from .language import LocalLanguage
from .native_meaning_query import resolve_reference
from .persistent_runtime import close_agent
from .runtime_store import atomic_json, digest
from .concept_query_language import evidence_hash, sha


def cases(core):
    parents = [record for record in core.interactions.records.values() if record['request']['action'] == 'relate' and record['status'] == 'completed']
    if len(parents) != 1:
        raise ValueError('Comparison requires one contextual reporting topic.')
    parent = parents[0]
    source = core.interactions.report_source(parent['request']['id'])
    binding = {'version': source['id'], 'moment_ref': copy.deepcopy(source['moment_ref']),
               'relation': core.native.interpretations.relations[source['relation']]}
    values = []
    tests = [('current', 'Quem é o dono dessa imagem atualmente?', True, False, []),
             ('initial', 'No primeiro relato, quem era o dono dessa imagem?', True, False, []),
             ('erased', 'Quem é o dono dessa imagem atualmente?', True, True, []),
             ('erased_with_generated_history', 'Quem é o dono dessa imagem atualmente?', True, True,
              [{'question': 'Quem fez?', 'reply': 'Foi a mãe.', 'origin': 'self_generated_response'}]),
             ('topic_after_distraction', 'Quem é o dono dessa imagem atualmente?', True, False,
              [{'question': 'Vamos conversar sobre formigas?', 'reply': 'Formigas vivem em colônias.', 'origin': 'self_generated_response'}]),
             ('no_live_vision', 'Você está vendo essa imagem agora?', True, False, []),
             ('arithmetic', 'Quanto é dois mais dois? Responde curto.', False, False, []),
             ('informal', 'Oi! Porra, tudo bem? Bora conversar.', False, False, [])]
    saved = core.native.interpretations.bank.weights.clone()
    try:
        for index, (name, question, selected, erased, history) in enumerate(tests):
            core.native.interpretations.bank.weights.copy_(saved)
            if erased:
                core.native.interpretations.bank.weights.zero_()
            memory = None if not selected else resolve_reference(core.native, binding, {'view': 'comparison'}, question)
            context = {'kind': 'dialogue_context', 'input': {'frame': {'stream_id': 'e'*32, 'sequence': index},
                       'sha256': sha(question), 'acquired': False, 'moment_ref': None},
                       'about': parent['request']['id'] if selected else None,
                       'state': {'clock': core.clock, 'attention_mode': core.native.attention.mode,
                                 'perceptions': core.native.observations, 'names': core.native.names.copy()},
                       'memory': memory, 'history': history,
                       'signature': evidence_hash({'fixture': name, 'memory': None if memory is None else memory['signature']})}
            expected = None if memory is None else {view: report['subject'] for view, report in memory['reports'].items()}
            values.append({'name': name, 'question': question, 'context': context, 'expected_owner_values': expected})
    finally:
        core.native.interpretations.bank.weights.copy_(saved)
    return values


def run(checkpoint, output, endpoint, model):
    output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(1)
    checksum = digest(checkpoint)
    core, mind, _ = load_scheduler(checkpoint)
    try:
        dataset = cases(core)
        before = core.native.observations, core.native.moments.next_id
        report = {'protocol_completed': False, 'quality_approved': False, 'manual_review_required': True,
                  'synthetic_input_context': True, 'owner_memory_read_from_weights': True,
                  'fresh_sensory_inference': False, 'live_sensors': False, 'new_model_downloaded': False,
                  'source_sha256': checksum, 'model': model, 'cases': []}
        language = DialogueLanguage(LocalLanguage(endpoint, model, timeout=90, wait_seconds=0, ram_fraction=.9))
        for case in dataset:
            item = copy.deepcopy(case)
            try:
                item['proposal'] = asdict(language.express(case['question'], case['context']))
                item['completed'] = True
            except (OSError, RuntimeError, ValueError) as error:
                item.update(completed=False, error=type(error).__name__ + ': ' + str(error)[:2048])
            report['cases'].append(item)
            atomic_json(output / 'report.json', report)
        if (core.native.observations, core.native.moments.next_id) != before or digest(checkpoint) != checksum:
            raise RuntimeError('Language comparison changed source experiences.')
        report.update(protocol_completed=all(item['completed'] for item in report['cases']), source_unchanged=True,
                      completed=sum(item['completed'] for item in report['cases']), total=len(dataset))
        atomic_json(output / 'report.json', report)
        return report
    finally:
        close_agent(core, mind)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--model', default='qwen3.5:0.8b-q8_0')
    args = parser.parse_args()
    result = run(args.checkpoint, args.output, args.endpoint, args.model)
    print({'model': result['model'], 'completed': result['completed'], 'total': result['total'], 'quality_approved': False})


if __name__ == '__main__': main()
