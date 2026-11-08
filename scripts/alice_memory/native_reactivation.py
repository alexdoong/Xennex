"""Nonverbal reactivation into working state after accepting a new percept.

The coupling gain and ranking prior are supplied experimental policies. No text,
name, language worker or generated belief is required by this mechanism.
"""
import torch
from torch.nn import functional as F


def activate(native, cues, now, exclude, describe=False, *, regions=None):
    query = native.working.clone()
    regional = None
    if regions is not None:
        image = next(cue for cue in cues if cue.modality == 'image')
        regional = native.moments.recall_regions(image, regions, now, exclude=exclude)
    if regional is not None and regional['entries']:
        recalled = {**regional, 'skipped': []}
        native.moments.warm(regional['entries'][0]['candidate']['id'], now)
    else:
        recalled = native.moments.related(cues, now, exclude=exclude, reactivate=True,
            preference=native.recall_preference, contexts=native.recall_context, context=query)
    entries = recalled['entries']
    choice = None if native.recall_preference is None else native.recall_preference.credit(
        entries, native.recall_context, query, native.moments, now)
    if entries:
        states = torch.stack([F.normalize(torch.stack(list(entry['representations'].values())).mean(0), dim=0)
                              for entry in entries])
        weights = torch.tensor([entry['candidate']['priority'] for entry in entries], dtype=torch.float32).softmax(0)
        activation = (states * weights[:, None]).sum(0)
        native.working.copy_(F.normalize(native.working + .25 * activation, dim=0))
        if native.dynamics.last is not None:
            native.dynamics.last['context'] = F.normalize(
                native.dynamics.last['context'] + .25 * activation.double(), dim=0)
    result = {'supported': bool(entries), 'moments': [entry['candidate']['id'] for entry in entries],
            'recall_choice': choice,
            'candidate_count': recalled['candidate_count'], 'skipped': recalled['skipped'],
            'autobiographical_write': False, 'word_learning': False}
    if regional is not None:
        result['visual_route'] = regional['reason']
    if describe:
        from .native_query import tensor_hash
        result['evocations'] = [{'moment_ref': native.moments.reference(entry['candidate']['id']),
            'evoked_sha256': {name: tensor_hash(value) for name, value in entry['representations'].items()}}
            for entry in entries]
    return result
