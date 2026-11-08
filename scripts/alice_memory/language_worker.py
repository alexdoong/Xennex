"""One bounded language I/O operation; owns no neural mind or sensor state."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .episodic_language import write_report
from .language import AdmissionDeferred, LocalLanguage, MemoryEvidence
from .language_input import LanguageInput, references
from .expectation_protocol import ExpectationEvidence, ExpectationLanguage


def read_operation(path: Path) -> dict:
    if path.stat().st_size > 32768:
        raise ValueError("Language operation exceeds its input budget.")
    value = json.loads(path.read_text(encoding="utf-8"))
    fields = {"format", "token", "stage", "endpoint", "model", "question", "view", "required", "evidence"}
    if not isinstance(value, dict) or set(value) != fields or type(value["format"]) is not int or value["format"] != 1:
        raise ValueError("Invalid language operation fields.")
    token = value["token"]
    if not isinstance(token, str) or len(token) != 32 or any(char not in "0123456789abcdef" for char in token):
        raise ValueError("Invalid language operation token.")
    if value["stage"] not in ("parse", "expression", "expectation", "lesson", "concept_parse", "concept_expression", "native_parse", "native_expression", "interpretation_parse", "context_report_parse", "meaning_parse", "meaning_expression", "reference_parse", "reference_expression", "feedback_parse", "name_parse", "dialogue") or value["view"] not in ("initial", "current"):
        raise ValueError("Invalid language operation stage/view.")
    if value['stage'] in ('feedback_parse', 'name_parse', 'dialogue'):
        from .native_feedback_language import message_valid
        message_valid(value['question'])
    else:
        references(value["question"])
    required = value["required"]
    if not isinstance(required, list) or len(required) > 4 or any(item not in ("atividade", "impressao", "autor", "contexto") for item in required) or len(set(required)) != len(required):
        raise ValueError("Invalid required language attributes.")
    if not isinstance(value["evidence"], list) or len(value["evidence"]) > 8:
        raise ValueError("Invalid operation evidence.")
    if value['stage'] == 'dialogue':
        from .dialogue_language import validate_context
        if value['view'] != 'current' or required or len(value['evidence']) != 1:
            raise ValueError('Dialogue requires exactly one bounded owner context.')
        validate_context(value['evidence'][0], value['question'])
        return value
    if value["stage"] in ("parse", "lesson", "concept_parse") and (value["evidence"] or required):
        raise ValueError("Parser cannot receive evidence or expected fields.")
    if value['stage'] in ('feedback_parse', 'name_parse'):
        if value['view'] != 'current' or required or value['evidence']:
            raise ValueError('Feedback parser cannot receive memory values or expected reactions.')
        return value
    if value['stage'] in ('interpretation_parse', 'context_report_parse'):
        if value['view'] != 'current' or required or value['evidence']:
            raise ValueError('Native statement parser cannot receive retained beliefs/evidence.')
        return value
    if value['stage'] in ('reference_parse', 'reference_expression'):
        if value['view'] != 'current' or required or (value['stage'] == 'reference_parse' and value['evidence']):
            raise ValueError('Referenced parser cannot receive owner context or memory.')
        if value['stage'] == 'reference_expression':
            from .reference_language import validate_evidence, sha
            if len(value['evidence']) != 1 or validate_evidence(value['evidence'][0])['query_sha256'] != sha(value['question']):
                raise ValueError('Referenced expression changed its question/evidence.')
        return value
    if value['stage'] in ('meaning_parse', 'meaning_expression'):
        if value['view'] != 'current' or required or (value['stage'] == 'meaning_parse' and value['evidence']):
            raise ValueError('Meaning parser cannot receive memory evidence.')
        if value['stage'] == 'meaning_expression':
            from .native_meaning_language import sha, validate_evidence
            if len(value['evidence']) != 1 or validate_evidence(value['evidence'][0])['query_sha256'] != sha(value['question']):
                raise ValueError('Meaning expression changed its original question/evidence.')
        return value
    if value['stage'] in ('native_parse', 'native_expression'):
        if value['view'] != 'current' or required or (value['stage'] == 'native_parse' and value['evidence']):
            raise ValueError('Native parser cannot receive memory evidence.')
        if value['stage'] == 'native_expression':
            from .native_query_language import sha, validate_evidence
            if len(value['evidence']) != 1 or validate_evidence(value['evidence'][0])['query_sha256'] != sha(value['question']):
                raise ValueError('Native expression changed its original question/evidence.')
        return value
    if value['stage'] in ('concept_parse', 'concept_expression'):
        if value['view'] != 'current' or required:
            raise ValueError("Conceptual query cannot assert dated episodic attributes.")
        if value['stage'] == 'concept_expression':
            from .concept_query_language import sha, validate_evidence
            if len(value['evidence']) != 1:
                raise ValueError("Conceptual expression requires one learned deduction.")
            evidence = validate_evidence(value['evidence'][0])
            if evidence['query_sha256'] != sha(value['question']):
                raise ValueError("Conceptual expression changed its original query.")
        return value
    if value["stage"] == "expectation":
        if value["view"] != "current" or len(required) > 1 or len(value["evidence"]) > 1:
            raise ValueError("Expectation worker cannot receive dated or multiple facts.")
        items = []
        for item in value["evidence"]:
            from dataclasses import fields
            if not isinstance(item, dict) or set(item) != {field.name for field in fields(ExpectationEvidence)}:
                raise ValueError("Invalid expectation worker evidence fields.")
            evidence = ExpectationEvidence(**item)
            evidence.validate()
            if required != [evidence.target]:
                raise ValueError("Expectation evidence changed the requested field.")
            items.append(evidence)
        value["evidence"] = tuple(items)
        return value
    items = []
    for item in value["evidence"]:
        if not isinstance(item, dict) or set(item) != {"source", "interpretation", "attributes", "confidence"}:
            raise ValueError("Invalid operation evidence fields.")
        evidence = MemoryEvidence(item["source"], item["interpretation"], tuple(tuple(pair) for pair in item["attributes"]), item["confidence"])
        evidence.validate()
        items.append(evidence)
    value["evidence"] = tuple(items)
    return value


def execute(operation: dict, language_factory=None, ram_fraction=.75) -> dict:
    if language_factory is None:
        language_class = ExpectationLanguage if operation["stage"] == "expectation" else LocalLanguage
        language_factory = lambda *args, **kwargs: language_class(*args, **kwargs, ram_fraction=ram_fraction)
    language = language_factory(operation["endpoint"], operation["model"], timeout=90, wait_seconds=0)
    result = {"format": 1, "token": operation["token"], "stage": operation["stage"], "status": "failed", "value": None}
    try:
        if operation["stage"] == "parse":
            value = LanguageInput(language).parse(operation["question"])
        elif operation['stage'] == 'dialogue':
            from .dialogue_language import DialogueLanguage
            value = DialogueLanguage(language).express(operation['question'], operation['evidence'][0])
        elif operation["stage"] == "lesson":
            from .concept_language import ConceptLanguage
            value = ConceptLanguage(language).parse(operation["question"])
        elif operation['stage'] == 'feedback_parse':
            from .native_feedback_language import FeedbackLanguage
            value = FeedbackLanguage(language).parse(operation['question'])
        elif operation['stage'] == 'name_parse':
            from .native_name_language import NativeNameLanguage
            value = NativeNameLanguage(language).parse(operation['question'])
        elif operation['stage'] == 'interpretation_parse':
            from .native_statement_language import NativeStatementLanguage
            value = NativeStatementLanguage(language).parse(operation['question'])
        elif operation['stage'] == 'context_report_parse':
            from .context_report_language import ContextReportLanguage
            value = ContextReportLanguage(language).parse(operation['question'])
        elif operation['stage'] in ('reference_parse', 'reference_expression'):
            from .reference_language import ReferenceLanguage
            bridge = ReferenceLanguage(language)
            value = bridge.parse(operation['question']) if operation['stage'] == 'reference_parse' else bridge.express(operation['evidence'][0])
        elif operation['stage'] in ('meaning_parse', 'meaning_expression'):
            from .native_meaning_language import NativeMeaningLanguage
            bridge = NativeMeaningLanguage(language)
            value = bridge.parse(operation['question']) if operation['stage'] == 'meaning_parse' else bridge.express(operation['evidence'][0])
        elif operation['stage'] in ('native_parse', 'native_expression'):
            from .native_query_language import NativeQueryLanguage
            bridge = NativeQueryLanguage(language)
            value = bridge.parse(operation['question']) if operation['stage'] == 'native_parse' else bridge.express(operation['evidence'][0])
        elif operation['stage'] in ('concept_parse', 'concept_expression'):
            from .concept_query_language import ConceptQueryLanguage
            bridge = ConceptQueryLanguage(language)
            value = bridge.parse(operation['question']) if operation['stage'] == 'concept_parse' else bridge.express(operation['evidence'][0])
        elif operation["stage"] == "expectation":
            value = language.propose_expectation(operation["question"], operation["evidence"][0] if operation["evidence"] else None)
        else:
            value = language.propose(operation["question"], operation["evidence"], operation["view"], tuple(operation["required"]))
        result.update(status="ready", value=asdict(value))
    except AdmissionDeferred as error:
        result.update(status="deferred", value={"reason": str(error), "used_bytes": error.used_bytes,
                                                "total_bytes": error.total_bytes, "reserve_bytes": error.reserve_bytes,
                                                "ram_fraction": error.ram_fraction})
    except (OSError, RuntimeError, ValueError) as error:
        result["value"] = {"reason": str(error)[:2048]}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    operation = read_operation(args.request)
    import os
    fraction = float(os.environ.get('ALICE_EXPERIMENT_RAM_FRACTION', '.75'))
    write_report(args.output, execute(operation, ram_fraction=fraction))


if __name__ == "__main__":
    main()
