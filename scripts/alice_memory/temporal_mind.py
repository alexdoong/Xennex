"""Causal coupling of learned 32-d anticipation to the persistent mind.

Only external accepted percepts update the temporal observation state. Own
speech uses its existing source-aware feedback path; its efferent copy is marked
as conversation, never as an activity-control instruction.
"""
from __future__ import annotations

import json
from pathlib import Path

import torch

from .continuous_mind import ContinuousMind, checkpoint_payload as mind_payload, restore as restore_mind
from .importance import bounded
from .loop_checkpoint import atomic_write
from .temporal32 import Temporal32, Temporal32Session
from .temporal32 import action_features
from .contracts import Action


def load_models(path: Path, kind: str = "multi") -> tuple[dict, Temporal32]:
    if path.stat().st_size > 2_000_000 or kind not in ("multi", "gru"):
        raise ValueError("Invalid temporal model size or architecture.")
    report_path = path.parent / "report.json"
    if report_path.stat().st_size > 32768:
        raise ValueError("Temporal validation report exceeds its size limit.")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(report, dict) or report.get("accepted") is not True:
        raise ValueError("Temporal models have not passed their evaluation gate.")
    payload = torch.load(path, map_location="cpu", weights_only=True)
    if not isinstance(payload, dict) or set(payload) != {"format", "perception", "models", "torch_rng"} or payload["format"] != 20:
        raise ValueError("Temporal runtime requires the paired gated-context model format 20.")
    with torch.random.fork_rng(devices=[]):
        core = Temporal32(kind)
        expected = core.state_dict()
        tensors = payload["models"][kind]
        if not isinstance(tensors, dict) or set(tensors) != set(expected):
            raise ValueError("Invalid temporal model tensor fields.")
        for name, value in tensors.items():
            if not isinstance(value, torch.Tensor) or value.dtype != expected[name].dtype or value.shape != expected[name].shape:
                raise ValueError("Invalid temporal model tensor type/shape.")
        core.load_state_dict(tensors, strict=True)
        if any(not torch.isfinite(value).all() for value in core.state_dict().values()):
            raise ValueError("Nonfinite temporal model weights.")
    return payload["perception"], core.eval().requires_grad_(False)


class TemporalMind:
    def __init__(self, mind: ContinuousMind, core: Temporal32, source_perception: dict) -> None:
        actual = mind.actor.session.perception.state_dict()
        if not isinstance(source_perception, dict) or set(source_perception) != set(actual):
            raise ValueError("Temporal perception contract mismatch.")
        if any(not isinstance(source_perception[name], torch.Tensor) or source_perception[name].dtype != value.dtype
               or not torch.equal(value, source_perception[name])
               for name, value in actual.items()):
            raise ValueError("Temporal model and mind use different sensory weights.")
        self.mind = mind
        self.temporal = Temporal32Session(core, mind.clock)

    def issue_scripted(self, code: int | None, purpose: int = 0) -> Action:
        """Explicit experiment actuator; separate from the learned answer policy."""
        action_features(code, purpose)
        actor = self.mind.actor
        if code is not None and len(actor.pending) >= 32:
            raise ValueError("Scripted actuator return queue is full.")
        actor.actions += 1
        action = Action("wait", actor.actions, self.clock) if code is None else Action("emit", actor.actions, self.clock, signal=code)
        actor.last_action = action
        if code is not None:
            actor.pending[action.sequence] = (purpose, code, self.clock)
        self.temporal.predict(code, purpose)
        return action

    @property
    def clock(self) -> float:
        return self.mind.clock

    def perceive(self, observations, elapsed: float) -> dict:
        result = self.mind.perceive(observations, elapsed)
        return self.after_perception(result, elapsed)

    def after_perception(self, result: dict, elapsed: float) -> dict:
        """Advance the predictor once, independently of episodic frame routing."""
        latent = self.mind.actor.session.joint[0] if result["encoded"] else None
        self.temporal.advance(latent, elapsed)
        if latent is not None:
            # Distance between normalized vectors, not calibrated probability.
            self.mind.internal.novelty = min(1., self.temporal.last_error * 8)
        return {**result, "forecast_error": self.temporal.last_error, "forecast_is_hypothesis": True}

    def request(self, cues, field: int, window=None) -> None:
        self.mind.request(cues, field, window)

    def revise(self, cues, evidence, field: int, elapsed: float, window=None) -> dict:
        result = self.mind.revise(cues, evidence, field, elapsed, window)
        # Evidence about an old event must not replace the current sensory scene.
        self.temporal.advance(None, elapsed)
        return result

    def tick(self, elapsed: float, mode: str = "learned", pending_intent: bool = False) -> dict:
        result = self.mind.tick(elapsed, mode, pending_intent)
        self.temporal.advance(None, elapsed)
        if result["action"] is not None and result["action"]["kind"] == "emit":
            self.temporal.predict(result["action"]["signal"], 2)  # Speech, irrespective of asked field.
        return {**result, "forecast_is_hypothesis": True}

    def hear(self, observations, elapsed: float) -> dict:
        result = self.mind.hear(observations, elapsed)
        self.temporal.advance(None, elapsed)
        return result

    def consequences(self, items, elapsed: float) -> dict:
        result = self.mind.consequences(items, elapsed)
        self.temporal.advance(None, elapsed)
        return result

    def unobserved_gap(self, elapsed: float) -> None:
        bounded(elapsed, 0, 7 * 24 * 3600)
        self.mind.unobserved_gap(elapsed)
        remaining = elapsed
        while remaining > 0:
            step = min(60., remaining)
            self.temporal.advance(None, step)
            remaining -= step

    def forecasts(self) -> dict:
        return {"available": self.temporal.observations > 0, "hypothesis": True,
                "next_external_latent": self.temporal.last_prediction[0, 0].tolist(),
                "later_context_latent": self.temporal.last_prediction[0, 1].tolist(),
                "observations": self.temporal.observations, "error": self.temporal.last_error}


