"""Use a sound to retrieve a name learned on remembered vision."""
from .native_sensor import NativeObservation
from .native_reference import validate_reference

MAX_SOURCES = 4


def recognize(native, sound, before):
    """Return a sourced association, without adding a name, memory, or sensation."""
    if not isinstance(sound, NativeObservation) or sound.modality != 'audio' or sound.origin == 'self' or type(before) is not int or not 0 <= before <= native.moments.next_id:
        raise ValueError('Visual naming by sound requires an external cue and a prior-moment boundary.')
    sound.validate()
    if not any('image' in source['samples'] for source in native.sources):
        return {'supported': False, 'reason': 'no_learned_visual_names'}
    memory = native.moments
    matches = memory.recall([sound], native.clock, reactivate=False, candidates_only=True)['candidates']
    paired = [candidate['id'] for candidate in matches
              if candidate['id'] < before and candidate['acquired_at'] <= sound.acquired_at and candidate['known'][0]]
    if not paired:
        return {'supported': False, 'reason': 'no_matching_audio_visual_moment'}
    if len(paired) > MAX_SOURCES:
        return {'supported': False, 'reason': 'too_many_matching_moments'}
    names, references = set(), []
    for index in sorted(paired):
        recalled = memory.read_candidate(index, [sound], ['image'])
        if recalled['reason'] == 'outside_associative_coverage':
            continue
        if not recalled['supported']:
            return {'supported': False, 'reason': recalled['reason']}
        ref = memory.reference(index)
        visual_source = ref['sources']['image']
        visual = NativeObservation('image', recalled['representations']['image'], ref['acquired_at'],
                                   visual_source['sequence'], visual_source['sha256'], origin=visual_source['origin'])
        name = native.recognize(visual)
        if not name['supported']:
            return {'supported': False, 'reason': 'remembered_image_has_no_supported_name'}
        names.add(name['name'])
        references.append(ref)
    if not references:
        return {'supported': False, 'reason': 'outside_associative_coverage'}
    if len(names) != 1:
        return {'supported': False, 'reason': 'conflicting_visual_names'}
    return {'supported': True, 'name': next(iter(names)), 'sources': references,
            'kind': 'remembered_visual_name', 'directly_observed': False, 'word_learning': False,
            'autobiographical_write': False}


def validate_association(result, native, current):
    fields = {'supported', 'name', 'sources', 'kind', 'directly_observed', 'word_learning', 'autobiographical_write'}
    if (not isinstance(result, dict) or set(result) != fields or result['supported'] is not True
            or result['kind'] != 'remembered_visual_name'
            or any(result[key] is not False for key in ('directly_observed', 'word_learning', 'autobiographical_write'))
            or not isinstance(result['sources'], list) or not 1 <= len(result['sources']) <= MAX_SOURCES):
        raise ValueError('Invalid saved sound-to-image association.')
    if not any(record['name'] == result['name'] and 'image' in record['samples'] for record in native.sources):
        raise ValueError('Saved sound association lacks an externally taught visual name.')
    previous = -1
    for ref in result['sources']:
        validate_reference(ref, current['acquired_at'], current['id'])
        if ref['id'] <= previous or not {'image', 'audio'} <= set(ref['sources']):
            raise ValueError('Saved sound association lacks a distinct earlier audiovisual episode.')
        actual = native.moments.reference(ref['id'])
        if actual is not None and actual != ref:
            raise ValueError('Saved sound association changed its supporting episode.')
        previous = ref['id']
