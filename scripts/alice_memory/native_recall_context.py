"""Episode-associated prior working context in one-hot-address RLS weights."""
import copy

import torch
from torch.nn import functional as F

from .native_links import context_value
from .native_sensor import DIMENSION


class RecallContexts:
    def __init__(self, capacity):
        from .native_moments import CAPACITY
        if type(capacity) is not int or not 1 <= capacity <= CAPACITY:
            raise ValueError('Invalid episodic context capacity.')
        self.capacity = capacity
        self.ids = []
        self.weights = torch.zeros(capacity, DIMENSION, dtype=torch.float64)
        self.precision = torch.full((capacity,), 1000., dtype=torch.float64)
        self.written = torch.zeros(capacity, dtype=torch.bool)

    def sync(self, moments):
        ids = [trace['id'] for trace in moments.traces]
        if ids == self.ids:
            return
        old = {number: slot for slot, number in enumerate(self.ids)}
        weights, precision, written = self.weights.clone(), self.precision.clone(), self.written.clone()
        self.weights.zero_(); self.precision.fill_(1000.); self.written.zero_()
        for slot, number in enumerate(ids):
            if number in old:
                self.weights[slot] = weights[old[number]]
                self.precision[slot] = precision[old[number]]
                self.written[slot] = written[old[number]]
        self.ids = ids

    @torch.no_grad()
    def capture(self, moments, number, context):
        context = context_value(context)
        if number != moments.next_id - 1 or number in self.ids:
            raise ValueError('Past observed context cannot be supplied after the experience.')
        self.sync(moments)
        slot = moments.slot(number)
        if slot is None or self.written[slot]:
            raise ValueError('Recall context requires a new retained moment.')
        if context.norm() < .05:
            return
        projected = self.precision[slot].clone()
        self.weights[slot] += (context - self.weights[slot]) * projected / (.1 + projected)
        self.precision[slot] -= projected.square() / (.1 + projected)
        self.written[slot] = True

    def read(self, number):
        if number not in self.ids:
            return None
        slot = self.ids.index(number)
        value = self.weights[slot]
        if not self.written[slot] or value.norm() < .05:
            return None
        return F.normalize(value, dim=0)

    def snapshot(self):
        return {'format': 1, 'ids': self.ids.copy(), 'weights': self.weights.clone(),
                'precision': self.precision.clone(), 'written': self.written.clone()}


def restore(payload, moments):
    if not isinstance(payload, dict) or set(payload) != {'format', 'ids', 'weights', 'precision', 'written'} or type(payload['format']) is not int or payload['format'] != 1 or not isinstance(payload['ids'], list) or any(type(x) is not int for x in payload['ids']) or payload['ids'] != [x['id'] for x in moments.traces]:
        raise ValueError('Recall contexts changed their retained episode addresses.')
    result = RecallContexts(moments.capacity)
    for key in ('weights', 'precision', 'written'):
        value, expected = payload[key], getattr(result, key)
        if not isinstance(value, torch.Tensor) or value.device.type != 'cpu' or value.dtype != expected.dtype or value.shape != expected.shape or not torch.isfinite(value).all():
            raise ValueError('Invalid recall context tensors.')
        setattr(result, key, value.clone())
    mask = result.written
    trained = 1000. - 1000.**2 / 1000.1
    if mask[len(payload['ids']):].any() or result.weights[~mask].count_nonzero() or not torch.equal(result.precision[~mask], torch.full_like(result.precision[~mask], 1000.)) or not torch.allclose(result.precision[mask], torch.full_like(result.precision[mask], trained), atol=1e-8, rtol=0) or (result.weights[mask].norm(dim=-1) > 1.00001).any():
        raise ValueError('Recall context contains unsupported or hidden state.')
    result.ids = copy.deepcopy(payload['ids'])
    return result
