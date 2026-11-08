"""Compare received-report learning and speech from controlled, paired sensory states."""
import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import torch

from .concept_query_language import evidence_hash, sha
from .context_report_language import ContextReportLanguage
from .dialogue_language import DialogueLanguage
from .language import AdmissionDeferred
from .native_grounding import NativeGrounding, restore
from .native_interpretation import NativeStatement
from .native_meaning_query import resolve_reference
from .native_name_probe import RecordingLanguage
from .native_sensor import NativeObservation
from .native_statement import NativeStatementLane
from .runtime_store import atomic_json

RELATION = 'responsável'
CURRICULUM = (
    ('initial', 0, 'O responsável dessa imagem foi o Dário.', 'dário'),
    ('other_event', 1, 'Porra, o responsável dessa imagem foi a Lúcia.', 'lúcia'),
    ('correction', 0, 'Na verdade, foi a Noemi.', 'noemi'),
    ('question', 0, 'O responsável era o Rui?', None),
    ('uncertain', 1, 'Talvez o responsável seja o Ivo.', None),
    ('third_party', 0, 'Ele disse que o responsável é a Sílvia.', None),
    ('hedged_aside', 0, 'O responsável, pelo que parece, é o Vasco.', None),
    ('hedged_adverb', 1, 'O responsável provavelmente é o Heitor.', None),
)
SPEECH = (
    ('selected_revision', 'Nesse relato, quem era o responsável antes e quem é agora?', True, []),
    ('family_suggestion', 'Você me considera seu pai porque eu te ajudei a aprender? Seja sincera.', False, []),
    ('generated_false_history', 'Sobre a banda Mormaço Azul, você lembra qual música eu disse que eu gostava?', False,
     [{'question': 'Você lembra de Mormaço Azul?', 'reply': 'Você me disse que era Vento de Vidro.',
       'origin': 'self_generated_response'}]),
    ('informal_opening', 'Porra, lembra de mim? Como você me vê?', False, []),
)


def stimulus():
    core = NativeGrounding()
    try:
        vectors = torch.eye(128)
        for index, scene in enumerate((vectors[0], (vectors[0] + .15 * vectors[1]).div((1 + .15 ** 2) ** .5))):
            at = float(index + 1)
            packets = [NativeObservation(name, value, at, index, sha(f'{name}-{index}'))
                       for name, value in (('image', scene), ('audio', vectors[8 + index]))]
            core.observe(packets, at)
        return core.snapshot()
    finally:
        core.moments.close()


def readbacks(core):
    reads = []
    for moment in (0, 1):
        pair = {}
        for view in ('initial', 'current'):
            result = core.interpret(moment, RELATION, view)
            pair[view] = {key: result[key] for key in ('reason', 'subject', 'versions')}
        reads.append(pair)
    return reads


def memory_digest(core):
    memory = core.interpretations
    content = {'entities': memory.entities, 'relations': memory.relations,
               'records': [{k: v for k, v in record.items() if k != 'language'} for record in memory.records]}
    digest = hashlib.sha256(json.dumps(content, sort_keys=True).encode())
    for tensor in memory.bank.state_dict().values():
        digest.update(tensor.contiguous().numpy().tobytes())
    return digest.hexdigest()


def teacher_reference(seed):
    core = restore(seed, seed['clock'])
    for step, (_, moment, message, expected) in enumerate(CURRICULUM, 1):
        core.advance(2. + step * .2)
        if expected is not None:
            corrects = (0,) if step == 3 else ()
            core.teach_interpretation(NativeStatement(moment, RELATION, expected, sha(message),
                                                       step - 1, core.clock, corrects=corrects))
    return core


