"""Test fixture: accepts the real protocol, never imports tracking or Windows input."""
import argparse
import json
import sys
p = argparse.ArgumentParser()
p.add_argument('--camera')
p.add_argument('--config')
args = p.parse_args()
def emit(kind, **data):
    print(json.dumps({'type': kind, **data}), flush=True)
emit('status', message='Fake camera ready', armed=False)
for line in sys.stdin:
    command = json.loads(line)
    kind = command['type']
    if kind == 'stop':
        emit('stopped', armed=False)
        break
    if kind == 'arm':
        emit('frame', armed=command['enabled'], recording=False, points=None, hand=None, match='')
    if kind == 'record':
        emit('recorded', id=command['id'], token=command['token'], sample={'duration': 1, 'frames': [[[.1,.2,0]] * 21], 'hand': 'Right'})
