"""A learned discrete action policy whose input includes recalled experience.

Questions are four taught field symbols, not natural language. Missing memory
is a masked condition; the policy is trained to wait instead of inventing facts.
"""
from __future__ import annotations

from dataclasses import asdict
import math
from pathlib import Path

import torch
from torch import nn
from torch.nn import functional as F

from .contracts import Action, Observation, interval
from .episodic_session import EpisodicSession, checkpoint_payload as session_payload, restore as restore_session
from .episodic_memory import cue_valid
from .experience_perception import semantic
from .loop_checkpoint import atomic_write
from .process_metrics import Budget


class RecallPolicy(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.layers = nn.Sequential(nn.Linear(40, 64), nn.GELU(), nn.Linear(64, 9))

    def forward(self, current: torch.Tensor, recall: torch.Tensor,
                known: torch.Tensor, field: torch.Tensor) -> torch.Tensor:
        return self.layers(torch.cat((current, recall, known, F.one_hot(field, 4).float()), -1))


def train(policy: RecallPolicy, seed: int, budget: Budget, steps: int = 1200) -> None:
    generator = torch.Generator().manual_seed(seed)
    optimizer = torch.optim.Adam(policy.parameters(), lr=.003)
    for step in range(steps):
        budget.check(step)
        attributes = torch.randint(4, (128, 4), generator=generator)
        known = (torch.rand(128, 4, generator=generator) > .2).float()
        recall = (F.one_hot(attributes, 4).float() * known.unsqueeze(-1)).flatten(1)
        # The current cue omits appraisal/author. It has no hidden target values.
        current = F.one_hot(attributes, 4).float()
        current[:, (1, 2)] = 0
        current = current.flatten(1)
        field = torch.randint(4, (128,), generator=generator)
        rows = torch.arange(128)
        target = torch.where(known[rows, field].bool(), attributes[rows, field], 8)
        loss = F.cross_entropy(policy(current, recall, known, field), target)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
    policy.eval().requires_grad_(False)


class MemoryActor:
    def __init__(self, session: EpisodicSession, policy: RecallPolicy) -> None:
        self.session, self.policy = session, policy
        self.actions = 0
        self.last_action: Action | None = None
        self.pending: dict[int, tuple[int, int, float]] = {}
        self.self_feedback = 0
        self.stale_feedback = 0
        self.last_feedback = torch.zeros(1, 32)
        self.last_error = 0.

    @torch.no_grad()
    def respond(self, cues: list[Observation], field: int, window: tuple[float, float] | None = None,
                view: str = "current", control: str = "memory", replacement: dict | None = None) -> dict:
        if type(field) is not int or not 0 <= field < 4 or control not in ("memory", "none", "shuffled"):
            raise ValueError("Invalid taught question or memory control.")
        self.session.validate_cues(cues, self.session.clock)
        recalled = self.session.query(cues, view, window) if control == "memory" else None
        selected = recalled if control == "memory" else replacement if control == "shuffled" else None
        if control == "shuffled" and replacement is None:
            raise ValueError("Shuffled-memory control needs an explicit replacement.")
        current, _ = semantic(self.session.interpret(cues)[0])
        return self._choose(current, selected, field, recalled, control)

    @torch.no_grad()
    def respond_semantic(self, current: torch.Tensor, field: int,
                         window: tuple[float, float] | None = None) -> dict:
        """Resume a bounded pending task from its already perceived semantic cue."""
        cue_valid(current)
        if type(field) is not int or not 0 <= field < 4:
            raise ValueError("Invalid pending task field.")
        recalled = self.session.memory.read(current, self.session.clock, window=window)
        return self._choose(current, recalled, field, recalled, "memory")

    def _choose(self, current: torch.Tensor, selected: dict | None, field: int,
                recalled: dict | None, control: str) -> dict:
        values = torch.tensor(selected["distributions"] if selected else [[0.] * 4] * 4).reshape(1, 16)
        known = torch.tensor(selected["known"] if selected else [False] * 4).float().unsqueeze(0)
        logits = self.policy(current.float().unsqueeze(0), values, known, torch.tensor([field]))
        code = logits.argmax(-1).item()
        if code not in (0, 1, 2, 3, 8):
            raise ValueError("Policy produced an unsupported taught motor code.")
        self.pending = {key: value for key, value in self.pending.items() if self.session.clock - value[2] <= 60}
        if len(self.pending) >= 32:
            code = 8
        self.actions += 1
        self.last_action = (Action("wait", self.actions, self.session.clock) if code == 8 else
                            Action("emit", self.actions, self.session.clock, signal=code))
        self.last_action.validate()
        if self.last_action.kind == "emit":
            self.pending[self.actions] = (field, code, self.session.clock)
        return {"action": asdict(self.last_action), "recall": recalled, "control": control}

    @torch.no_grad()
    def feedback(self, observations: list[Observation], elapsed: float) -> dict:
        interval(elapsed)
        if not isinstance(observations, list) or len(observations) > 32:
            raise ValueError("Expected at most 32 own-feedback packets.")
        now = self.session.clock + elapsed
        for packet in observations:
            packet.validate()
            if packet.origin != "self" or packet.acquired_at > now + 1e-8:
                raise ValueError("Invalid own-feedback origin/acquisition.")
        pending = dict(self.pending)
        accepted, stale = 0, 0
        feature, error = self.last_feedback, self.last_error
        for packet in observations:
            if packet.action_id not in pending:
                stale += 1
                continue
            field, code, issued = pending[packet.action_id]
            if not packet.present or packet.quality == 0:
                continue
            if packet.acquired_at < issued or now - issued > 60:
                stale += 1
                continue
            probabilities, feature = self.session.interpret([packet])
            error = 1 - probabilities[field, code].item()
            pending.pop(packet.action_id)
            accepted += 1
        # A self percept advances time but never becomes a person's remembered claim.
        self.session.tick(elapsed)
        self.pending = {key: value for key, value in pending.items() if now - value[2] <= 60}
        self.self_feedback += accepted
        self.stale_feedback += stale
        self.last_feedback, self.last_error = feature.clone(), error
        return {"accepted": accepted, "stale": stale, "error": error}


def save(path: Path, actor: MemoryActor) -> None:
    atomic_write(path, checkpoint_payload(actor))


def checkpoint_payload(actor: MemoryActor) -> dict:
    session = session_payload(actor.session)
    return {"format": 25 if session["format"] == 24 else (14 if actor.session.boundary.mask_unobserved else 12), "session": session,
                        "policy": actor.policy.state_dict(), "actions": actor.actions,
                        "last_action": None if actor.last_action is None else asdict(actor.last_action),
                        "feedback": {"pending": dict(actor.pending), "self_feedback": actor.self_feedback,
                                     "stale_feedback": actor.stale_feedback, "last_feedback": actor.last_feedback,
                                     "last_error": actor.last_error},
                        "torch_rng": torch.get_rng_state()}


def load(path: Path) -> MemoryActor:
    from .checkpoint_io import read_checkpoint
    payload = read_checkpoint(path, 8000000)
    return restore(payload)


def restore(payload: dict) -> MemoryActor:
    fields = {"format", "session", "policy", "actions", "last_action", "torch_rng"}
    if isinstance(payload, dict) and payload.get("format") in (12, 14, 25):
        fields.add("feedback")
    if not isinstance(payload, dict) or set(payload) != fields or payload["format"] not in (11, 12, 14, 25):
        raise ValueError("Invalid memory actor format.")
    rng = payload["torch_rng"]
    if not isinstance(rng, torch.Tensor) or rng.dtype != torch.uint8 or rng.shape != torch.get_rng_state().shape:
        raise ValueError("Invalid memory actor RNG.")
    with torch.random.fork_rng(devices=[]):
        session = restore_session(payload["session"])
        if (payload["format"] in (14, 25)) != session.boundary.mask_unobserved:
            raise ValueError("Actor and episodic representation versions disagree.")
        policy = RecallPolicy()
        policy.load_state_dict(payload["policy"], strict=True)
        if any(not torch.isfinite(value).all() for value in policy.state_dict().values()):
            raise ValueError("Nonfinite memory policy weights.")
        if type(payload["actions"]) is not int or payload["actions"] < 0:
            raise ValueError("Invalid action counter.")
        action = None if payload["last_action"] is None else Action(**payload["last_action"])
        if action is not None:
            action.validate()
            if action.sequence != payload["actions"] or action.issued_at > session.clock:
                raise ValueError("Memory action does not match actor state.")
        actor = MemoryActor(session, policy.eval().requires_grad_(False))
        actor.actions, actor.last_action = payload["actions"], action
        if payload["format"] in (12, 14, 25):
            state = payload["feedback"]
            if not isinstance(state, dict) or set(state) != {"pending", "self_feedback", "stale_feedback", "last_feedback", "last_error"}:
                raise ValueError("Invalid actor feedback fields.")
            for counter in ("self_feedback", "stale_feedback"):
                if type(state[counter]) is not int or state[counter] < 0:
                    raise ValueError("Invalid feedback counter.")
            feature = state["last_feedback"]
            if not isinstance(feature, torch.Tensor) or feature.shape != (1, 32) or feature.dtype != torch.float32 or not torch.isfinite(feature).all():
                raise ValueError("Invalid feedback latent.")
            if isinstance(state["last_error"], bool) or not isinstance(state["last_error"], (int, float)) or not math.isfinite(state["last_error"]) or not 0 <= state["last_error"] <= 1:
                raise ValueError("Invalid feedback error.")
            pending = state["pending"]
            if not isinstance(pending, dict) or len(pending) > 32:
                raise ValueError("Invalid pending feedback capacity.")
            for key, value in pending.items():
                if type(key) is not int or not 0 < key <= actor.actions or not isinstance(value, (tuple, list)) or len(value) != 3 or type(value[0]) is not int or not 0 <= value[0] < 4 or type(value[1]) is not int or not 0 <= value[1] < 4 or not math.isfinite(value[2]) or not 0 <= value[2] <= session.clock:
                    raise ValueError("Invalid pending emission record.")
            actor.pending = {key: tuple(value) for key, value in pending.items()}
            actor.self_feedback, actor.stale_feedback = state["self_feedback"], state["stale_feedback"]
            actor.last_feedback, actor.last_error = feature.clone(), state["last_error"]
        # Format 11 explicitly initializes feedback registers empty: that old
        # prototype did not observe own returns, so no historical percept is invented.
    torch.set_rng_state(rng)
    return actor
