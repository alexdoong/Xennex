"""Portuguese syntax for native recall; worker receives no sensor/weight history.

Initial expression chooses a verified phrase, not open scene descriptions. This
keeps factual text checkable while open grounded dialogue remains future work.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, fields

from .concept_query_language import ConceptQueryLanguage, evidence_hash, provenance, sha
from .language_input import references

MODALITIES = ('image', 'audio', 'text')
WINDOW = r'\[\s*\d+(?:[.,]\d+)?\s*;\s*\d+(?:[.,]\d+)?\s*\]'
WORDS = {'image': r'\b(?:imagem|imagens|foto|fotos|visão|viu)\b',
         'audio': r'\b(?:áudio|audio|som|sons|voz|ouviu)\b',
         'text': r'\b(?:texto|textos|leu)\b'}


def literal_parts(question):
    names = references(question)
    quoted = re.findall(r'"([^"\n]+)"|“([^“”\n]+)”', question)
    remainder = re.sub(r'"([^"\n]+)"|“([^“”\n]+)”', '', question)
    modalities = [name for name in MODALITIES if re.search(WORDS[name], remainder, re.I)]
    windows = re.findall(WINDOW, remainder)
    unclear = len(names) != 1 or len(quoted) != 1 or len(windows) > 1 or remainder.count('[') != len(windows) or remainder.count(']') != len(windows)
    return names, modalities, windows, unclear


def window_numbers(fragment):
    if not isinstance(fragment, str) or re.fullmatch(WINDOW, fragment) is None:
        raise ValueError('Native query needs one literal [start; end] window.')
    values = [float(item.strip().replace(',', '.')) for item in fragment[1:-1].split(';')]
    if any(not math.isfinite(item) or not 0 <= item <= 1e12 for item in values) or values[1] < values[0]:
        raise ValueError('Invalid native query time window.')
    return values


@dataclass(frozen=True)
class NativeQueryPlan:
    name: str | None
    modalities: list[str]
    window_fragment: str | None
    basis: str
    uncertain: bool
    model: str
    model_digest: str
    question_sha256: str
    prompt_sha256: str
    wall_seconds: float
    kind: str = 'literal_native_recall'


def validate_plan(value, question, model):
    if not isinstance(value, dict) or set(value) != {item.name for item in fields(NativeQueryPlan)} or value['kind'] != 'literal_native_recall' or type(value['uncertain']) is not bool:
        raise ValueError('Invalid native recall plan fields.')
    provenance(value, model)
    if value['question_sha256'] != sha(question) or value['basis'] not in ('relative', 'utc') or not isinstance(value['modalities'], list):
        raise ValueError('Native recall plan changed its source.')
    names, modalities, windows, unclear = literal_parts(question)
    if value['uncertain']:
        if value['name'] is not None or value['modalities'] or value['window_fragment'] is not None or value['basis'] != 'relative':
            raise ValueError('Uncertain native query cannot assert a memory address.')
        return value
    basis = 'utc' if re.search(r'\bUTC\b', question, re.I) else 'relative'
    if unclear or value['name'] != names[0] or value['modalities'] != modalities or value['window_fragment'] != (windows[0] if windows else None) or value['basis'] != basis:
        raise ValueError('Native query requires literal name, cue modalities and window.')
    if windows:
        window_numbers(windows[0])
    return value


def validate_evidence(value):
    expected = {'kind', 'name', 'cue_modalities', 'window', 'basis', 'supported', 'reason', 'candidate_count',
                'candidate_ids', 'moment_id', 'acquired_at', 'modalities', 'evoked_sha256', 'query_sha256',
                'computed_at', 'signature', 'confidence_is_calibrated'}
    if not isinstance(value, dict) or set(value) != expected or value['kind'] != 'native_recall' or type(value['supported']) is not bool:
        raise ValueError('Invalid native recall evidence fields.')
    if value['confidence_is_calibrated'] is not False:
        raise ValueError('Native recall thresholds are not calibrated confidence.')
    if references('"' + str(value['name']) + '"') != [value['name']] or value['basis'] not in ('relative', 'utc'):
        raise ValueError('Invalid native recall evidence name/basis.')
    for field in ('cue_modalities', 'modalities'):
        items = value[field]
        if not isinstance(items, list) or items != [item for item in MODALITIES if item in items]:
            raise ValueError('Invalid native recall evidence modalities.')
    window = value['window']
    if window is not None:
        if not isinstance(window, list) or len(window) != 2:
            raise ValueError('Invalid native recall evidence window.')
        if any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) or not 0 <= item <= 1e12 for item in window) or window[1] < window[0]:
            raise ValueError('Invalid native recall evidence window values.')
    if type(value['candidate_count']) is not int or not 0 <= value['candidate_count'] <= 2048:
        raise ValueError('Invalid native recall candidate count.')
    ids = value['candidate_ids']
    if not isinstance(ids, list) or len(ids) != min(value['candidate_count'], 8) or ids != sorted(set(ids)) or any(type(item) is not int or not 0 <= item < 1000000 for item in ids):
        raise ValueError('Invalid native recall candidates.')
    for key in ('query_sha256', 'signature'):
        if not isinstance(value[key], str) or re.fullmatch(r'[0-9a-f]{64}', value[key]) is None:
            raise ValueError('Invalid native recall evidence hash.')
    if isinstance(value['computed_at'], bool) or not isinstance(value['computed_at'], (int, float)) or not math.isfinite(value['computed_at']) or not 0 <= value['computed_at'] <= 1e12:
        raise ValueError('Invalid native recall evidence clock.')
    allowed = {'supported', 'unlearned_native_meaning', 'unlearned_weights', 'no_supported_moment',
               'ambiguous_moments', 'unobserved_target', 'outside_associative_coverage', 'future_window'}
    if value['reason'] not in allowed or value['supported'] != (value['reason'] == 'supported'):
        raise ValueError('Invalid native recall support reason.')
    if value['supported']:
        if value['candidate_count'] != 1 or value['moment_id'] != ids[0] or not value['modalities'] or not isinstance(value['evoked_sha256'], dict) or set(value['evoked_sha256']) != set(value['modalities']):
            raise ValueError('Supported native recall lost its moment.')
        if isinstance(value['acquired_at'], bool) or not isinstance(value['acquired_at'], (int, float)) or not 0 <= value['acquired_at'] <= value['computed_at']:
            raise ValueError('Invalid native recalled capture time.')
        if any(not isinstance(item, str) or re.fullmatch(r'[0-9a-f]{64}', item) is None for item in value['evoked_sha256'].values()):
            raise ValueError('Invalid native evoked representation hash.')
    elif value['moment_id'] is not None or value['acquired_at'] is not None or value['modalities'] or value['evoked_sha256']:
        raise ValueError('Unsupported native recall cannot assert evoked content.')
    return value


def phrases(evidence):
    validate_evidence(evidence)
    name = '"' + evidence['name'] + '"'
    if evidence['supported']:
        labels = {'image': 'imagem', 'audio': 'áudio', 'text': 'texto'}
        items = [labels[item] for item in evidence['modalities']]
        joined = items[0] if len(items) == 1 else ', '.join(items[:-1]) + ' e ' + items[-1]
        return [f'Consigo evocar {joined} do momento associado a {name}.',
                f'Lembro de {joined} em um momento associado a {name}.']
    if evidence['reason'] == 'ambiguous_moments':
        return [f'Encontrei mais de um momento compatível com {name}. Preciso de uma pista de quando aconteceu.',
                f'Há vários momentos compatíveis com {name}; ainda não consigo escolher um deles.']
    if evidence['reason'] == 'unlearned_native_meaning':
        return [f'Ainda não tenho uma associação aprendida que me permita evocar {name}.']
    return [f'Não consegui evocar um momento confiável de {name} com essa pista.',
            f'Essa pista ainda não me permite recuperar um momento de {name} com confiança.']


@dataclass(frozen=True)
class NativeExpression:
    text: str
    model: str
    model_digest: str
    evidence_sha256: str
    prompt_sha256: str
    wall_seconds: float


def validate_expression(value, evidence, model):
    if not isinstance(value, dict) or set(value) != {item.name for item in fields(NativeExpression)}:
        raise ValueError('Invalid native expression fields.')
    provenance(value, model)
    if value['evidence_sha256'] != evidence_hash(evidence) or value['text'] not in phrases(evidence):
        raise ValueError('Native expression changed its grounded factual text.')
    return value


class NativeQueryLanguage(ConceptQueryLanguage):
    def parse(self, question):
        names, modalities, windows, unclear = literal_parts(question)
        def variant(name, cues, fragment, basis, uncertain):
            constants = {'name': name, 'modalities': cues, 'window_fragment': fragment, 'basis': basis, 'uncertain': uncertain}
            return {'type': 'object', 'properties': {key: {'const': item} for key, item in constants.items()},
                    'required': list(constants), 'additionalProperties': False}
        variants = [variant(None, [], None, 'relative', True)]
        if not unclear:
            variants.insert(0, variant(names[0], modalities, windows[0] if windows else None,
                            'utc' if re.search(r'\bUTC\b', question, re.I) else 'relative', False))
        draft, metadata = self.request(
            'Interprete uma pergunta de evocação de memória em português, sem responder. '
            'Aceite um nome entre aspas e pistas de imagem/foto, áudio/som/voz ou texto. '
            'Copie name em minúsculas, modalities em ordem image,audio,text conforme palavras da pergunta. '
            'Sem modalidade escrita use []. Copie o único intervalo literal [início; fim], se houver, '
            'sem converter ontem ou datas; UTC escrito usa basis utc, caso contrário relative. '
            'Se não for uma pergunta clara de lembrança ou houver ambiguidade, use uncertain true, '
            'name null, modalities [], window_fragment null, basis relative. Não deduza significados.', question,
            {'anyOf': variants})
        if not isinstance(draft, dict) or set(draft) != {'name', 'modalities', 'window_fragment', 'basis', 'uncertain'}:
            raise ValueError('Native query draft changed its schema.')
        result = NativeQueryPlan(**draft, **metadata, question_sha256=sha(question))
        validate_plan(asdict(result), question, self.language.model)
        return result

    def express(self, evidence):
        choices = phrases(evidence)
        draft, metadata = self.request('Escolha uma das frases autorizadas para expressar esta evocação. '
            'Copie a frase exatamente. Não descreva a cena, pessoa, som ou significado do nome. Retorne JSON com text.',
            json.dumps(evidence, ensure_ascii=False), {'type': 'object', 'properties': {'text': {'type': 'string', 'enum': choices}},
            'required': ['text'], 'additionalProperties': False})
        if not isinstance(draft, dict) or set(draft) != {'text'}:
            raise ValueError('Native expression draft changed its schema.')
        result = NativeExpression(**draft, **metadata, evidence_sha256=evidence_hash(evidence))
        validate_expression(asdict(result), evidence, self.language.model)
        return result
