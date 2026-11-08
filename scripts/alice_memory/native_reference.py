"""Bounded event provenance without neural imports or remembered sensory values."""
import math
import re

MAX_MOMENT_ID = 1_000_000
MODALITIES = ('image', 'audio', 'text')


def number(value, lower, upper):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError('Invalid event reference time.')


def validate_reference(value, now, next_id=MAX_MOMENT_ID):
    fields = {'id', 'acquired_at', 'known', 'sources', 'source_context'}
    if not isinstance(value, dict) or set(value) != fields or type(value['id']) is not int or not 0 <= value['id'] < next_id or not isinstance(value['known'], list) or len(value['known']) != 3 or any(type(item) is not bool for item in value['known']) or not any(value['known']):
        raise ValueError('Invalid remembered event reference.')
    number(value['acquired_at'], 0, now)
    context = value['source_context']
    if context is not None:
        if not isinstance(context, dict) or set(context) != {'stream_id', 'source_sequence', 'captured_wall', 'received_wall'} or not isinstance(context['stream_id'], str) or re.fullmatch(r'[0-9a-f]{32}', context['stream_id']) is None or type(context['source_sequence']) is not int or not 0 <= context['source_sequence'] < 1000000:
            raise ValueError('Invalid remembered event stream.')
        number(context['captured_wall'], 0, 1e12)
        number(context['received_wall'], context['captured_wall'], context['captured_wall'] + 3600)
    sources = value['sources']
    known = {name for slot, name in enumerate(MODALITIES) if value['known'][slot]}
    if not isinstance(sources, dict) or set(sources) != known:
        raise ValueError('Event reference lost its observed modalities.')
    for source in sources.values():
        if not isinstance(source, dict) or set(source) != {'origin', 'sequence', 'sha256'} or source['origin'] not in ('person', 'environment') or type(source['sequence']) is not int or not 0 <= source['sequence'] <= 1000000 or not isinstance(source['sha256'], str) or re.fullmatch(r'[0-9a-f]{64}', source['sha256']) is None:
            raise ValueError('Invalid remembered event source.')
    return value
