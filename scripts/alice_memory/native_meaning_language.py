"""Literal questions about reported meaning; no history in the parser."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, fields

from .concept_query_language import ConceptQueryLanguage, evidence_hash, provenance, sha
from .language_input import references
from .native_query_language import MODALITIES, WORDS, WINDOW, validate_evidence as sensory_evidence, window_numbers
from .written_symbols import symbol
from .native_reference import validate_reference


def parts(question):
    references(question)
    matches = re.findall(r'"([^"\n]+)"|“([^“”\n]+)”', question)
    names = [symbol(left or right) for left, right in matches]
    remainder = re.sub(r'"([^"\n]+)"|“([^“”\n]+)”', '', question)
    windows = re.findall(WINDOW, remainder)
    initial = bool(re.search(r'\b(?:inicial|primeira|antes)\b', remainder, re.I))
    current = bool(re.search(r'\b(?:atual|agora)\b', remainder, re.I))
    comparison = bool(re.search(r'\b(?:mudou|mudança|compare|comparação)\b', remainder, re.I)) or (initial and current)
    uncertain = len(names) != 2 or len(windows) > 1 or remainder.count('[') != len(windows) or remainder.count(']') != len(windows)
    if uncertain:
        return {'name': None, 'relation': None, 'view': 'current', 'modalities': [], 'window_fragment': None, 'basis': 'relative', 'uncertain': True}
    return {'name': names[0], 'relation': names[1], 'view': 'comparison' if comparison else ('initial' if initial else 'current'),
            'modalities': [item for item in MODALITIES if re.search(WORDS[item], remainder, re.I)],
            'window_fragment': windows[0] if windows else None,
            'basis': 'utc' if re.search(r'\bUTC\b', remainder, re.I) else 'relative', 'uncertain': False}


@dataclass(frozen=True)
class NativeMeaningPlan:
    name: str | None
    relation: str | None
    view: str
    modalities: list[str]
    window_fragment: str | None
    basis: str
    uncertain: bool
    model: str
    model_digest: str
    question_sha256: str
    prompt_sha256: str
    wall_seconds: float
    kind: str = 'literal_native_meaning_query'


def validate_plan(value, question, model):
    if not isinstance(value, dict) or set(value) != {item.name for item in fields(NativeMeaningPlan)} or value['kind'] != 'literal_native_meaning_query' or type(value['uncertain']) is not bool:
        raise ValueError('Invalid native meaning plan fields.')
    provenance(value, model)
    if value['question_sha256'] != sha(question):
        raise ValueError('Native meaning query changed its source.')
    literal = parts(question)
    body = {key: value[key] for key in literal}
    empty = {'name': None, 'relation': None, 'view': 'current', 'modalities': [], 'window_fragment': None, 'basis': 'relative', 'uncertain': True}
    if body != empty and body != literal:
        raise ValueError('Native meaning query requires literal name/relation/view/window.')
    if body['window_fragment'] is not None:
        window_numbers(body['window_fragment'])
    return value


def validate_report(value, moment, relation, view, now):
    expected = {'supported', 'kind', 'moment', 'relation', 'view', 'versions', 'subject', 'sources',
                'confidence_is_calibrated', 'directly_observed', 'autobiographical_write', 'reason'}
    if not isinstance(value, dict) or set(value) != expected or value['kind'] != 'reported_interpretation' or type(value['supported']) is not bool or value['moment'] != moment or type(value['moment']) is not int or value['relation'] != relation or value['view'] != view:
        raise ValueError('Invalid reported meaning evidence address.')
    if value['directly_observed'] is not False or value['confidence_is_calibrated'] is not False or value['autobiographical_write'] is not False:
        raise ValueError('Reported meaning cannot assert direct observation/confidence.')
    versions = value['versions']
    if not isinstance(versions, list) or len(versions) > 32 or versions != sorted(set(versions)) or any(type(item) is not int or not 0 <= item < 4096 for item in versions):
        raise ValueError('Invalid reported meaning versions.')
    if value['reason'] not in ('supported', 'unlearned_interpretation', 'outside_learned_coverage', 'conflicting_statements') or value['supported'] != (value['reason'] == 'supported'):
        raise ValueError('Invalid reported meaning support reason.')
    if value['supported']:
        if not versions or not isinstance(value['subject'], str) or symbol(value['subject']) != value['subject']:
            raise ValueError('Supported meaning has no learned subject.')
    elif value['subject'] is not None:
        raise ValueError('Unsupported meaning asserts a subject.')
    sources = value['sources']
    expected_sources = len(versions) if value['reason'] in ('supported', 'conflicting_statements') else 0
    if not isinstance(sources, list) or len(sources) != expected_sources:
        raise ValueError('Reported meaning lost provenance.')
    for index, source in enumerate(sources):
        required = {'id', 'moment', 'relation', 'kind', 'source_sha256', 'origin', 'sequence', 'acquired_at', 'corrects'}
        if not isinstance(source, dict) or set(source) not in (required, required | {'moment_ref'}, required | {'moment_ref', 'language'}) or type(source['id']) is not int or source['id'] != versions[index] or type(source['moment']) is not int or source['moment'] != moment or type(source['relation']) is not int or not 0 <= source['relation'] < 32 or source['kind'] != 'external_statement' or source['origin'] not in ('person', 'environment'):
            raise ValueError('Invalid meaning source fields.')
        if not isinstance(source['source_sha256'], str) or re.fullmatch(r'[0-9a-f]{64}', source['source_sha256']) is None or type(source['sequence']) is not int or not 0 <= source['sequence'] < 1000000 or isinstance(source['acquired_at'], bool) or not isinstance(source['acquired_at'], (int, float)) or not 0 <= source['acquired_at'] <= now:
            raise ValueError('Invalid meaning source hash/time/sequence.')
        if 'moment_ref' in source and (validate_reference(source['moment_ref'], source['acquired_at'])['id'] != moment):
            raise ValueError('Reported meaning changed its original event reference.')
        if 'language' in source:
            from .context_report_language import validate_source
            validate_source(source['language'])
            if source['language']['message_sha256'] != source['source_sha256']:
                raise ValueError('Reported meaning changed its contextual language source.')
        corrected = source['corrects']
        if not isinstance(corrected, list) or corrected != sorted(set(corrected)) or any(type(item) is not int or not 0 <= item < source['id'] for item in corrected):
            raise ValueError('Invalid meaning correction links.')
    return value


def validate_evidence(value):
    required = {'kind', 'name', 'relation', 'view', 'sensory', 'reports', 'signature', 'query_sha256', 'computed_at'}
    if not isinstance(value, dict) or set(value) != required or value['kind'] != 'native_meaning' or not isinstance(value['relation'], str) or symbol(value['relation']) != value['relation'] or value['view'] not in ('initial', 'current', 'comparison'):
        raise ValueError('Invalid native meaning evidence fields.')
    sensory = sensory_evidence(value['sensory'])
    if value['name'] != sensory['name']:
        raise ValueError('Native meaning evidence changed its named cue.')
    if value['query_sha256'] != sensory['query_sha256'] or value['computed_at'] != sensory['computed_at'] or not isinstance(value['signature'], str) or re.fullmatch(r'[0-9a-f]{64}', value['signature']) is None:
        raise ValueError('Native meaning evidence changed its sensory source.')
    views = ['initial', 'current'] if value['view'] == 'comparison' else [value['view']]
    reports = value['reports']
    if not isinstance(reports, dict) or set(reports) != (set(views) if sensory['supported'] else set()):
        raise ValueError('Meaning cannot bypass an ambiguous/unsupported moment.')
    for view in views if sensory['supported'] else []:
        validate_report(reports[view], sensory['moment_id'], value['relation'], view, value['computed_at'])
    return value


def phrases(value):
    validate_evidence(value)
    sensory = value['sensory']
    name, relation = '"' + sensory['name'] + '"', '"' + value['relation'] + '"'
    if not sensory['supported']:
        if sensory['reason'] == 'ambiguous_moments':
            return [f'Preciso de uma pista de quando aconteceu para escolher o momento de {name} e consultar {relation}.']
        return [f'Não consegui localizar um momento confiável de {name} para consultar {relation}.']
    if any(item['reason'] == 'conflicting_statements' for item in value['reports'].values()):
        return [f'Os relatos registrados para {relation} de {name} estão em conflito; ainda não tenho uma atribuição única.']
    if any(not item['supported'] for item in value['reports'].values()):
        return [f'Ainda não consigo recuperar uma interpretação aprendida confiável de {relation} para {name}.']
    if value['view'] == 'comparison':
        initial, current = (value['reports'][view]['subject'] for view in ('initial', 'current'))
        if initial == current:
            return [f'A primeira informação e a informação atual registradas para {relation} de {name} apontam para "{current}". São relatos recebidos.']
        return [f'A primeira informação registrada para {relation} de {name} apontava para "{initial}"; a informação atual aponta para "{current}". São relatos recebidos.']
    report = value['reports'][value['view']]
    label = 'primeira' if value['view'] == 'initial' else 'atual'
    return [f'A informação {label} registrada para {relation} de {name} aponta para "{report["subject"]}". É um relato recebido.']


@dataclass(frozen=True)
class NativeMeaningExpression:
    text: str
    model: str
    model_digest: str
    evidence_sha256: str
    prompt_sha256: str
    wall_seconds: float


def validate_expression(value, evidence, model):
    if not isinstance(value, dict) or set(value) != {item.name for item in fields(NativeMeaningExpression)}:
        raise ValueError('Invalid native meaning expression fields.')
    provenance(value, model)
    if value['evidence_sha256'] != evidence_hash(evidence) or value['text'] not in phrases(evidence):
        raise ValueError('Native meaning expression changed factual text or observation status.')
    return value


class NativeMeaningLanguage(ConceptQueryLanguage):
    def parse(self, question):
        literal = parts(question)
        uncertain = {'name': None, 'relation': None, 'view': 'current', 'modalities': [], 'window_fragment': None, 'basis': 'relative', 'uncertain': True}
        variants = [uncertain] if literal['uncertain'] else [literal, uncertain]
        schema = {'anyOf': [{'type': 'object', 'properties': {key: {'const': item} for key, item in choice.items()},
                             'required': list(choice), 'additionalProperties': False} for choice in variants]}
        draft, metadata = self.request('Interprete a pergunta em português sobre relatos de memória, sem responder. '
            'O primeiro nome entre aspas nomeia o acontecimento; o segundo nomeia a relação. '
            'Use initial para primeira/inicial/antes; current para atual/agora; comparison para o que mudou ou comparação. '
            'Copie pistas de modalidade e intervalo literalmente, sem deduzir pessoas ou datas. '
            'Pergunta ambígua usa uncertain true e campos vazios. Não invente significado dos nomes.', question, schema)
        if not isinstance(draft, dict) or set(draft) != set(literal):
            raise ValueError('Native meaning query draft changed schema.')
        result = NativeMeaningPlan(**draft, **metadata, question_sha256=sha(question))
        validate_plan(asdict(result), question, self.language.model)
        return result

    def express(self, evidence):
        choices = phrases(evidence)
        draft, metadata = self.request('Copie exatamente a frase autorizada para esta evidência. '
            'Mantenha primeira/atual e que se trata de relato recebido, sem alegar que viu a cena. Retorne text.',
            json.dumps(evidence, ensure_ascii=False), {'type': 'object', 'properties': {'text': {'type': 'string', 'enum': choices}},
            'required': ['text'], 'additionalProperties': False})
        if not isinstance(draft, dict) or set(draft) != {'text'}:
            raise ValueError('Native meaning expression draft changed schema.')
        result = NativeMeaningExpression(**draft, **metadata, evidence_sha256=evidence_hash(evidence))
        validate_expression(asdict(result), evidence, self.language.model)
        return result
