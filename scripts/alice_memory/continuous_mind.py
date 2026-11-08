"""Persistent perception/memory/action loop with internal work and learned value.

Natural language and the old 16-dimensional predictor are not connected to this
32-dimensional sensory representation. Pending questions use taught field codes.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import torch

from .contracts import Observation, interval
from .episodic_memory import cue_valid
from .experience_perception import semantic
from .importance import Consequence, FunctionalState, Importance, bounded
from .loop_checkpoint import atomic_write
from .memory_actor import MemoryActor, checkpoint_payload as actor_payload, restore as restore_actor


def validate_window(window, clock: float) -> None:
    if window is None:
        return
    if not isinstance(window, (tuple, list)) or len(window) != 2:
        raise ValueError("Invalid task occurrence-time window.")
    for value in window:
        bounded(value, 0, clock)
    if window[0] > window[1]:
        raise ValueError("Reversed task occurrence-time window.")


class ContinuousMind:
    def __init__(self, actor: MemoryActor) -> None:
        self.actor = actor
        from .paged_memory import PagedMemory
        if isinstance(actor.session.memory, PagedMemory):
            from .diagonal_importance import DiagonalImportance
            self.importance = DiagonalImportance(actor.session.memory.capacity)
        else:
            self.importance = Importance(actor.session.memory.capacity)
        self.internal = FunctionalState()
        self.last_cue = torch.zeros(16, dtype=torch.float64)
        self.task: dict | None = None
        self.credits: dict[int, tuple[int, int, float]] = {}
        self.next_evocation = actor.session.clock
        self.last_evoked = -1
        self.evocations = 0
        self.consequences_received = 0
        self.stale_consequences = 0
        self.expired_tasks = 0
        self.unobserved_seconds = 0.
        self.context_reset = True

    @property
    def clock(self) -> float:
        return self.actor.session.clock

    def _expire(self) -> None:
        self.credits = {key: value for key, value in self.credits.items() if self.clock - value[2] <= 60}
        if self.task is not None and self.clock > self.task["expires"]:
            self.expired_tasks += 1
            self.task = None

    @torch.no_grad()
    def perceive(self, observations: list[Observation], elapsed: float) -> dict:
        result = self.actor.session.step(observations, elapsed)
        return self.after_perception(result, elapsed)

    @torch.no_grad()
    def after_perception(self, result: dict, elapsed: float,
                         attended_cue: torch.Tensor | None = None) -> dict:
        """Update internal work after a driver has committed one sensory frame."""
        if attended_cue is not None:
            cue_valid(attended_cue)
            self.last_cue = attended_cue.clone()
            self.last_cue.reshape(4, 4)[(1, 2), :] = 0
        elif result["episode"] is not None:
            if self.context_reset and result["new_episode"] and self.actor.session.boundary.mask_unobserved:
                known = self.actor.session.memory.blocks[result["episode"]].known[1]
                self.actor.session.previous.reshape(4, 4)[~known] = 0
            self.last_cue = self.actor.session.previous[0].double().clone()
            self.last_cue.reshape(4, 4)[(1, 2), :] = 0  # Contextual evocation need not match hidden author/appraisal.
        self._expire()
        self.internal.advance(elapsed, result["encoded"], self.task is not None)
        return result

    @torch.no_grad()
    def revise(self, cues: list[Observation], evidence: list[Observation], field: int,
               elapsed: float, window: tuple[float, float] | None = None) -> dict:
        interval(elapsed)
        validate_window(window, self.clock + elapsed)
        result = self.actor.session.revise(cues, evidence, field, elapsed, window)
        self.actor.pending = {key: value for key, value in self.actor.pending.items() if self.clock - value[2] <= 60}
        self._expire()
        self.internal.advance(elapsed, 2, self.task is not None)
        return result

    @torch.no_grad()
    def request(self, cues: list[Observation], field: int,
                window: tuple[float, float] | None = None) -> None:
        if self.task is not None:
            raise ValueError("The bounded pending-task slot is occupied.")
        if type(field) is not int or not 0 <= field < 4:
            raise ValueError("Invalid taught task field.")
        self.actor.session.validate_cues(cues, self.clock)
        validate_window(window, self.clock)
        current, _ = semantic(self.actor.session.interpret(cues)[0])
        self.request_semantic(current, field, window)

    @torch.no_grad()
    def request_semantic(self, current: torch.Tensor, field: int,
                         window: tuple[float, float] | None = None) -> None:
        """Queue a learned conceptual cue without recording it as perception."""
        if self.task is not None:
            raise ValueError("The bounded pending-task slot is occupied.")
        if type(field) is not int or not 0 <= field < 4:
            raise ValueError("Invalid taught task field.")
        cue_valid(current)
        validate_window(window, self.clock)
        self.last_cue = current.clone()
        self.task = {"cue": current.clone(), "field": field, "window": None if window is None else tuple(window),
                     "issued": self.clock, "due": self.clock + .1, "expires": self.clock + 60}

    @torch.no_grad()
    def tick(self, elapsed: float, mode: str = "learned", pending_intent: bool = False) -> dict:
        interval(elapsed)
        if mode not in ("learned", "fixed", "surprise") or type(pending_intent) is not bool:
            raise ValueError("Invalid internal salience control.")
        self.actor.feedback([], elapsed)
        self._expire()
        self.internal.advance(elapsed, int(pending_intent), self.task is not None or pending_intent)
        if self.internal.energy < .02:
            return {"action": None, "evoked": None, "reason": "functional_work_budget"}
        if self.task is not None and len(self.credits) >= 32:
            return {"action": None, "evoked": None, "reason": "consequence_queue_full"}
        if self.task is not None and self.clock >= self.task["due"]:
            task = self.task
            result = self.actor.respond_semantic(task["cue"], task["field"], task["window"])
            recalled = result["recall"]
            episode = recalled["episode"]
            if episode is not None:
                self.importance.access(episode, self.clock)
                if result["action"]["kind"] == "emit":
                    self.credits[result["action"]["sequence"]] = (episode, task["field"], self.clock)
            self.task = None
            self.internal.advance(0., 1 + recalled["blocks_read"], pending_intent)
            return {"action": result["action"], "recall": recalled, "evoked": None, "resumed_pending": True}
        if self.clock < self.next_evocation or not cue_valid(self.last_cue).any():
            return {"action": None, "evoked": None}
        candidates = self.importance.rank(self.actor.session.memory, self.last_cue, 2, self.clock, mode)
        self.next_evocation = self.clock + 2.
        if not candidates:
            return {"action": None, "evoked": None}
        selected = candidates[0]
        index = selected["episode"]
        # An attention hypothesis may inspect a particular episode internally;
        # this never becomes a factual answer to an ambiguous external question.
        recalled = self.actor.session.memory.read(self.last_cue, self.clock, window=tuple(selected["occurred_at"]))
        self.importance.access(index, self.clock)
        self.last_evoked = index
        self.evocations += 1
        self.internal.advance(0., 1 + recalled["blocks_read"], pending_intent)
        return {"action": None, "evoked": {**selected, "content": recalled},
                "addresses_compared": len(self.actor.session.memory.blocks), "autobiographical_write": False}

    @torch.no_grad()
    def hear(self, observations: list[Observation], elapsed: float) -> dict:
        if not isinstance(observations, list) or len(observations) > 1:
            raise ValueError("This curriculum accepts one motor return per tick.")
        result = self.actor.feedback(observations, elapsed)
        self._expire()
        if result["accepted"] and observations[0].action_id in self.credits:
            episode = self.credits[observations[0].action_id][0]
            self.importance.observe_surprise(episode, result["error"])
            self.internal.novelty = result["error"]
        self.internal.advance(elapsed, result["accepted"], self.task is not None)
        return result

    @torch.no_grad()
    def consequences(self, items: list[Consequence], elapsed: float) -> dict:
        interval(elapsed)
        if not isinstance(items, list) or len(items) > 32:
            raise ValueError("Consequences exceed the bounded return queue.")
        now = self.clock + elapsed
        for item in items:
            item.validate()
            if item.acquired_at > now + 1e-8:
                raise ValueError("Consequence comes from the future.")
        self.actor.feedback([], elapsed)
        self._expire()
        accepted, stale = 0, 0
        for item in items:
            credit = self.credits.get(item.action_id)
            if credit is None or item.acquired_at < credit[2]:
                stale += 1
                continue
            episode, field, _ = self.credits.pop(item.action_id)
            self.importance.learn(episode, field, item)
            self.internal.observe(item)
            accepted += 1
        self.consequences_received += accepted
        self.stale_consequences += stale
        self.internal.advance(elapsed, accepted, self.task is not None)
        return {"accepted": accepted, "stale": stale}

    def unobserved_gap(self, elapsed: float) -> None:
        """Elapsed offline time is unknown experience, never imaginary perception."""
        bounded(elapsed, 0, 7 * 24 * 3600)
        remaining = elapsed
        while remaining > 0:
            step = min(60., remaining)
            self.actor.feedback([], step)
            self.internal.advance(step, 0, False)
            remaining -= step
        self._expire()
        self.unobserved_seconds += elapsed
        self.next_evocation = max(self.next_evocation, self.clock)

    def snapshot(self) -> dict:
        task = None if self.task is None else {**self.task, "cue": self.task["cue"].clone()}
        return {"internal": asdict(self.internal), "last_cue": self.last_cue.clone(), "task": task,
                "credits": dict(self.credits), "next_evocation": self.next_evocation, "last_evoked": self.last_evoked,
                "evocations": self.evocations, "consequences_received": self.consequences_received,
                "stale_consequences": self.stale_consequences, "expired_tasks": self.expired_tasks,
                "unobserved_seconds": self.unobserved_seconds}


def save(path: Path, mind: ContinuousMind) -> None:
    atomic_write(path, checkpoint_payload(mind))


def checkpoint_payload(mind: ContinuousMind) -> dict:
    payload = {"format": 18 if mind.context_reset else 15, "actor": actor_payload(mind.actor),
               "importance": mind.importance.state_dict(), "state": mind.snapshot(), "torch_rng": torch.get_rng_state()}
    if mind.context_reset:
        payload["context_reset"] = True
    from .diagonal_importance import DiagonalImportance
    if isinstance(mind.importance, DiagonalImportance):
        payload.update(format=26, importance_kind="diagonal-onehot-v1")
    return payload


def load(path: Path) -> ContinuousMind:
    from .checkpoint_io import read_checkpoint
    payload = read_checkpoint(path, 8000000)
    return restore(payload)


def restore(payload: dict) -> ContinuousMind:
    fields = {"format", "actor", "importance", "state", "torch_rng"}
    if isinstance(payload, dict) and payload.get("format") in (18, 26):
        fields.add("context_reset")
    if isinstance(payload, dict) and payload.get("format") == 26:
        fields.add("importance_kind")
    if not isinstance(payload, dict) or set(payload) != fields or payload["format"] not in (15, 18, 26):
        raise ValueError("Invalid continuous mind checkpoint.")
    if payload["format"] in (18, 26) and payload["context_reset"] is not True:
        raise ValueError("Invalid continuous context reset configuration.")
    rng = payload["torch_rng"]
    if not isinstance(rng, torch.Tensor) or rng.dtype != torch.uint8 or rng.shape != torch.get_rng_state().shape:
        raise ValueError("Invalid continuous mind RNG.")
    with torch.random.fork_rng(devices=[]):
        mind = ContinuousMind(restore_actor(payload["actor"]))
        from .diagonal_importance import DiagonalImportance
        if (payload["format"] == 26) != isinstance(mind.importance, DiagonalImportance) or (payload["format"] == 26 and payload["importance_kind"] != "diagonal-onehot-v1"):
            raise ValueError("Learned-value architecture does not match its checkpoint.")
        mind.context_reset = payload["format"] != 15
        expected = mind.importance.state_dict()
        if not isinstance(payload["importance"], dict) or set(payload["importance"]) != set(expected):
            raise ValueError("Invalid learned-value tensor fields.")
        for name, template in expected.items():
            tensor = payload["importance"][name]
            if not isinstance(tensor, torch.Tensor) or tensor.shape != template.shape or tensor.dtype != template.dtype:
                raise ValueError("Invalid learned-value tensor shape/type.")
        mind.importance.load_state_dict(payload["importance"], strict=True)
        validate_importance(mind)
        state = payload["state"]
        if not isinstance(state, dict) or set(state) != set(mind.snapshot()):
            raise ValueError("Invalid continuous mind state fields.")
        mind.internal = FunctionalState(**state["internal"])
        mind.internal.validate()
        cue_valid(state["last_cue"])
        mind.last_cue = state["last_cue"].clone()
        for name in ("evocations", "consequences_received", "stale_consequences", "expired_tasks"):
            if type(state[name]) is not int or state[name] < 0:
                raise ValueError("Invalid continuous mind counter.")
            setattr(mind, name, state[name])
        for name in ("next_evocation", "unobserved_seconds"):
            bounded(state[name], 0, float("inf"))
            setattr(mind, name, state[name])
        if mind.unobserved_seconds > mind.clock:
            raise ValueError("Unobserved duration exceeds elapsed time.")
        index = state["last_evoked"]
        if type(index) is not int or not -1 <= index < len(mind.actor.session.memory.blocks):
            raise ValueError("Invalid evoked episode reference.")
        mind.last_evoked = index
        validate_task(state["task"], mind.clock)
        mind.task = state["task"]
        validate_credits(state["credits"], mind)
        mind.credits = {key: tuple(value) for key, value in state["credits"].items()}
    torch.set_rng_state(rng)
    return mind


def validate_task(task: dict | None, clock: float) -> None:
    if task is None:
        return
    if not isinstance(task, dict) or set(task) != {"cue", "field", "window", "issued", "due", "expires"}:
        raise ValueError("Invalid pending internal task.")
    cue_valid(task["cue"])
    if type(task["field"]) is not int or not 0 <= task["field"] < 4:
        raise ValueError("Invalid pending internal field.")
    bounded(task["issued"], 0, clock)
    bounded(task["due"], task["issued"], task["issued"] + 60)
    bounded(task["expires"], task["due"], task["issued"] + 60)
    if task["expires"] < clock:
        raise ValueError("Expired pending task in checkpoint.")
    validate_window(task["window"], task["issued"])


def validate_credits(credits: dict, mind: ContinuousMind) -> None:
    if not isinstance(credits, dict) or len(credits) > 32:
        raise ValueError("Invalid consequence attribution capacity.")
    for key, value in credits.items():
        if type(key) is not int or not 1 <= key <= mind.actor.actions or not isinstance(value, (tuple, list)) or len(value) != 3:
            raise ValueError("Invalid consequence attribution.")
        episode, field, issued = value
        mind.importance.key(episode, field)
        if episode >= len(mind.actor.session.memory.blocks):
            raise ValueError("Attribution references an absent episode.")
        bounded(issued, max(0., mind.clock - 60), mind.clock)


def validate_importance(mind: ContinuousMind) -> None:
    value = mind.importance
    for tensor in value.state_dict().values():
        if not torch.isfinite(tensor).all():
            raise ValueError("Nonfinite importance state.")
    if (value.updates < 0).any() or (value.accesses < 0).any() or value.updates.sum() != value.values.writes:
        raise ValueError("Inconsistent learned-value counters.")
    if (value.last_access < -1).any() or (value.last_access > mind.clock).any() or (value.surprise < 0).any() or (value.surprise > 1).any():
        raise ValueError("Invalid reactivation/surprise state.")
    if ((value.accesses == 0) != (value.last_access == -1)).any():
        raise ValueError("Inconsistent memory access clocks.")
    size = len(mind.actor.session.memory.blocks)
    if value.updates[size:].any() or value.accesses[size:].any() or value.surprise[size:].any():
        raise ValueError("Importance refers to absent episodes.")
    precision = value.values.precision
    if precision.ndim == 1:
        if (precision <= 0).any() or (precision > 1000).any():
            raise ValueError("Invalid diagonal importance precision.")
        return
    if not torch.allclose(precision, precision.T, atol=1e-8) or torch.linalg.cholesky_ex(precision).info.item() != 0:
        raise ValueError("Invalid learned-value covariance.")
