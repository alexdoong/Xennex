"""Lexical learning and conceptual queries in the persistent audiovisual mind."""
from __future__ import annotations

import math
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

import torch

from .consolidating_mind import ConsolidatingMind, checkpoint_payload as agent_payload, restore as restore_agent
from .continuous_mind import validate_window
from .loop_checkpoint import atomic_write
from .word_grounding import WordGrounding, restore as restore_words, symbol


@dataclass(frozen=True)
class WrittenName:
    text: str
    acquired_at: float
    sequence: int
    origin: str = "person"
    action_id: int | None = None

    def validate(self):
        symbol(self.text)
        if isinstance(self.acquired_at, bool) or not isinstance(self.acquired_at, (int, float)) or not math.isfinite(self.acquired_at) or self.acquired_at < 0:
            raise ValueError("Invalid written-name acquisition time.")
        if type(self.sequence) is not int or self.sequence < 0 or self.origin not in ("person", "environment", "self"):
            raise ValueError("Invalid written-name origin/sequence.")
        if self.action_id is not None and (type(self.action_id) is not int or self.action_id < 1):
            raise ValueError("Invalid lexical action reference.")
        if self.origin == "self" and self.action_id is None:
            raise ValueError("Self-origin names require an action reference.")


class GroundedMind:
    def __init__(self, agent: ConsolidatingMind, capacity: int = 128):
        self.agent = agent
        self.words = WordGrounding(agent.mind.actor.session.perception, capacity)
        self.context: dict | None = None
        self.label_sequence: dict[str, int] = {}
        self.label_time: dict[str, float] = {}

    @property
    def mind(self):
        return self.agent.mind

    @property
    def temporal(self):
        return self.agent.temporal

    @property
    def semantic(self):
        return self.agent.semantic

    @property
    def clock(self):
        return self.agent.clock

    def perceive(self, observations, elapsed: float) -> dict:
        session = self.mind.actor.session
        previous = dict(session.last_sequence)
        previous_time = dict(session.last_acquisition)
        result = self.agent.perceive(observations, elapsed)
        self.context = None
        if result["encoded"] and sum(result["known"]) == 1:
            accepted = [packet for packet in observations if packet.origin != "self" and packet.present
                        and packet.quality > 0 and packet.sequence > previous.get(packet.modality + ":" + packet.origin, -1)]
            accepted = [packet for packet in accepted if packet.acquired_at >= previous_time.get(packet.modality + ":" + packet.origin, -1)]
            self.context = {"latent": session.joint[0].clone(),
                            "acquired_at": max(packet.acquired_at for packet in accepted),
                            "step": session.steps, "consumed": False}
        return result

    def teach_name(self, item: WrittenName) -> dict:
        if not isinstance(item, WrittenName):
            raise ValueError("A lexical lesson requires a typed written-name input.")
        item.validate()
        if item.acquired_at > self.clock + 1e-8:
            raise ValueError("Lexical lesson comes from the future.")
        if item.origin == "self":
            return {"learned": False, "reason": "self_generated_name"}
        if item.sequence <= self.label_sequence.get(item.origin, -1) or item.acquired_at < self.label_time.get(item.origin, -1):
            return {"learned": False, "reason": "stale_label"}
        context = self.context
        if context is None or context["consumed"] or context["step"] != self.mind.actor.session.steps or abs(context["acquired_at"] - item.acquired_at) > .025:
            return {"learned": False, "reason": "no_synchronized_attended_percept"}
        result = self.words.teach(item.text, context["latent"], self.clock)
        context["consumed"] = True
        self.label_sequence[item.origin], self.label_time[item.origin] = item.sequence, item.acquired_at
        return result

    def query_names(self, names: list[str], view="current", window=None) -> dict:
        if view not in ("initial", "current"):
            raise ValueError("Unknown episodic interpretation.")
        validate_window(window, self.clock)
        grounding = self.words.cue(names)
        if not grounding["supported"]:
            return {"grounding_supported": False, "reason": grounding["reason"], "result": None}
        result = self.mind.actor.session.memory.read(grounding["cue"], self.clock, view, window)
        return {"grounding_supported": True, "names": grounding["names"], "result": result,
                "concept_activation_is_hypothesis": True, "autobiographical_write": False}

    def request_names(self, names: list[str], field: int, window=None) -> dict:
        if type(field) is not int or not 0 <= field < 4:
            raise ValueError("Invalid requested field.")
        validate_window(window, self.clock)
        grounding = self.words.cue(names)
        if not grounding["supported"]:
            return {"queued": False, "reason": grounding["reason"]}
        self.mind.request_semantic(grounding["cue"], field, window)
        return {"queued": True, "concept_activation_is_hypothesis": True, "autobiographical_write": False}

    def expect_names(self, names: list[str], field: int) -> dict:
        """A learned regularity, never evidence that a particular event occurred."""
        if type(field) is not int or not 0 <= field < 4:
            raise ValueError("Invalid expectation field.")
        result = {"kind": "learned_expectation", "autobiographical_write": False,
                  "grounding_supported": False, "prediction": None}
        if field != self.semantic.target:
            return {**result, "reason": "target_not_learned"}
        grounding = self.words.cue(names)
        if not grounding["supported"]:
            return {**result, "reason": grounding["reason"]}
        prediction = self.semantic.predict(grounding["cue"])
        return {**result, "grounding_supported": True, "names": grounding["names"],
                "prediction": prediction, "reason": prediction.get("reason", "supported hypothesis" if prediction["supported"] else "unsupported hypothesis")}

    def tick(self, *args, **kwargs):
        result = self.agent.tick(*args, **kwargs)
        self.context = None
        return result

    def request(self, *args, **kwargs):
        return self.agent.request(*args, **kwargs)

    def revise(self, *args, **kwargs):
        result = self.agent.revise(*args, **kwargs)
        self.context = None
        return result

    def hear(self, *args, **kwargs):
        result = self.agent.hear(*args, **kwargs)
        self.context = None
        return result

    def consequences(self, *args, **kwargs):
        result = self.agent.consequences(*args, **kwargs)
        self.context = None
        return result

    def issue_scripted(self, *args, **kwargs):
        return self.agent.issue_scripted(*args, **kwargs)

    def unobserved_gap(self, elapsed: float):
        result = self.agent.unobserved_gap(elapsed)
        self.context = None
        return result

    def consolidate_current(self):
        return self.agent.consolidate_current()

    def expand_capacity(self, capacity: int):
        return self.agent.expand_capacity(capacity)

    def expect(self, *args, **kwargs):
        return self.agent.expect(*args, **kwargs)


