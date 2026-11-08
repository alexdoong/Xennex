"""Explicit test-only language backend for delay, refusal and malformed output."""
import argparse
import hashlib
import json
import os
import time
from dataclasses import asdict
from pathlib import Path

from scripts.alice_memory.episodic_language import write_report
from scripts.alice_memory.language import LanguageProposal
from scripts.alice_memory.language_input import QuestionPlan, references
from scripts.alice_memory.language_worker import read_operation
from scripts.alice_memory.expectation_protocol import ExpectationProposal


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(Path(os.environ["ALICE_FAKE_LANGUAGE_CONFIG"]).read_text(encoding="utf-8"))
    delay = config.get("delay", 0.)
    if not 0 <= delay <= 5:
        raise ValueError("Test delay must be finite and bounded.")
    operation = read_operation(args.request)
    time.sleep(delay)
    mode = config.get("mode", "normal")
    if mode == "no_result":
        return
    if mode == "oversized":
        args.output.write_text("x" * 65537, encoding="utf-8")
        return
    result = {"format": 1, "token": operation["token"], "stage": operation["stage"], "status": "ready", "value": None}
    if mode == "deferred":
        result.update(status="deferred", value={"reason": "fixture resource pressure"})
    elif operation['stage'] == 'name_parse':
        from scripts.alice_memory.native_name_language import NativeNamePlan, guarded, sha
        unclear = guarded(operation['question']) or mode == 'name_uncertain'
        result['value'] = asdict(NativeNamePlan(None if unclear else config.get('name_fragment', 'lumo'),
            'unspecified' if unclear else config.get('name_modality', 'image'), unclear,
            operation['model'], 'fixture-digest', sha(operation['question']), '4' * 64, delay))
        if mode == 'invent_claim':
            result['value']['name_fragment'] = 'invented'
    elif operation['stage'] == 'reference_parse':
        from scripts.alice_memory.reference_language import ReferencePlan, perspective, sha
        view = perspective(operation['question'])
        result['value'] = asdict(ReferencePlan(view, view == 'uncertain', operation['model'], 'fixture-digest',
            sha(operation['question']), '4'*64, delay))
        if mode == 'invent_claim':
            result['value']['view'] = 'comparison' if view != 'comparison' else 'initial'
            result['value']['uncertain'] = False
    elif operation['stage'] == 'reference_expression':
        from scripts.alice_memory.reference_language import ReferenceExpression, phrases, evidence_hash
        evidence = operation['evidence'][0]
        text = phrases(evidence)[0] if mode != 'invent_claim' else 'Eu vi sua mãe.'
        result['value'] = asdict(ReferenceExpression(text, operation['model'], 'fixture-digest', evidence_hash(evidence), '5'*64, delay))
    elif operation['stage'] == 'meaning_parse':
        from scripts.alice_memory.native_meaning_language import NativeMeaningPlan, parts, sha
        draft = parts(operation['question'])
        result['value'] = asdict(NativeMeaningPlan(**draft, model=operation['model'], model_digest='fixture-digest',
            question_sha256=sha(operation['question']), prompt_sha256='4' * 64, wall_seconds=delay))
        if mode == 'invent_claim' and not draft['uncertain']:
            result['value']['relation'] = 'invented'
    elif operation['stage'] == 'meaning_expression':
        from scripts.alice_memory.native_meaning_language import NativeMeaningExpression, phrases, evidence_hash
        evidence = operation['evidence'][0]
        text = phrases(evidence)[0] if mode != 'invent_claim' else 'Eu vi seu pai cozinhar.'
        result['value'] = asdict(NativeMeaningExpression(text, operation['model'], 'fixture-digest', evidence_hash(evidence), '5' * 64, delay))
    elif operation['stage'] == 'context_report_parse':
        from scripts.alice_memory.context_report_language import LEGACY_REPORT_KIND, REPORT_KIND, ContextReportPlan, parts, sha
        kind = LEGACY_REPORT_KIND if mode == 'legacy_context_report' else REPORT_KIND
        draft = parts(operation['question'], kind=kind)
        result['value'] = asdict(ContextReportPlan(**draft, model=operation['model'], model_digest='fixture-digest',
            message_sha256=sha(operation['question']), prompt_sha256='4' * 64, wall_seconds=delay, kind=kind))
        if mode == 'invent_claim' and not draft['uncertain']:
            result['value']['subject_fragment'] = 'invented'
    elif operation['stage'] == 'interpretation_parse':
        from scripts.alice_memory.native_statement_language import NativeStatementPlan, parts, sha
        draft = parts(operation['question'])
        result['value'] = asdict(NativeStatementPlan(**draft, model=operation['model'], model_digest='fixture-digest',
            message_sha256=sha(operation['question']), prompt_sha256='4' * 64, wall_seconds=delay))
        if mode == 'invent_claim' and not draft['uncertain']:
            result['value']['subject'] = 'invented'
    elif operation['stage'] == 'native_parse':
        from scripts.alice_memory.native_query_language import NativeQueryPlan, literal_parts, sha
        names, modalities, windows, unclear = literal_parts(operation['question'])
        uncertain = unclear or mode == 'query_uncertain'
        basis = 'utc' if 'UTC' in operation['question'] else 'relative'
        result['value'] = asdict(NativeQueryPlan(None if uncertain else names[0], [] if uncertain else modalities,
            None if uncertain or not windows else windows[0], 'relative' if uncertain else basis, uncertain,
            operation['model'], 'fixture-digest', sha(operation['question']), '4' * 64, delay))
        if mode == 'invent_claim' and not uncertain:
            result['value']['name'] = 'invented'
    elif operation['stage'] == 'native_expression':
        from scripts.alice_memory.native_query_language import NativeExpression, phrases, evidence_hash
        evidence = operation['evidence'][0]
        text = phrases(evidence)[0]
        if mode in ('invent_claim', 'native_bad_expression'):
            text = 'Lembro que seu pai estava cozinhando.'
        result['value'] = asdict(NativeExpression(text, operation['model'], 'fixture-digest', evidence_hash(evidence), '5' * 64, delay))
    elif operation['stage'] == 'dialogue':
        from scripts.alice_memory.dialogue_language import DialogueExpression
        from scripts.alice_memory.concept_query_language import evidence_hash
        from scripts.alice_memory.dialogue_recall import memory as selected_memory
        memory = selected_memory(operation['evidence'][0])
        subject = None if memory is None else memory['reports']['current']['subject']
        text = config.get('dialogue_text', 'Oi, vamos conversar.' if subject is None else 'O relato atual aponta para ' + subject + '.')
        value = asdict(DialogueExpression(text, operation['model'], 'fixture', evidence_hash(operation['evidence'][0]), 'a'*64, .1))
        result['value'] = value
    elif operation['stage'] == 'feedback_parse':
        from scripts.alice_memory.native_feedback_language import FeedbackPlan, guarded, sha
        reaction = config.get('reaction', 'discouraging' if 'não gostei' in operation['question'].lower() else 'encouraging')
        if guarded(operation['question']) or mode == 'feedback_uncertain':
            reaction = 'uncertain'
        result['value'] = asdict(FeedbackPlan(reaction, operation['model'], 'fixture-digest',
            sha(operation['question']), '7' * 64, delay))
        if mode == 'invent_claim':
            result['value']['message_sha256'] = '8' * 64
    elif operation['stage'] == 'concept_parse':
        from scripts.alice_memory.concept_query_language import ConceptQueryPlan, literal_vectors, sha
        names, pairs = references(operation['question']), literal_vectors(operation['question'])
        uncertain = not names or len(pairs) != 1 or mode == 'query_uncertain'
        result['value'] = asdict(ConceptQueryPlan([] if uncertain else names, None if uncertain else pairs[0].group(),
                               uncertain, operation['model'], 'fixture-digest', sha(operation['question']), '4' * 64, delay))
        if mode == 'invent_claim' and not uncertain:
            result['value']['input_fragment'] = '(63, 63)'
    elif operation['stage'] == 'concept_expression':
        from scripts.alice_memory.concept_query_language import ConceptExpression, evidence_hash
        evidence = operation['evidence'][0]
        vector = '(' + ', '.join(format(item, '.6f') for item in evidence['value']) + ')'
        text = 'Com a regra que aprendi, o resultado aproximado é ' + vector + '.'
        if mode == 'invent_claim':
            text = 'O resultado é (63, 63).'
        result['value'] = asdict(ConceptExpression(text, operation['model'], 'fixture-digest',
                                                 evidence_hash(evidence), '5' * 64, delay))
    elif operation["stage"] == "lesson":
        from scripts.alice_memory.concept_language import LessonPlan
        import re
        pairs = re.findall(r'\([^()]+\)', operation['question'])
        names = references(operation['question'])
        uncertain = len(names) != 1 or len(pairs) != 2 or mode == 'lesson_uncertain'
        draft = LessonPlan(None if uncertain else names[0], None if uncertain else pairs[0],
                           None if uncertain else pairs[1], uncertain, operation['model'], 'fixture-digest',
                           hashlib.sha256(operation['question'].encode()).hexdigest(), '3' * 64, delay)
        result['value'] = asdict(draft)
        if mode == 'invent_claim' and not uncertain:
            result['value']['output_fragment'] = '(63, 63)'
    elif operation["stage"] == "parse":
        names = references(operation["question"])
        field = "impressao" if "impress" in operation["question"].casefold() else ("autor" if names else "unknown")
        plan = QuestionPlan(field, tuple(names), not names, operation["model"], "fixture-digest",
                            hashlib.sha256(operation["question"].encode()).hexdigest(), "1" * 64, delay)
        result["value"] = asdict(plan)
    elif operation["stage"] == "expectation":
        evidence = asdict(operation["evidence"][0]) if operation["evidence"] else None
        expected = {} if evidence is None else {evidence["target"]: evidence["value"]}
        if mode == "invent_claim":
            expected["autor"] = "unsupported person"
        factual = {"autor": "pai"} if mode == "expectation_as_fact" else {}
        draft = ExpectationProposal("Eu esperaria esse padrão." if expected else "Não sei.", expected, factual,
                                    not expected, True, (), operation["model"], "fixture-digest",
                                    hashlib.sha256(json.dumps(evidence, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
                                    "2" * 64, delay)
        result["value"] = asdict(draft)
    else:
        evidence = [asdict(item) for item in operation["evidence"]]
        available = {key: value for item in evidence for key, value in item["attributes"]}
        claims = {key: available[key] for key in operation["required"] if key in available}
        if mode == "invent_claim":
            claims["autor"] = "unsupported person"
        text = "; ".join(key + "=" + value for key, value in claims.items()) or "Não sei."
        draft = LanguageProposal(text, claims, not claims, True, (), operation["model"], "fixture-digest",
                                 hashlib.sha256(json.dumps(evidence, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
                                 "2" * 64, delay)
        result["value"] = asdict(draft)
    if mode == "wrong_token":
        result["token"] = "0" * 32
    write_report(args.output, result)


if __name__ == "__main__":
    main()
