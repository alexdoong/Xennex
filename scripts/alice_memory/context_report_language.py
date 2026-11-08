"""Literal role/value fragments in Portuguese; event selection stays with owner."""
import re
from dataclasses import asdict, dataclass, fields

from .concept_query_language import ConceptQueryLanguage, provenance, sha, evidence_hash
from .native_feedback_language import message_valid
from .written_symbols import symbol

EMPTY = {'relation_fragment': None, 'subject_fragment': None, 'uncertain': True}
PARTICLES = {'o', 'a', 'um', 'uma', 'meu', 'minha', 'do', 'da', 'pelo', 'pela', 'por'}
LEGACY_REPORT_KIND = 'contextual_relation'
REPORT_KIND = 'contextual_relation_v2'
REPORT_KINDS = (LEGACY_REPORT_KIND, REPORT_KIND)
HEDGE = re.compile(r'\b(?:aparentemente|supostamente|provavelmente|possivelmente|presumivelmente|'
                   r'(?:pelo|ao)\s+que\s+parece|ao\s+que\s+tudo\s+indica|'
                   r'(?:acho|acredito|creio)\s+que|sem\s+certeza)\b', re.I)


def subject_value(fragment):
    if not isinstance(fragment, str) or not 1 <= len(fragment) <= 256:
        raise ValueError('Invalid literal subject fragment.')
    words = [word for word in re.findall(r'\w+', fragment) if word.casefold() not in PARTICLES]
    if len(words) != 1:
        raise ValueError('Subject fragment needs one canonical value.')
    return symbol(words[0])


def literal_value(fragment, message):
    predicate = next(re.finditer(r'\b(?:é|foi|era|passa\s+a\s+ser)\b', message, re.I))
    source = [symbol(word) for word in re.findall(r'\w+', message[predicate.end():])]
    selected = [symbol(word) for word in re.findall(r'\w+', fragment)]
    return bool(selected) and any(source[index:index+len(selected)] == selected for index in range(len(source)))


def parts(message, *, kind=REPORT_KIND):
    message_valid(message)
    if re.search(r'[?"“”]|\b(?:não|nao|nunca|talvez|seria|poderia|disse|segundo|ignore|retorne|responda)\b', message, re.I):
        return EMPTY.copy()
    predicates = list(re.finditer(r'\b(?:é|foi|era|passa\s+a\s+ser)\b', message, re.I))
    if len(predicates) != 1:
        return EMPTY.copy()
    predicate = predicates[0]
    prefix, suffix = message[:predicate.start()], message[predicate.end():]
    if kind == REPORT_KIND and (HEDGE.search(prefix) or len(set(re.findall(r'\w+', message))) > 128):
        return EMPTY.copy()
    role = re.match(r'\s*(?:(?:porra|caralho)[,!]\s*)?(?:(?:na\s+verdade|corrigindo)[,:]?\s*)?(?:o|a)\s+(\w+)\b', prefix, re.I)
    if role is None and any(word.casefold() not in ('na', 'verdade', 'corrigindo') for word in re.findall(r'\w+', prefix)):
        return EMPTY.copy()
    values = [word for word in re.findall(r'\w+', suffix) if word.casefold() not in PARTICLES]
    if len(values) != 1:
        return EMPTY.copy()
    try:
        symbol(values[0])
        if role is not None:
            symbol(role[1])
    except ValueError:
        return EMPTY.copy()
    return {'relation_fragment': None if role is None else role[1], 'subject_fragment': values[0], 'uncertain': False}


@dataclass(frozen=True)
class ContextReportPlan:
    relation_fragment: str | None
    subject_fragment: str | None
    uncertain: bool
    model: str
    model_digest: str
    message_sha256: str
    prompt_sha256: str
    wall_seconds: float
    kind: str = REPORT_KIND


def validate_plan(value, message, model):
    if not isinstance(value, dict) or set(value) != {item.name for item in fields(ContextReportPlan)} or value['kind'] not in REPORT_KINDS or type(value['uncertain']) is not bool:
        raise ValueError('Invalid contextual report plan.')
    provenance(value, model)
    if value['message_sha256'] != sha(message):
        raise ValueError('Contextual report changed its source message.')
    literal = parts(message, kind=value['kind'])
    body = {key: value[key] for key in EMPTY}
    if body == EMPTY:
        return value
    if body['uncertain'] or literal['uncertain']:
        raise ValueError('Guarded contextual report cannot teach.')
    role = body['relation_fragment']
    if (role is None) != (literal['relation_fragment'] is None) or (role is not None and symbol(role) != symbol(literal['relation_fragment'])):
        raise ValueError('Contextual report changed its supplied literal role.')
    if subject_value(body['subject_fragment']) != symbol(literal['subject_fragment']) or not literal_value(body['subject_fragment'], message):
        raise ValueError('Contextual report requires a literal value after the predicate.')
    return value


def language_source(plan):
    return {'kind': plan['kind'], 'model': plan['model'], 'model_digest': plan['model_digest'],
            'message_sha256': plan['message_sha256'], 'prompt_sha256': plan['prompt_sha256'],
            'plan_sha256': evidence_hash(plan)}


def validate_source(value):
    keys = {'kind', 'model', 'model_digest', 'message_sha256', 'prompt_sha256', 'plan_sha256'}
    if not isinstance(value, dict) or set(value) != keys or value['kind'] not in REPORT_KINDS:
        raise ValueError('Invalid contextual language source.')
    for key in ('model', 'model_digest'):
        if not isinstance(value[key], str) or not 1 <= len(value[key]) <= 128 or any(ord(char) < 32 for char in value[key]):
            raise ValueError('Invalid contextual model identity.')
    if any(not isinstance(value[key], str) or re.fullmatch(r'[0-9a-f]{64}', value[key]) is None for key in ('message_sha256', 'prompt_sha256', 'plan_sha256')):
        raise ValueError('Invalid contextual language hashes.')
    return value


class ContextReportLanguage(ConceptQueryLanguage):
    def parse(self, message):
        literal = parts(message)
        # The grammar identifies a literal value. The model can still
        # abstain from interpreting the received text as a clear report.
        allowed = {'const': None} if literal['uncertain'] else {'enum': [literal['subject_fragment'], None]}
        schema = {'type': 'object', 'properties': {
            'value_fragment': allowed},
            'required': ['value_fragment'], 'additionalProperties': False}
        instruction = ('Verifique se a frase é uma atribuição explícita em português. '
            'Para uma afirmação ou correção clara, copie em value_fragment a palavra atribuída após é, foi, era ou passa a ser. '
            'O autor é meu pai -> pai. Na verdade, foi minha mãe -> mãe. A cor é azul -> azul. '
            'Pergunta, negação, hipótese, citação ou dúvida -> null. Preserve a grafia e os acentos. '
            'Retorne apenas o campo value_fragment.')
        draft, metadata = self.request(instruction, message, schema)
        if not isinstance(draft, dict) or set(draft) != {'value_fragment'}:
            raise ValueError('Contextual report draft changed its fields.')
        uncertain = draft['value_fragment'] is None
        # Literal role grammar is supplied, not an inferred model belief. The
        # model proposes only the value span and sees no owner/context identifiers.
        value = ContextReportPlan(None if uncertain else literal['relation_fragment'], draft['value_fragment'],
                                  uncertain, **metadata, message_sha256=sha(message))
        validate_plan(asdict(value), message, self.language.model)
        return value