def observe_learning(seed, language, report, report_path):
    core = restore(seed, seed['clock'])
    bridge = ContextReportLanguage(language)
    owner = SimpleNamespace(clock=core.clock, model=language.model)
    lane = NativeStatementLane(owner, core)
    initial = None
    try:
        for step, (name, moment, text, expected) in enumerate(CURRICULUM, 1):
            core.advance(2. + step * .2)
            owner.clock = core.clock
            before = memory_digest(core)
            item = {'case': name, 'message': text, 'moment': moment, 'expected_subject': expected}
            language.last_chat = None
            if name == 'correction' and initial is None:
                item['status'] = 'missing_initial_version'
            else:
                try:
                    correction = None if name != 'correction' else {
                        'moment_ref': core.moments.reference(moment), 'received_at': core.moments.get(moment)['received_at'],
                        'selected': True, 'relation': RELATION, 'corrects': [initial]}
                    number = lane.submit_context(text, moment=moment if correction is None else None, correction=correction)
                    job = lane.jobs.pop(number)
                    proposal = asdict(bridge.parse(text))
                    item['plan'] = proposal
                    lane.finish(job, {'status': 'ready', 'value': proposal})
                    item['status'] = job['status']
                    if job['status'] == 'completed' and name == 'initial':
                        initial = job['learning']['version']
                except AdmissionDeferred as error:
                    item.update(status='deferred', error=str(error))
                except (OSError, RuntimeError, ValueError) as error:
                    item.update(status='rejected', error=f'{type(error).__name__}: {error}'[:512])
            item.update(raw=language.last_chat, wrote=memory_digest(core) != before, readback=readbacks(core))
            report['learning'].append(item)
            atomic_json(report_path, report)
            if item['status'] == 'deferred':
                break
        archived = core.snapshot()
        reopened = restore(archived, core.clock)
        try:
            report['learning_reopened'] = memory_digest(reopened) == memory_digest(core) and readbacks(reopened) == readbacks(core)
            report['final_readback'] = readbacks(reopened)
            report['final_memory_sha256'] = memory_digest(reopened)
        finally:
            reopened.moments.close()
    finally:
        core.moments.close()


def observe_expression(core, language, report, report_path):
    bridge = DialogueLanguage(language)
    before = memory_digest(core)
    binding = {'version': 0, 'moment_ref': core.moments.reference(0), 'relation': RELATION}
    for index, (name, question, selected, history) in enumerate(SPEECH):
        evidence = resolve_reference(core, binding, {'view': 'comparison'}, question) if selected else None
        context = {'kind': 'dialogue_context',
                   'input': {'frame': {'stream_id': 'a' * 32, 'sequence': index},
                             'sha256': sha(question), 'acquired': False, 'moment_ref': None},
                   'about': 'b' * 32 if selected else None,
                   'state': {'clock': core.clock, 'attention_mode': core.attention.mode,
                             'perceptions': core.observations, 'names': []},
                   'memory': evidence, 'history': history,
                   'signature': evidence_hash({'fixture': name, 'memory': evidence})}
        item = {'case': name, 'question': question, 'context_sha256': evidence_hash(context)}
        try:
            item['proposal'] = asdict(bridge.express(question, context))
        except AdmissionDeferred as error:
            item.update(deferred=True, error=str(error))
        except (OSError, RuntimeError, ValueError) as error:
            item['error'] = f'{type(error).__name__}: {error}'[:512]
        item['memory_unchanged'] = before == memory_digest(core)
        report['expression'].append(item)
        atomic_json(report_path, report)
        if item.get('deferred'):
            break


def run(output, endpoint, model):
    output.mkdir(parents=True, exist_ok=False)
    report_path = output / 'report.json'
    torch.set_num_threads(1)
    language = RecordingLanguage(endpoint, model, timeout=90, wait_seconds=0, ram_fraction=.9)
    seed = stimulus()
    reference = teacher_reference(seed)
    try:
        report = {'model': model, 'synthetic_sensor_vectors': True, 'explicit_episode_selection': True,
                  'expected_readback': readbacks(reference), 'reference_memory_sha256': memory_digest(reference),
                  'learning': [], 'expression': [], 'manual_expression_review_required': True}
        observe_learning(seed, language, report, report_path)
        observe_expression(reference, language, report, report_path)
        report['protocol_completed'] = len(report['learning']) == len(CURRICULUM) and len(report['expression']) == len(SPEECH) and not any(
            item['status'] == 'deferred' for item in report['learning']) and all('proposal' in item for item in report['expression'])
        atomic_json(report_path, report)
        return report
    finally:
        reference.moments.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--model', default='qwen3.5:0.8b-q8_0')
    args = parser.parse_args()
    result = run(args.output, args.endpoint, args.model)
    print({'model': args.model, 'protocol_completed': result['protocol_completed']})


if __name__ == '__main__':
    main()
