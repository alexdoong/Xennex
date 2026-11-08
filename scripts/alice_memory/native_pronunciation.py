"""A bounded vocabulary learned from external word and waveform pairings."""
import copy
import math
from collections import Counter

from .concept_memory import scalar
from .native_reference import validate_reference
from .spoken_pattern import MAX_DISTANCE, MIN_MARGIN, distance, validate as validate_pattern
from .written_symbols import symbol

MAX_EXAMPLES = 32
MAX_PER_WORD = 4


def teach(memory, moment, word, pattern):
    trace = memory.get(moment)
    if trace is None or set(trace['sources']) != {'audio'} or trace['sources']['audio']['origin'] != 'person':
        raise ValueError('A pronunciation lesson requires an attended external audio-only moment.')
    word = symbol(word)
    validate_pattern(pattern)
    records = memory.pronunciations
    digest = trace['sources']['audio']['sha256']
    for record in records.values():
        if record['audio_sha256'] == digest:
            return {'status': 'duplicate' if record['word'] == word else 'conflicting_example'}
    sample = pattern.detach().clone()
    same_word = sorted(index for index, record in records.items() if record['word'] == word)
    if len(same_word) >= MAX_PER_WORD:
        del records[same_word[0]]
    if len(records) >= MAX_EXAMPLES:
        del records[min(records)]
    records[moment] = {'word': word, 'audio_sha256': digest, 'pattern': sample}
    return {'status': 'learned', 'word': word}


def recognize(memory, moment, pattern):
    trace = memory.get(moment)
    if trace is None or set(trace['sources']) != {'audio'}:
        raise ValueError('An acoustic word query requires an attended audio-only moment.')
    validate_pattern(pattern)
    by_word = {}
    for index, record in memory.pronunciations.items():
        if index >= moment or memory.get(index)['acquired_at'] > trace['acquired_at']:
            continue
        score = distance(record['pattern'], pattern)
        if math.isfinite(score):
            word = record['word']
            by_word[word] = min(by_word.get(word, (math.inf, index)), (score, index))
    ranked = sorted((score, index, word) for word, (score, index) in by_word.items())
    if not ranked or ranked[0][0] > MAX_DISTANCE:
        return {'status': 'unmatched'}
    score, index, word = ranked[0]
    margin = None if len(ranked) < 2 else ranked[1][0] - score
    if margin is not None and margin < MIN_MARGIN:
        return {'status': 'ambiguous'}
    return {'status': 'heard', 'word': word, 'distance': score, 'margin': margin,
            'source': memory.reference(index)}


def restore_examples(records, traces):
    if not isinstance(records, dict) or not 1 <= len(records) <= min(len(traces), MAX_EXAMPLES):
        raise ValueError('Invalid saved acoustic vocabulary size.')
    moments = {trace['id']: trace for trace in traces}
    counts, digests = Counter(), set()
    for index, record in records.items():
        if (type(index) is not int or index not in moments or not isinstance(record, dict)
                or set(record) != {'word', 'audio_sha256', 'pattern'} or symbol(record['word']) != record['word']):
            raise ValueError('Invalid saved pronunciation lesson.')
        sources = moments[index]['sources']
        digest = record['audio_sha256']
        if set(sources) != {'audio'} or sources['audio']['origin'] != 'person' or sources['audio']['sha256'] != digest or digest in digests:
            raise ValueError('Saved pronunciation lost its external auditory source.')
        validate_pattern(record['pattern'])
        counts[record['word']] += 1
        digests.add(digest)
    if any(count > MAX_PER_WORD for count in counts.values()):
        raise ValueError('Saved pronunciation exceeds its per-word budget.')
    return copy.deepcopy(records)


def validate_result(result, memory, current, attended, name):
    if not isinstance(result, dict) or 'status' not in result:
        raise ValueError('Invalid saved pronunciation result.')
    status = result['status']
    if not attended:
        if result != {'status': 'unattended'}:
            raise ValueError('Unattended speech cannot teach or match an acoustic word.')
        return
    if current is None or set(current['sources']) != {'audio'}:
        raise ValueError('A saved acoustic word requires its audio-only experience.')
    if status == 'learned' and name is not None and result == {'status': 'learned', 'word': name}:
        record = memory.pronunciations.get(current['id'])
        if record is not None and record['word'] != name:
            raise ValueError('A saved pronunciation changed its written lesson.')
        return
    if set(result) == {'status'} and (status == 'unusable_audio' or status in (
            ('duplicate', 'conflicting_example') if name is not None else ('unmatched', 'ambiguous'))):
        return
    if (name is not None or status != 'heard' or set(result) != {'status', 'word', 'distance', 'margin', 'source'}
            or symbol(result['word']) != result['word']):
        raise ValueError('Invalid saved acoustic word match.')
    scalar(result['distance'], 0, MAX_DISTANCE)
    if result['margin'] is not None:
        scalar(result['margin'], MIN_MARGIN, 201.)
    ref = validate_reference(result['source'], current['acquired_at'], current['id'])
    if set(ref['sources']) != {'audio'} or ref['sources']['audio']['origin'] != 'person':
        raise ValueError('Saved acoustic word lacks an earlier pronunciation lesson.')
    retained = memory.reference(ref['id'])
    record = memory.pronunciations.get(ref['id'])
    if (retained is not None and retained != ref) or (record is not None and record['word'] != result['word']):
        raise ValueError('Saved acoustic word changed its earlier lesson.')