def save(path: Path, agent: GroundedMind):
    atomic_write(path, checkpoint_payload(agent))


def checkpoint_payload(agent: GroundedMind):
    from .scene_mind import SceneGroundedMind
    if isinstance(agent, SceneGroundedMind):
        return agent.snapshot()
    return base_checkpoint_payload(agent)


def base_checkpoint_payload(agent: GroundedMind):
    context = None if agent.context is None else {**agent.context, "latent": agent.context["latent"].clone()}
    return {"format": 29, "agent": agent_payload(agent.agent), "words": agent.words.snapshot(),
                        "context": context, "label_sequence": dict(agent.label_sequence),
                        "label_time": dict(agent.label_time), "torch_rng": torch.get_rng_state()}


def load(path: Path) -> GroundedMind:
    from .checkpoint_io import read_checkpoint
    return restore(read_checkpoint(path, 12_000_000))


def restore(payload: dict) -> GroundedMind:
    if isinstance(payload, dict) and payload.get("format") == 35:
        from .scene_mind import restore as restore_scene
        return restore_scene(payload)
    fields = {"format", "agent", "words", "context", "label_sequence", "label_time", "torch_rng"}
    if not isinstance(payload, dict) or set(payload) != fields or payload["format"] != 29:
        raise ValueError("Invalid grounded mind checkpoint fields.")
    rng = payload["torch_rng"]
    if not isinstance(rng, torch.Tensor) or rng.dtype != torch.uint8 or rng.shape != torch.get_rng_state().shape:
        raise ValueError("Invalid grounded mind RNG.")
    with torch.random.fork_rng(devices=[]), ExitStack() as cleanup:
        agent = restore_agent(payload["agent"])
        from .paged_memory import PagedMemory
        if isinstance(agent.mind.actor.session.memory, PagedMemory):
            cleanup.callback(agent.mind.actor.session.memory.close)
        result = GroundedMind(agent)
        result.words = restore_words(payload["words"], agent.mind.actor.session.perception, agent.clock)
        sequence, times = payload["label_sequence"], payload["label_time"]
        if not isinstance(sequence, dict) or not isinstance(times, dict) or set(sequence) != set(times) or not set(sequence) <= {"person", "environment"} or any(type(v) is not int or v < 0 for v in sequence.values()) or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= result.clock for v in times.values()):
            raise ValueError("Invalid lexical source watermarks.")
        result.label_sequence, result.label_time = dict(sequence), dict(times)
        context = payload["context"]
        if context is not None:
            if not isinstance(context, dict) or set(context) != {"latent", "acquired_at", "step", "consumed"}:
                raise ValueError("Invalid lexical teaching context.")
            value = context["latent"]
            time = context["acquired_at"]
            if not isinstance(value, torch.Tensor) or value.dtype != torch.float32 or value.shape != (32,) or not torch.isfinite(value).all() or not torch.isclose(value.norm(), torch.tensor(1.), atol=1e-5):
                raise ValueError("Invalid attended lexical latent.")
            if isinstance(time, bool) or not isinstance(time, (int, float)) or not math.isfinite(time) or not 0 <= time <= result.clock or type(context["step"]) is not int or context["step"] != result.mind.actor.session.steps or type(context["consumed"]) is not bool:
                raise ValueError("Invalid teaching-context clock/counter.")
            if not torch.equal(value, result.mind.actor.session.joint[0]):
                raise ValueError("Teaching context differs from the last sensory state.")
        result.context = None if context is None else {**context, "latent": context["latent"].clone()}
        cleanup.pop_all()
    torch.set_rng_state(rng)
    return result
