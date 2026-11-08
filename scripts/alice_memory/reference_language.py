"""Bounded anaphoric question perspective; the model never selects its referent."""
import re
import json
import unicodedata
from dataclasses import asdict, dataclass, fields

from .concept_query_language import ConceptQueryLanguage, provenance, sha, evidence_hash
from .native_feedback_language import message_valid
from .native_reference import validate_reference, number
from .native_meaning_language import validate_report
from .written_symbols import symbol


def perspective(question):
    message_valid(question)
    text = ' '.join(unicodedata.normalize('NFKC', question).casefold().split()).strip(' ?!.')
    if re.fullmatch(r'(?:o que|quem) (?:mudou|muda)|compare(?: antes e agora| as versões)?', text):
        return 'comparison'
    if re.fullmatch(r'(?:e )?(?:antes|agora)', text):
        return 'initial' if text.endswith('antes') else 'current'
    if re.fullmatch(r'(?:quem|o que)(?: (?:é|era|foi))?(?: antes|agora|inicialmente|originalmente)?', text):
        if 'agora' in text and re.search(r'\b(?:era|foi)\b', text):
            return 'uncertain'
        return 'initial' if re.search(r'\b(?:era|foi|antes|inicialmente|originalmente)\b', text) else 'current'
    if re.fullmatch(r'qual (?:é|era|foi) a (?:informação|interpretação|atribuição) (?:atual|inicial|primeira|original)', text):
        return 'current' if text.endswith('atual') else 'initial'
    return 'uncertain'


@dataclass(frozen=True)
class ReferencePlan:
    view: str
    uncertain: bool
    model: str
    model_digest: str
    question_sha256: str
    prompt_sha256: str
    wall_seconds: float
    kind: str = 'referenced_interpretation_query'


def validate_plan(value, question, model):
    if not isinstance(value, dict) or set(value) != {item.name for item in fields(ReferencePlan)} or value['kind'] != 'referenced_interpretation_query' or type(value['uncertain']) is not bool:
        raise ValueError('Invalid referenced query plan.')
    provenance(value, model)
    if value['question_sha256'] != sha(question) or value['view'] not in ('initial', 'current', 'comparison', 'uncertain') or value['uncertain'] != (value['view'] == 'uncertain'):
        raise ValueError('Referenced question changed its source/perspective.')
    if not value['uncertain'] and value['view'] != perspective(question):
        raise ValueError('Referenced question has no literal supported perspective.')
    return value


def validate_evidence(value):
    expected = {'kind', 'relation', 'view', 'moment_ref', 'reports', 'sensory_episode_retained',
                'signature', 'query_sha256', 'computed_at'}
    if not isinstance(value, dict) or set(value) != expected or value['kind'] != 'referenced_interpretation' or value['view'] not in ('initial', 'current', 'comparison') or symbol(value['relation']) != value['relation'] or type(value['sensory_episode_retained']) is not bool:
        raise ValueError('Invalid referenced interpretation evidence.')
    number(value['computed_at'], 0, 1e12)
    reference = validate_reference(value['moment_ref'], value['computed_at'])
    for key in ('signature', 'query_sha256'):
        if not isinstance(value[key], str) or re.fullmatch(r'[0-9a-f]{64}', value[key]) is None:
            raise ValueError('Invalid referenced interpretation signature.')
    views = ['initial', 'current'] if value['view'] == 'comparison' else [value['view']]
    if not isinstance(value['reports'], dict) or set(value['reports']) != set(views):
        raise ValueError('Referenced interpretation lost its requested views.')
    for view in views:
        report = value['reports'][view]
        validate_report(report, reference['id'], value['relation'], view, value['computed_at'])
        if any(source['moment_ref'] != reference for source in report['sources']):
            raise ValueError('Referenced interpretation changed its original episode.')
    return value


def phrases(value):
    validate_evidence(value)
    role = '"' + value['relation'] + '"'
    reports = value['reports']
    if any(report['reason'] == 'conflicting_statements' for report in reports.values()):
        text = f'Os relatos sobre {role} nessa experiência estão em conflito; ainda não tenho uma atribuição única.'
    elif any(not report['supported'] for report in reports.values()):
        text = f'Ainda não consigo recuperar uma interpretação aprendida confiável sobre {role} nessa experiência.'
    elif value['view'] == 'comparison':
        initial, current = (reports[view]['subject'] for view in ('initial', 'current'))
        text = f'O primeiro relato sobre {role} nessa experiência apontava para "{initial}"; o atual aponta para "{current}". São relatos recebidos.'
    else:
        label = 'primeiro' if value['view'] == 'initial' else 'atual'
        text = f'O relato {label} sobre {role} nessa experiência aponta para "{reports[value["view"]]["subject"]}". É um relato recebido.'
    if not value['sensory_episode_retained']:
        text += ' O episódio sensorial não está mais retido; esta resposta usa a interpretação conservada.'
    return [text]


@dataclass(frozen=True)
class ReferenceExpression:
    text: str
    model: str
    model_digest: str
    evidence_sha256: str
    prompt_sha256: str
    wall_seconds: float


def validate_expression(value, evidence, model):
    if not isinstance(value, dict) or set(value) != {item.name for item in fields(ReferenceExpression)}:
        raise ValueError('Invalid referenced interpretation expression.')
    provenance(value, model)
    if value['evidence_sha256'] != evidence_hash(evidence) or value['text'] not in phrases(evidence):
        raise ValueError('Referenced expression changed its learned evidence.')
    return value


class ReferenceLanguage(ConceptQueryLanguage):
    def parse(self, question):
        expected = perspective(question)
        schema = {'type': 'object', 'properties': {'view': {'enum': ['initial', 'current', 'comparison', 'uncertain']}},
                  'required': ['view'], 'additionalProperties': False}
        if expected == 'uncertain':
            schema['properties'] = {'view': {'const': 'uncertain'}}
        draft, metadata = self.request('Classifique somente a perspectiva da pergunta em português. '
            'Quem era antes/E antes -> initial. Quem é agora/E agora -> current. '
            'O que mudou/compare -> comparison. Pergunta de outro assunto ou sem interpretação clara -> uncertain. '
            'Não responda, não selecione pessoa, relação ou episódio.', question, schema)
        if not isinstance(draft, dict) or set(draft) != {'view'}:
            raise ValueError('Referenced query draft changed its fields.')
        value = ReferencePlan(draft['view'], draft['view'] == 'uncertain', **metadata, question_sha256=sha(question))
        validate_plan(asdict(value), question, self.language.model)
        return value

    def express(self, evidence):
        choices = phrases(evidence)
        draft, metadata = self.request('Copie exatamente a frase autorizada, mantendo que são relatos recebidos '
            'e se o episódio sensorial ainda está retido. Não alegue ter visto a atribuição.',
            json.dumps(evidence, ensure_ascii=False),
            {'type': 'object', 'properties': {'text': {'enum': choices}}, 'required': ['text'], 'additionalProperties': False})
        if not isinstance(draft, dict) or set(draft) != {'text'}:
            raise ValueError('Referenced expression draft changed its fields.')
        value = ReferenceExpression(**draft, **metadata, evidence_sha256=evidence_hash(evidence))
        validate_expression(asdict(value), evidence, self.language.model)
        return value
