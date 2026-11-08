"""Conservative projection inferred from contrasts in learned neural outputs.

This is a fixed statistical rule over the kernel's learned function, not a
meta-trained attention gate. It keeps no targets. At most one field is ignored,
and only when contrasts support two other varying, influential fields.
"""
from __future__ import annotations

import torch
from torch import nn


def probabilities(values):
    values = values.clamp_min(0)
    return values / values.sum(-1, keepdim=True).clamp_min(1e-10)


class SupportProjection(nn.Module):
    def __init__(self):
        super().__init__()
        self.register_buffer("effects", torch.zeros(3, dtype=torch.float64))
        self.register_buffer("contrasts", torch.zeros(3, dtype=torch.int64))
        self.register_buffer("contexts", torch.zeros(3, dtype=torch.int64))
        self.register_buffer("ignored", torch.tensor(-1, dtype=torch.int64))
        self.register_buffer("fitted_writes", torch.tensor(0, dtype=torch.int64))

    @torch.no_grad()
    def fit(self, bank, index):
        keys = index.keys[:int(index.count)]
        self.effects.zero_()
        self.contrasts.zero_()
        self.contexts.zero_()
        self.ignored.fill_(-1)
        self.fitted_writes.copy_(bank.writes)
        if len(keys) < 4:
            return
        identities = keys.reshape(-1, 3, 4).argmax(-1)
        outputs = probabilities(bank.network(keys))
        confident = outputs.max(-1).values >= .8
        if not bool(confident.all()):
            return
        left, right = torch.triu_indices(len(keys), len(keys), offset=1)
        for field in range(3):
            others = [axis for axis in range(3) if axis != field]
            eligible = ((identities[left][:, others] == identities[right][:, others]).all(-1) &
                        (identities[left, field] != identities[right, field]) & confident[left] & confident[right])
            a, b = left[eligible], right[eligible]
            if not len(a):
                continue
            contexts = identities[a][:, others].unique(dim=0)
            # Reject variations drawn only from one value of another field.
            if any(len(contexts[:, axis].unique()) < 2 for axis in range(2)):
                continue
            self.effects[field] = (.5 * (outputs[a] - outputs[b]).abs().sum(-1)).max()
            self.contrasts[field] = len(a)
            self.contexts[field] = len(contexts)
        established = (self.contrasts >= 4) & (self.contexts >= 4)
        candidates = [field for field in range(3) if bool(established[field]) and self.effects[field] <= .15
                      and all(bool(established[other]) and self.effects[other] >= .35
                              for other in range(3) if other != field)]
        if candidates:
            self.ignored.fill_(min(candidates, key=lambda field: self.effects[field].item()))

    def snapshot(self):
        return {name: value.clone() for name, value in self.state_dict().items()}

    def restore(self, payload, bank, index):
        if not isinstance(payload, dict) or set(payload) != set(self.state_dict()):
            raise ValueError("Invalid learned-projection fields.")
        for name, expected in self.state_dict().items():
            value = payload[name]
            if not isinstance(value, torch.Tensor) or value.device.type != "cpu" or value.dtype != expected.dtype or value.shape != expected.shape or not torch.isfinite(value).all():
                raise ValueError("Invalid learned-projection tensor.")
        # Recompute from the saved function/routes, rather than trust a manually
        # supplied field mask or effects. An unused legacy module fits lazily.
        self.fit(bank, index)
        if any(not torch.equal(payload[name], value) for name, value in self.state_dict().items()):
            raise ValueError("Learned projection disagrees with its neural evidence.")
