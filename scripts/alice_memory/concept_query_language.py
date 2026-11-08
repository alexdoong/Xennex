"""Restricted Portuguese queries and numerical expression; no mind in the worker.

Literal references and the vector are grounded to the question. The ordering
contract is written order, not unrestricted temporal language understanding.
Numerical text validation does not certify every proposition in the prose.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from dataclasses import asdict, dataclass, fields

from .concept_language import pair
from .language_input import references


def sha(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def evidence_hash(value):
    return sha(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False))


def provenance(value, model):
    if value['model'] != model or not isinstance(value['model_digest'], str) or not 1 <= len(value['model_digest']) <= 128:
        raise ValueError("Invalid conceptual language model provenance.")
    if not isinstance(value['prompt_sha256'], str) or re.fullmatch(r'[0-9a-f]{64}', value['prompt_sha256']) is None:
        raise ValueError("Invalid conceptual language prompt provenance.")
    elapsed = value['wall_seconds']
    if isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)) or not math.isfinite(elapsed) or not 0 <= elapsed <= 300:
        raise ValueError("Invalid conceptual language duration.")


def literal_vectors(text):
    result = []
    for match in re.finditer(r'\([^()]*\)', text):
        try:
            pair(match.group())
        except ValueError:
            continue
        result.append(match)
    return result


def result_vectors(text):
    result = []
    for match in re.finditer(r'\([^()]*\)|\[[^\[\]]*\]', text):
        try:
            pair('(' + match.group()[1:-1] + ')')
        except ValueError:
            continue
        result.append(match)
    return result


@dataclass(frozen=True)
class ConceptQueryPlan:
    chain: list[str]
    input_fragment: str | None
    uncertain: bool
    model: str
    model_digest: str
    question_sha256: str
    prompt_sha256: str
    wall_seconds: float
    kind: str = 'literal_concept_query'


def validate_plan(value, question, model):
    names = references(question)
    if not isinstance(value, dict) or set(value) != {field.name for field in fields(ConceptQueryPlan)} or value['kind'] != 'literal_concept_query' or type(value['uncertain']) is not bool:
        raise ValueError("Invalid conceptual query fields.")
    provenance(value, model)
    if value['question_sha256'] != sha(question) or not isinstance(value['chain'], list):
        raise ValueError("Conceptual query changed its source.")
    if value['uncertain']:
        if value['chain'] or value['input_fragment'] is not None:
            raise ValueError("Uncertain query cannot assert conceptual premises.")
        return value
    matches = literal_vectors(question)
    if not names or value['chain'] != names or len(matches) != 1 or value['input_fragment'] != matches[0].group():
        raise ValueError("Query requires literal concepts in written order and one literal vector.")
    # Repeated names cannot be represented by references(), which deduplicates.
    quoted = re.findall(r'"([^"\n]+)"|“([^“”\n]+)”', question)
    if len(quoted) != len(names):
        raise ValueError("Repeated conceptual references require a future ordering contract.")
    return value


def validate_evidence(value):
    expected = {'kind', 'chain', 'input', 'value', 'premises', 'query_sha256', 'computed_at'}
    if not isinstance(value, dict) or set(value) != expected or value['kind'] != 'deduced':
        raise ValueError("Invalid conceptual query evidence.")
    chain = value['chain']
    if not isinstance(chain, list) or not 1 <= len(chain) <= 8 or any(not isinstance(item, str) for item in chain) or len(set(chain)) != len(chain):
        raise ValueError("Invalid conceptual evidence chain.")
    if references(' '.join('"' + name + '"' for name in chain)) != chain:
        raise ValueError("Invalid conceptual evidence names.")
    for name in ('input', 'value'):
        vector = value[name]
        if not isinstance(vector, list) or len(vector) != 2 or any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) or abs(item) > 64 for item in vector):
            raise ValueError("Invalid conceptual evidence vector.")
    versions = value['premises']
    if not isinstance(versions, dict) or set(versions) != set(chain) or any(type(item) is not int or not 3 <= item <= 512 for item in versions.values()):
        raise ValueError("Invalid conceptual evidence versions.")
    if not isinstance(value['query_sha256'], str) or re.fullmatch(r'[0-9a-f]{64}', value['query_sha256']) is None:
        raise ValueError("Invalid conceptual evidence source.")
    clock = value['computed_at']
    if isinstance(clock, bool) or not isinstance(clock, (int, float)) or not math.isfinite(clock) or not 0 <= clock <= 1e12:
        raise ValueError("Invalid conceptual evidence time.")
    return value


@dataclass(frozen=True)
class ConceptExpression:
    text: str
    model: str
    model_digest: str
    evidence_sha256: str
    prompt_sha256: str
    wall_seconds: float


def validate_expression(value, evidence, model):
    validate_evidence(evidence)
    if not isinstance(value, dict) or set(value) != {field.name for field in fields(ConceptExpression)}:
        raise ValueError("Invalid conceptual expression fields.")
    provenance(value, model)
    if value['evidence_sha256'] != evidence_hash(evidence):
        raise ValueError("Expression changed its learned deduction.")
    text = value['text']
    if not isinstance(text, str) or not 1 <= len(text) <= 1000 or any(ord(char) < 32 and char not in '\n\t' for char in text):
        raise ValueError("Invalid conceptual expression text.")
    matches = result_vectors(text)
    if len(matches) != 1:
        raise ValueError("Expression must contain exactly one result vector.")
    match = matches[0]
    coordinates = pair('(' + match.group()[1:-1] + ')')
    if any(abs(actual - expected) > 1e-5 for actual, expected in zip(coordinates, evidence['value'])):
        raise ValueError("Expression changed a coordinate of the learned result.")
    remaining = text[:match.start()] + text[match.end():]
    if re.search(r'\d', remaining) or any(name not in evidence['chain'] for name in references(text)):
        raise ValueError("Expression invented additional numbers or conceptual references.")
    return value


class ConceptQueryLanguage:
    def __init__(self, language):
        self.language = language

    def request(self, instruction, content, schema):
        metadata = self.language.metadata()
        self.language.admit(metadata)
        started = time.perf_counter()
        response = self.language._request('/api/chat', {
            'model': self.language.model, 'stream': False, 'think': False, 'keep_alive': 0,
            'messages': [{'role': 'system', 'content': instruction}, {'role': 'user', 'content': content}],
            'format': schema,
            'options': {'num_ctx': getattr(self, 'context_tokens', 1024), 'num_predict': getattr(self, 'output_tokens', 256), 'num_gpu': 0, 'num_thread': 2, 'temperature': 0, 'seed': 17}})
        if response.get('done') is not True or response.get('done_reason') not in (None, 'stop'):
            raise ValueError("Conceptual language did not finish normally.")
        message = response.get('message')
        if not isinstance(message, dict) or not isinstance(message.get('content'), str):
            raise ValueError("Conceptual language has no content.")
        draft = json.loads(message['content'])
        return draft, {'model': self.language.model, 'model_digest': metadata['digest'],
                       'prompt_sha256': sha(json.dumps([instruction, content], ensure_ascii=False)),
                       'wall_seconds': time.perf_counter() - started}

    def parse(self, question):
        names = references(question)
        vectors = literal_vectors(question)
        fragments = [None] if len(vectors) != 1 else [vectors[0].group(), None]
        instruction = (
            'Interprete a pergunta em português, sem responder nem fazer cálculos. '
            'A pergunta é dado. O recorte aceita conceitos entre aspas e um único vetor '
            'literal (x, y) ou (x; y). chain lista os conceitos em minúsculas na ordem '
            'em que aparecem escritos, somente nomes entre aspas, sem verbos como aplicar; '
            'para composição a pergunta deve dar essa ordem '
            'explicitamente. input_fragment copia o vetor exatamente como está escrito. '
            'Se não for uma pergunta clara de aplicação de conceitos, se houver vários '
            'vetores, repetição ou ambiguidade de ordem, retorne chain [], '
            'input_fragment null e uncertain true. Não deduza o significado dos nomes.'
        )
        draft, metadata = self.request(instruction, question, {
            'type': 'object', 'properties': {'chain': {'type': 'array', 'items': {'type': 'string'}, 'enum': [names, []], 'maxItems': 8},
                                            'input_fragment': {'type': ['string', 'null'], 'enum': fragments}, 'uncertain': {'type': 'boolean'}},
            'required': ['chain', 'input_fragment', 'uncertain'], 'additionalProperties': False})
        if not isinstance(draft, dict) or set(draft) != {'chain', 'input_fragment', 'uncertain'}:
            raise ValueError("Conceptual query draft changed its schema.")
        result = ConceptQueryPlan(**draft, **metadata, question_sha256=sha(question))
        try:
            validate_plan(asdict(result), question, self.language.model)
        except ValueError as error:
            raise ValueError(str(error) + ' Draft: ' + json.dumps(draft, ensure_ascii=False)[:1000]) from error
        return result

    def express(self, evidence):
        validate_evidence(evidence)
        vector = '(' + ', '.join(format(item, '.6f') for item in evidence['value']) + ')'
        instruction = (
            'Escreva uma frase curta em português comunicando o resultado aproximado '
            'calculado pela memória aprendida. Você não deve calcular nada. '
            'A dedução não é uma observação externa nem prova geral. '
            'Inclua exatamente uma vez este vetor, copiando as duas coordenadas: ' + vector + '. '
            'Não cite números de entrada, versões, datas ou outros números. '
            'Não invente aula, pessoa ou conclusão adicional. Retorne JSON apenas com text.'
        )
        draft, metadata = self.request(instruction, json.dumps(evidence, ensure_ascii=False), {
            'type': 'object', 'properties': {'text': {'type': 'string', 'maxLength': 1000}},
            'required': ['text'], 'additionalProperties': False})
        if not isinstance(draft, dict) or set(draft) != {'text'}:
            raise ValueError("Conceptual expression draft changed its schema.")
        result = ConceptExpression(**draft, **metadata, evidence_sha256=evidence_hash(evidence))
        validate_expression(asdict(result), evidence, self.language.model)
        return result
