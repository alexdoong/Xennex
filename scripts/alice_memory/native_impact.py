"""Episode-local consequence values in diagonal one-hot RLS weights."""
import torch
from torch import nn


class MomentValues(nn.Module):
    def __init__(self, capacity):
        super().__init__()
        self.register_buffer('weights', torch.zeros(capacity, 3, dtype=torch.float64))
        self.register_buffer('precision', torch.full((capacity,), 1000., dtype=torch.float64))
        self.register_buffer('updates', torch.zeros(capacity, dtype=torch.int64))

    @torch.no_grad()
    def write(self, slot, outcome):
        outcome.validate()
        if type(slot) is not int or not 0 <= slot < len(self.weights) or int(self.updates[slot]):
            raise ValueError('Episode impact has already been credited or lacks a slot.')
        variance = self.precision[slot].clone()
        gain = variance / (.1 + variance)
        target = torch.tensor([outcome.benefit, outcome.social, outcome.effort], dtype=torch.float64)
        self.weights[slot].add_(gain * (target - self.weights[slot]))
        self.precision[slot].sub_(gain * variance)
        self.updates[slot] += 1

    def read(self, slot):
        if not int(self.updates[slot]):
            return {'supported': False, 'value': 0., 'impact': 0.}
        benefit, social, effort = self.weights[slot].clamp(-1, 1).tolist()
        value = benefit + .5 * social - .25 * max(0., effort)
        return {'supported': True, 'value': value, 'impact': min(1., abs(value))}

    @torch.no_grad()
    def retire(self, slot, count):
        for tensor, default in ((self.weights, 0.), (self.precision, 1000.), (self.updates, 0)):
            if slot < count - 1:
                tensor[slot:count-1].copy_(tensor[slot+1:count].clone())
            tensor[count-1].fill_(default)

    def snapshot(self):
        return {key: value.clone() for key, value in self.state_dict().items()}


def restore(payload, capacity, traces):
    model = MomentValues(capacity)
    expected = model.state_dict()
    if not isinstance(payload, dict) or set(payload) != set(expected) or any(not isinstance(tensor, torch.Tensor) or tensor.device.type != 'cpu' or tensor.dtype != expected[key].dtype or tensor.shape != expected[key].shape or not torch.isfinite(tensor).all() for key, tensor in payload.items()):
        raise ValueError('Invalid episode consequence tensors.')
    model.load_state_dict(payload)
    written = model.updates.bool()
    if any(int(model.updates[index]) != int(trace['impact'] is not None) for index, trace in enumerate(traces)) or model.updates[len(traces):].count_nonzero() or (model.updates < 0).any() or (model.updates > 1).any():
        raise ValueError('Episode impact counts disagree with their sources.')
    trained_precision = 1000. - 1000. * (1000. / 1000.1)
    if not torch.equal(model.precision[~written], torch.full_like(model.precision[~written], 1000.)) or not torch.allclose(model.precision[written], torch.full_like(model.precision[written], trained_precision), atol=1e-8, rtol=0) or model.weights[~written].count_nonzero() or model.weights.abs().max() > 1.00001 or (model.weights[:, 2] < 0).any():
        raise ValueError('Episode impact contains hidden or invalid learned state.')
    return model