def save(path: Path, agent: TemporalMind) -> None:
    atomic_write(path, checkpoint_payload(agent))


def checkpoint_payload(agent: TemporalMind) -> dict:
    if abs(agent.clock - agent.temporal.clock) > 1e-8:
        raise ValueError("Mind and temporal clocks are unsynchronized.")
    base = mind_payload(agent.mind)
    return {"format": 27 if base["format"] == 26 else 21, "mind": base, "kind": agent.temporal.core.kind,
                        "core": agent.temporal.core.state_dict(), "temporal": agent.temporal.snapshot(),
            "torch_rng": torch.get_rng_state()}


def load(path: Path) -> TemporalMind:
    from .checkpoint_io import read_checkpoint
    payload = read_checkpoint(path, 12000000)
    return restore(payload)


def restore(payload: dict) -> TemporalMind:
    if not isinstance(payload, dict) or set(payload) != {"format", "mind", "kind", "core", "temporal", "torch_rng"} or payload["format"] not in (21, 27):
        raise ValueError("Invalid temporal mind checkpoint.")
    if payload["kind"] not in ("multi", "gru"):
        raise ValueError("Invalid temporal mind architecture.")
    rng = payload["torch_rng"]
    if not isinstance(rng, torch.Tensor) or rng.dtype != torch.uint8 or rng.shape != torch.get_rng_state().shape:
        raise ValueError("Invalid temporal mind RNG.")
    with torch.random.fork_rng(devices=[]):
        mind = restore_mind(payload["mind"])
        from .paged_memory import PagedMemory
        if (payload["format"] == 27) != isinstance(mind.actor.session.memory, PagedMemory):
            raise ValueError("Temporal memory architecture mismatch.")
        core = Temporal32(payload["kind"])
        expected = core.state_dict()
        if not isinstance(payload["core"], dict) or set(payload["core"]) != set(expected):
            raise ValueError("Invalid temporal tensor fields.")
        for name, tensor in payload["core"].items():
            if not isinstance(tensor, torch.Tensor) or tensor.dtype != expected[name].dtype or tensor.shape != expected[name].shape or not torch.isfinite(tensor).all():
                raise ValueError("Invalid temporal tensor type/value.")
        core.load_state_dict(payload["core"], strict=True)
        agent = TemporalMind(mind, core, mind.actor.session.perception.state_dict())
        state = payload["temporal"]
        if not isinstance(state, dict) or set(state) != set(agent.temporal.snapshot()):
            raise ValueError("Invalid temporal session fields.")
        for name in ("hidden", "last_prediction", "command"):
            value, template = state[name], agent.temporal.snapshot()[name]
            if not isinstance(value, torch.Tensor) or value.dtype != template.dtype or value.shape != template.shape or not torch.isfinite(value).all():
                raise ValueError("Invalid temporal session tensor.")
        bounded(state["clock"], mind.clock - 1e-8, mind.clock + 1e-8)
        bounded(state["last_error"], 0, .126)
        if type(state["observations"]) is not int or not 0 <= state["observations"] <= mind.actor.session.steps:
            raise ValueError("Invalid temporal observation count.")
        command = state["command"]
        if not ((command == 0) | (command == 1)).all() or (command[0, 8] == 0 and command.sum() != 0) or (command[0, 8] == 1 and (command[0, :4].sum() != 1 or command[0, 4:8].sum() != 1)):
            raise ValueError("Invalid temporal efferent copy.")
        predicted = core.forecast(state["hidden"], command)
        if not torch.allclose(predicted, state["last_prediction"], atol=1e-5):
            raise ValueError("Temporal prediction does not match the restored state.")
        for name, value in state.items():
            setattr(agent.temporal, name, value.clone() if isinstance(value, torch.Tensor) else value)
    torch.set_rng_state(rng)
    return agent
