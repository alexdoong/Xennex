"""Literal Portuguese reports/corrections; no retained beliefs in the parser."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, fields

from .concept_query_language import ConceptQueryLanguage, provenance, sha
from .language_input import references
from .written_symbols import symbol


def parts(text):
    references(text)
    quoted = re.findall(r'"([^"\n]+)"|“([^“”\n]+)”', text)
    names = [symbol(left or right) for left, right in quoted]
    remaining = re.sub(r'"([^"\n]+)"|“([^“”\n]+)”', '', text)
    moments = re.findall(r'\bmomento\s+(\d{1,6})\b', remaining, re.I)
    lists = re.findall(r'\[(\s*\d+(?:\s*[;,]\s*\d+)*\s*)\]', remaining)
    negative = re.search(r'\b(?:não|nao|nunca|jamais|talvez)\b', remaining, re.I)
    explicit = re.search(r'\b(?:associe|atribua|corrija)\b', remaining, re.I)
    uncertain = len(names) != 2 or len(moments) != 1 or len(lists) > 1 or negative is not None or explicit is None
    correction = bool(re.search(r'\bcorrija\b', remaining, re.I))
    if correction != bool(lists) or remaining.count('[') != len(lists) or remaining.count(']') != len(lists):
        uncertain = True
    ids = [] if not lists else [int(item) for item in re.split(r'[;,]', lists[0])]
    if ids != sorted(set(ids)) or len(ids) > 32 or any(not 0 <= item < 4096 for item in ids):
        uncertain = True
    if uncertain:
        return {'moment': None, 'relation': None, 'subject': None, 'corrects': [], 'uncertain': True}
    return {'moment': int(moments[0]), 'relation': names[0], 'subject': names[1], 'corrects': ids, 'uncertain': False}


@dataclass(frozen=True)
class NativeStatementPlan:
    moment: int | None
    relation: str | None
    subject: str | None
    corrects: list[int]
    uncertain: bool
    model: str
    model_digest: str
    message_sha256: str
    prompt_sha256: str
    wall_seconds: float
    kind: str = 'literal_native_statement'


def validate_plan(value, message, model):
    if not isinstance(value, dict) or set(value) != {item.name for item in fields(NativeStatementPlan)} or value['kind'] != 'literal_native_statement' or type(value['uncertain']) is not bool:
        raise ValueError('Invalid native statement plan fields.')
    provenance(value, model)
    if value['message_sha256'] != sha(message):
        raise ValueError('Native statement changed its source message.')
    expected = parts(message)
    uncertain = {'moment': None, 'relation': None, 'subject': None, 'corrects': [], 'uncertain': True}
    body = {key: value[key] for key in expected}
    if body != uncertain and (expected['uncertain'] or body != expected):
        raise ValueError('Native statement requires literal moment/relation/subject/corrections.')
    if body['moment'] is not None and (type(body['moment']) is not int or not 0 <= body['moment'] < 1000000):
        raise ValueError('Invalid native statement moment.')
    if not isinstance(body['corrects'], list) or any(type(item) is not int for item in body['corrects']):
        raise ValueError('Invalid native statement correction identifiers.')
    return value


class NativeStatementLanguage(ConceptQueryLanguage):
    def parse(self, message):
        literal = parts(message)
        uncertain = {'moment': None, 'relation': None, 'subject': None, 'corrects': [], 'uncertain': True}
        alternatives = [uncertain] if literal['uncertain'] else [literal, uncertain]
        schema = {'anyOf': [{'type': 'object', 'properties': {key: {'const': item} for key, item in choice.items()},
                            'required': list(choice), 'additionalProperties': False} for choice in alternatives]}
        instruction = ('Interprete somente uma declaração externa explícita em português. '
            'Associe/atribua no momento N a primeira relação entre aspas ao segundo sujeito entre aspas. '
            'Corrija exige uma lista literal das versões substituídas. Copie todos os campos literalmente. '
            'Não deduza nomes/pessoas nem a verdade do relato. Negação, hipótese ou ambiguidade usam uncertain true '
            'e campos null/corrects []. Não responda nem invente evidência.')
        draft, metadata = self.request(instruction, message, schema)
        if not isinstance(draft, dict) or set(draft) != set(literal):
            raise ValueError('Native statement draft changed its schema.')
        result = NativeStatementPlan(**draft, **metadata, message_sha256=sha(message))
        validate_plan(asdict(result), message, self.language.model)
        return result
