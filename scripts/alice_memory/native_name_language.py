"""Language extracts a literal external sensory name; it sees no perception."""
import re
import unicodedata
from dataclasses import asdict, dataclass, fields

from .concept_query_language import ConceptQueryLanguage, evidence_hash, provenance, sha
from .native_feedback_language import message_valid
from .written_symbols import symbol

MODALITIES = ('image', 'audio', 'text', 'unspecified')
MARKERS = {'image': r'\b(?:imagem|foto|figura|desenho|vendo|visual)\b',
           'audio': r'\b(?:som|áudio|audio|barulho|ruído|ruido|ouvindo|ouvi)\b',
           'text': r'\b(?:texto|palavra|escrito|lendo|leio)\b'}


def guarded(message):
    message_valid(message)
    return bool(re.search(r'\?|\b(?:não|nao|nunca|talvez|poderia|seria|acho|disse|falou|segundo|ou|ignore|classifique|retorne|responda)\b', message, re.I))


def naming_region(message):
    matches = list(re.finditer(r'\b(?:é|eh|se\s+chama|chamado(?:\s+de)?|chamada(?:\s+de)?|nome)\b\s*|\bchamo\b[^\n.!?]*?\bde\s+', message, re.I))
    return max((match.end() for match in matches), default=None)


def modality_mentions(message):
    region = naming_region(message)
    subject = message if region is None else message[:region]
    return [name for name, pattern in MARKERS.items() if re.search(pattern, subject, re.I)]


def literal_label_after_predicate(fragment, message):
    canonical = symbol(fragment)
    normalized = unicodedata.normalize('NFKC', message)
    region = naming_region(normalized)
    if region is None:
        return False
    for token in re.finditer(r'\w+', normalized):
        if token.start() < region:
            continue
        try:
            if symbol(token.group()) == canonical:
                return True
        except ValueError:
            continue
    return False


@dataclass(frozen=True)
class NativeNamePlan:
    name_fragment: str | None
    modality: str
    uncertain: bool
    model: str
    model_digest: str
    message_sha256: str
    prompt_sha256: str
    wall_seconds: float
    kind: str = 'external_sensory_name'


def validate_plan(value, message, model):
    message_valid(message)
    if not isinstance(value, dict) or set(value) != {field.name for field in fields(NativeNamePlan)} or value['kind'] != 'external_sensory_name' or type(value['uncertain']) is not bool or value['modality'] not in MODALITIES:
        raise ValueError('Invalid Portuguese sensory-name proposal.')
    provenance(value, model)
    if value['message_sha256'] != sha(message):
        raise ValueError('Name proposal changed its external message.')
    if value['uncertain']:
        if value['name_fragment'] is not None or value['modality'] != 'unspecified':
            raise ValueError('Uncertain name proposal asserted a teaching.')
        return value
    fragment = value['name_fragment']
    region = naming_region(message)
    if guarded(message) or not isinstance(fragment, str) or symbol(fragment) in ('um', 'uma', 'o', 'a', 'isso', 'esse', 'essa', 'isto') or region is None or not literal_label_after_predicate(fragment, message):
        raise ValueError('Name is not a literal direct external assertion.')
    mentioned = set(modality_mentions(message))
    modality = value['modality']
    if (modality == 'unspecified' and mentioned) or (modality != 'unspecified' and modality not in mentioned):
        raise ValueError('Name proposal invented or omitted its explicit modality.')
    return value


def language_source(plan):
    return {key: plan[key] for key in ('kind', 'model', 'model_digest', 'message_sha256', 'prompt_sha256')} | {'plan_sha256': evidence_hash(plan)}


def validate_source(value):
    if isinstance(value, dict) and value.get('kind') == 'external_word_reply':
        if set(value) != {'kind', 'reply_sha256', 'request_sha256'} or any(not isinstance(value[key], str) or re.fullmatch(r'[0-9a-f]{64}', value[key]) is None for key in ('reply_sha256', 'request_sha256')):
            raise ValueError('Invalid direct word-reply provenance.')
        return value
    expected = {'kind', 'model', 'model_digest', 'message_sha256', 'prompt_sha256', 'plan_sha256'}
    if not isinstance(value, dict) or set(value) != expected or value['kind'] != 'external_sensory_name' or any(not isinstance(value[key], str) or not 1 <= len(value[key]) <= 128 or any(ord(char) < 32 for char in value[key]) for key in ('model', 'model_digest')) or any(not isinstance(value[key], str) or re.fullmatch(r'[0-9a-f]{64}', value[key]) is None for key in ('message_sha256', 'prompt_sha256', 'plan_sha256')):
        raise ValueError('Invalid sensory-name language provenance.')
    return value


class NativeNameLanguage(ConceptQueryLanguage):
    def parse(self, message):
        message_valid(message)
        mentioned = modality_mentions(message)
        protected = guarded(message) or naming_region(message) is None or len(mentioned) > 1
        schema = {'type': 'object', 'properties': {'name_fragment': {'const': None} if protected else
            {'type': ['string', 'null'], 'maxLength': 32}}, 'required': ['name_fragment'], 'additionalProperties': False}
        draft, metadata = self.request('Copy the single word AFTER the naming predicate in this Portuguese sentence. '
            'é means is; se chama means is called. Skip articles um/uma/o/a and quotes. '
            'The subject BEFORE the predicate is not the name to copy. Invented names are valid. '
            'Copy exactly from the message; never translate or identify an object yourself. '
            'Return null when no clear single-word name is taught. Profanity does not cancel a lesson. '
            'Only name_fragment is requested.', message, schema)
        if not isinstance(draft, dict) or set(draft) != {'name_fragment'}:
            raise ValueError('Sensory name parser changed its schema.')
        unclear = draft['name_fragment'] is None
        modality = 'unspecified' if unclear or not mentioned else mentioned[0]
        plan = NativeNamePlan(draft['name_fragment'], modality, unclear, **metadata, message_sha256=sha(message))
        validate_plan(asdict(plan), message, self.language.model)
        return plan
