"""Learned query latents and context-dependent attention, without factual writes.

Four latches retain working representations until an explicit replacement/release.
Retention is architectural; their meaning/decoding and attention are trained.
Inputs are grounded sensory cues and parser fields, not hidden LLM activations.
"""
from __future__ import annotations

import torch
from torch import nn

from .episodic_memory import cue_valid
from .experience_perception import semantic
from .word_grounding import sensory_digest


def source(agent) -> dict:
    return {"perception": sensory_digest(agent.mind.actor.session.perception),
            "temporal": sensory_digest(agent.temporal.core), "kind": agent.temporal.core.kind}


class TaskModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder = nn.Sequential(nn.Linear(21, 48), nn.GELU(), nn.Linear(48, 32), nn.Tanh())
        self.decoder = nn.Linear(32, 25)
        self.priority = nn.Sequential(nn.Linear(96, 64), nn.GELU(), nn.Linear(64, 1))

    def encode(self, cues, fields):
        intent = torch.nn.functional.one_hot(fields, 5).to(cues.dtype)
        return self.encoder(torch.cat((cues, intent), -1))

    def decode(self, latent):
        return self.decoder(latent).reshape(-1, 5, 5)

    def score(self, latent, context):
        return self.priority(torch.cat((latent, context), -1)).flatten()


class TaskSlots:
    def __init__(self, model: TaskModel, source_identity: dict):
        if not isinstance(model, TaskModel):
            raise ValueError("Neural tasks require the fixed task model architecture.")
        self.model = model.eval().requires_grad_(False)
        with torch.random.fork_rng(devices=[]):
            validate_weights(self.model.state_dict(), TaskModel())
        self.source = dict(source_identity)
        self.slots = torch.zeros(4, 32)
        self.identifiers = torch.full((4,), -1, dtype=torch.int64)
        self.enabled = torch.zeros(4, dtype=torch.bool)
        self.updates = 0

    def index(self, identifier: int):
        if type(identifier) is not int or not 1 <= identifier < 1000000:
            raise ValueError("Invalid neural task identifier.")
        matches = torch.where(self.identifiers == identifier)[0]
        return int(matches[0]) if len(matches) else None

    @torch.no_grad()
    def store(self, identifier: int, cue: torch.Tensor, field: int = 4, enabled=True):
        cue_valid(cue)
        if type(field) is not int or not 0 <= field <= 4 or type(enabled) is not bool or self.updates >= 2000000:
            raise ValueError("Invalid neural task field/source/budget.")
        index = self.index(identifier)
        if index is None:
            free = torch.where(self.identifiers == -1)[0]
            if not len(free):
                raise ValueError("Neural working-task capacity reached.")
            index = int(free[0])
        latent = self.model.encode(cue.float().unsqueeze(0), torch.tensor([field]))[0]
        if not torch.isfinite(latent).all():
            raise ValueError("Nonfinite neural task activation.")
        self.slots[index] = latent
        self.identifiers[index] = identifier
        self.enabled[index] = enabled
        self.updates += 1

    def release(self, identifier: int):
        index = self.index(identifier)
        if index is not None:
            self.slots[index].zero_()
            self.identifiers[index] = -1
            self.enabled[index] = False

    @torch.no_grad()
    def decode(self, identifier: int) -> dict:
        index = self.index(identifier)
        empty = {"supported": False, "cue": torch.zeros(16, dtype=torch.float64), "field": 4, "confidence": 0.}
        if index is None or not self.enabled[index] or not self.slots[index].count_nonzero():
            return empty
        probabilities = self.model.decode(self.slots[index:index + 1])[0].softmax(-1)
        cue, known = semantic(probabilities[:4])
        confidence, field = probabilities[4].max(-1)
        return {"supported": bool(known.any()), "cue": cue,
                "field": int(field) if confidence >= .8 else 4, "confidence": float(confidence)}

    @torch.no_grad()
    def score(self, identifier: int, context: torch.Tensor) -> float:
        if not isinstance(context, torch.Tensor) or context.dtype != torch.float32 or context.device.type != "cpu" or context.shape != (1, 64) or not torch.isfinite(context).all():
            raise ValueError("Neural attention requires the paired temporal hidden state.")
        index = self.index(identifier)
        if index is None or not self.decode(identifier)["supported"]:
            return 0.
        return float(self.model.score(self.slots[index:index + 1], context).sigmoid()[0])

    def snapshot(self):
        return {"source": dict(self.source), "model": {name: value.clone() for name, value in self.model.state_dict().items()},
                "slots": self.slots.clone(), "identifiers": self.identifiers.clone(),
                "enabled": self.enabled.clone(), "updates": self.updates}


def restore(payload: dict, agent) -> TaskSlots:
    if not isinstance(payload, dict) or set(payload) != {"source", "model", "slots", "identifiers", "enabled", "updates"}:
        raise ValueError("Invalid neural task checkpoint fields.")
    if payload["source"] != source(agent):
        raise ValueError("Neural task model and mind representation differ.")
    with torch.random.fork_rng(devices=[]):
        model = TaskModel()
        validate_weights(payload["model"], model)
        model.load_state_dict(payload["model"], strict=True)
        result = TaskSlots(model, payload["source"])
    for name, shape, dtype in (("slots", (4, 32), torch.float32), ("identifiers", (4,), torch.int64), ("enabled", (4,), torch.bool)):
        tensor = payload[name]
        if not isinstance(tensor, torch.Tensor) or tensor.device.type != "cpu" or tensor.shape != shape or tensor.dtype != dtype:
            raise ValueError("Invalid neural task storage type/shape.")
        setattr(result, name, tensor.clone())
    if not torch.isfinite(result.slots).all() or (result.slots.abs() > 1.00001).any():
        raise ValueError("Invalid neural task activation range.")
    identifiers = result.identifiers[result.identifiers != -1].tolist()
    if len(set(identifiers)) != len(identifiers) or any(not 1 <= identifier < 1000000 for identifier in identifiers):
        raise ValueError("Invalid neural task slot identities.")
    empty = result.identifiers == -1
    if result.enabled[empty].any() or result.slots[empty].count_nonzero():
        raise ValueError("Unowned neural task slots contain state.")
    if type(payload["updates"]) is not int or not 0 <= payload["updates"] <= 2000000 or payload["updates"] < len(identifiers):
        raise ValueError("Invalid neural task update count.")
    result.updates = payload["updates"]
    return result


def validate_weights(state, model):
    expected = model.state_dict()
    if not isinstance(state, dict) or set(state) != set(expected):
        raise ValueError("Invalid task model weight fields.")
    for name, tensor in state.items():
        if not isinstance(tensor, torch.Tensor) or tensor.device.type != "cpu" or tensor.dtype != expected[name].dtype or tensor.shape != expected[name].shape or not torch.isfinite(tensor).all():
            raise ValueError("Invalid task model weight type/shape/finitude.")
