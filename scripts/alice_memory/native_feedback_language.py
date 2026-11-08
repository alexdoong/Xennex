"""Pretrained language proposes a bounded social reaction to external feedback.

This is interpretation of a person's evaluation, not Alice's own subjective
emotion, factual verification or an estimate of benefit/effort.
"""
from dataclasses import asdict, dataclass, fields
import re

from .concept_query_language import ConceptQueryLanguage, evidence_hash, provenance, sha

REACTIONS = ('encouraging', 'discouraging', 'uncertain')


def message_valid(message):
    if not isinstance(message, str) or not 1 <= len(message) <= 4096 or not message.strip() or len(message.encode('utf-8')) > 8192 or any(ord(char) < 32 and char not in '\n\t' for char in message):
        raise ValueError('Invalid external feedback text.')


def guarded(message):
    message_valid(message)
    # A conservative boundary for this first direct-evaluation contract.
    # Neither profanity nor an ordinary negation implies a negative reaction.
    return bool(re.search(r'[?"“”]|\b(?:talvez|seria|poderia|disse|falou|segundo|sarcasmo|ironia|brincando|ignore|classifique|retorne|responda)\b|\b(?:quero saber|me explique|explique como)\b', message, re.I))


def explicit_adverse(message):
    for negative in re.finditer(r'\b(?:detestei|detesto|odiei|odeio|péssim\w*|pessim\w*|desagrad\w*|frustr\w*|horrível|horrivel)\b', message, re.I):
        if not re.search(r'\b(?:não|nao|nunca)\s+(?:\w+\s+){0,2}$', message[:negative.start()], re.I):
            return True
    return False


@dataclass(frozen=True)
class FeedbackPlan:
    reaction: str
    model: str
    model_digest: str
    message_sha256: str
    prompt_sha256: str
    wall_seconds: float
    kind: str = 'external_social_feedback'


def validate_plan(value, message, model):
    message_valid(message)
    if not isinstance(value, dict) or set(value) != {field.name for field in fields(FeedbackPlan)} or value['kind'] != 'external_social_feedback' or value['reaction'] not in REACTIONS:
        raise ValueError('Invalid social feedback proposal.')
    provenance(value, model)
    if value['message_sha256'] != sha(message) or (guarded(message) and value['reaction'] != 'uncertain'):
        raise ValueError('Feedback changed its message or asserted a guarded evaluation.')
    if value['reaction'] == 'encouraging' and re.search(r'\b(?:não|nao|nunca)\s+(?:\w+\s+){0,2}(?:gostei|gosto|adorei|adoro|curti)\b', message, re.I):
        raise ValueError('Positive feedback ignored an explicit negated appreciation.')
    if value['reaction'] == 'encouraging' and explicit_adverse(message):
        raise ValueError('Positive feedback contradicts an explicit adverse evaluation.')
    return value


def language_source(plan):
    return {'kind': plan['kind'], 'model': plan['model'], 'model_digest': plan['model_digest'],
            'message_sha256': plan['message_sha256'], 'prompt_sha256': plan['prompt_sha256'],
            'plan_sha256': evidence_hash(plan)}


def validate_source(value):
    fields = {'kind', 'model', 'model_digest', 'message_sha256', 'prompt_sha256', 'plan_sha256'}
    if not isinstance(value, dict) or set(value) != fields or value['kind'] != 'external_social_feedback' or any(not isinstance(value[key], str) or not 1 <= len(value[key]) <= 128 or any(ord(char) < 32 for char in value[key]) for key in ('model', 'model_digest')) or any(not isinstance(value[key], str) or re.fullmatch(r'[0-9a-f]{64}', value[key]) is None for key in ('message_sha256', 'prompt_sha256', 'plan_sha256')):
        raise ValueError('Invalid language feedback provenance.')
    return value


class FeedbackLanguage(ConceptQueryLanguage):
    def parse(self, message):
        message_valid(message)
        labels = {'positive': 'encouraging', 'negative': 'discouraging', 'uncertain': 'uncertain'}
        reaction = {'const': 'uncertain'} if guarded(message) else {'type': 'string', 'enum': list(labels)}
        if not guarded(message) and explicit_adverse(message):
            reaction = {'type': 'string', 'enum': ['negative', 'uncertain']}
        schema = {'type': 'object', 'properties': {'reaction': reaction}, 'required': ['reaction'], 'additionalProperties': False}
        draft, metadata = self.request('Classify the sentiment of this person\'s direct feedback in Brazilian Portuguese. '
            'positive: the person liked or approved the interaction. negative: the person disliked it, expressed '
            'dissatisfaction or frustration. In everyday Portuguese, gostar/adorar/apreciar/curtir express liking; '
            'odiar/detestar/reprovar express dislike. Interpret conjugated forms and negation, not substring matches. '
            'uncertain: no evaluation, information request, question, quotation, '
            'hypothetical statement, mixed evaluation or sarcasm. The interaction was already selected outside '
            'this classifier; this/that/what happened can refer to it. Read informal language and negation. '
            'Profanity alone does not determine sentiment. Never infer benefit, effort, truth or Alice\'s own feelings. '
            'Return only reaction.', message, schema)
        if not isinstance(draft, dict) or set(draft) != {'reaction'} or draft['reaction'] not in labels:
            raise ValueError('Feedback classifier changed its schema.')
        plan = FeedbackPlan(labels[draft['reaction']], **metadata, message_sha256=sha(message))
        validate_plan(asdict(plan), message, self.language.model)
        return plan
