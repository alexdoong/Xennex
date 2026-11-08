"""Persistent neural state with a declared scripted policy for the first loop."""
from __future__ import annotations

import math
from dataclasses import asdict

import torch
from torch.nn import functional as F

from .contracts import Action, Observation, StepResult, interval
from .network import Perception
from .signals import audio_features
from .temporal_core import TemporalSession


class AgentLoop:
    """M1 foundation: no episodic memory/policy-learning claims are made here."""

    def __init__(self, perception: Perception, temporal: TemporalSession) -> None:
        self.perception = perception
        self.temporal = temporal
        self.clock = 0.0
        self.steps = 0
        self.attention = 0
        self.last_sequence: dict[str, int] = {}
        self.last_acquisition: dict[str, float] = {}
        self.last_identity = 0
        self.last_action: Action | None = None
        self.emissions: dict[int, float] = {}
        self.self_feedback = 0
        self.external_feedback = 0
        self.stale = 0
        self.internal_ticks = 0

    @torch.no_grad()
    def step(self, observations: list[Observation], elapsed: float) -> StepResult:
        interval(elapsed)
        if not isinstance(observations, list) or len(observations) > 32:
            raise ValueError("Sensor batch must be a list with at most 32 packets.")
        now = self.clock + elapsed
        for packet in observations:
            packet.validate()
            if packet.acquired_at > now + 1e-8:
                raise ValueError("Observation acquisition time comes from the future.")
        self._start_step()
        self.clock = now
        self.steps += 1
        stale, own, external = 0, 0, 0
        encoded = []
        # Process chronologically, with per-stream watermarks against late/duplicate data.
        for packet in sorted(observations, key=lambda item: (item.acquired_at, item.sequence)):
            stream = packet.modality + ":" + packet.origin
            if packet.sequence <= self.last_sequence.get(stream, -1) or packet.acquired_at < self.last_acquisition.get(stream, -1):
                stale += 1
                continue
            self.last_sequence[stream] = packet.sequence
            self.last_acquisition[stream] = packet.acquired_at
            if not packet.present or packet.quality == 0:
                continue
            if packet.origin == "self" and packet.action_id not in self.emissions:
                stale += 1
                continue
            values = packet.payload.unsqueeze(0)
            if packet.modality == "audio":
                values = audio_features(values)
            feature = self.perception.encode(values, packet.modality)[0]
            encoded.append(feature * packet.quality)
            self._observe_feature(packet, feature)
            if packet.modality == "image" and packet.view == "focused":
                self.last_identity = self._decode_identity(feature)
            if packet.origin == "self":
                own += 1
                self.emissions.pop(packet.action_id)
            if packet.origin == "person":
                external += 1
        if encoded:
            signal = F.normalize(torch.stack(encoded).mean(0), dim=0).unsqueeze(0)
            self.temporal.advance(signal, elapsed)
        else:
            self.temporal.advance(None, elapsed)
            self.internal_ticks += 1
        self.stale += stale
        self.self_feedback += own
        self.external_feedback += external
        # Entries awaiting feedback expire; own sound never directly triggers another emission.
        self.emissions = {key: time for key, time in self.emissions.items() if now - time <= 60}
        action = self._policy()
        self.last_action = action  # Efferent command copy, separate from sensory feedback.
        return StepResult(action, len(encoded), stale, own, external,
                          self.temporal.hidden.norm().item(), not encoded)

    def tick(self, elapsed: float) -> StepResult:
        return self.step([], elapsed)

    def _start_step(self) -> None:
        """Hook after packet validation and before state mutation."""

    def _observe_feature(self, packet: Observation, feature: torch.Tensor) -> None:
        """Receive accepted percepts only, never stale or missing packets."""

    def _decode_identity(self, feature: torch.Tensor) -> int:
        return (feature @ self.perception.anchors.T).argmax().item()

    def _policy(self) -> Action:
        phase = (self.steps - 1) % 8
        if phase in (0, 3, 6):
            self.attention = (self.attention + 1) % 3
            return Action("focus", self.steps, self.clock, target=self.attention)
        if phase in (1, 4):
            return Action("inspect", self.steps, self.clock)
        if phase == 7 and len(self.emissions) < 32:
            self.emissions[self.steps] = self.clock
            return Action("emit", self.steps, self.clock, signal=self.last_identity)
        return Action("wait", self.steps, self.clock)

    def snapshot(self) -> dict:
        return {"clock": self.clock, "steps": self.steps, "attention": self.attention,
                "last_sequence": dict(self.last_sequence), "last_acquisition": dict(self.last_acquisition),
                "last_identity": self.last_identity,
                "last_action": None if self.last_action is None else asdict(self.last_action),
                "emissions": dict(self.emissions), "self_feedback": self.self_feedback,
                "external_feedback": self.external_feedback, "stale": self.stale,
                "internal_ticks": self.internal_ticks}

    def restore_state(self, payload: dict) -> None:
        if not isinstance(payload, dict) or set(payload) != set(self.snapshot()):
            raise ValueError("Invalid agent state fields.")
        if not math.isfinite(payload["clock"]) or payload["clock"] < 0:
            raise ValueError("Invalid agent clock.")
        for name in ("steps", "self_feedback", "external_feedback", "stale", "internal_ticks"):
            if type(payload[name]) is not int or payload[name] < 0:
                raise ValueError("Invalid agent counter.")
        if type(payload["attention"]) is not int or not 0 <= payload["attention"] < 3:
            raise ValueError("Invalid agent attention.")
        if type(payload["last_identity"]) is not int or not 0 <= payload["last_identity"] < 8:
            raise ValueError("Invalid perceived category.")
        valid_streams = {modality + ":" + origin for modality in ("image", "audio")
                         for origin in ("environment", "person", "self")}
        sequences, times = payload["last_sequence"], payload["last_acquisition"]
        if not isinstance(sequences, dict) or not isinstance(times, dict) or set(sequences) != set(times) or not set(sequences) <= valid_streams:
            raise ValueError("Invalid sensor watermarks.")
        if any(type(value) is not int or value < 0 for value in sequences.values()):
            raise ValueError("Invalid sensor sequence watermark.")
        if any(not math.isfinite(value) or not 0 <= value <= payload["clock"] for value in times.values()):
            raise ValueError("Invalid sensor acquisition watermark.")
        emissions = payload["emissions"]
        if not isinstance(emissions, dict) or len(emissions) > 32:
            raise ValueError("Invalid emission queue.")
        if any(type(key) is not int or not 0 <= key <= payload["steps"] or not math.isfinite(value) or not 0 <= value <= payload["clock"] for key, value in emissions.items()):
            raise ValueError("Invalid emission record.")
        action = None if payload["last_action"] is None else Action(**payload["last_action"])
        if action is not None:
            action.validate()
            if action.sequence != payload["steps"] or action.issued_at != payload["clock"]:
                raise ValueError("Agent action does not match its current state.")
        for key, value in payload.items():
            setattr(self, key, dict(value) if isinstance(value, dict) else value)
        self.last_action = action
