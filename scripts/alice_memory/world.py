"""A bounded, causal 2D laboratory world with delayed acoustic feedback."""
from __future__ import annotations

import math
import random

import torch
from PIL import Image, ImageDraw

from .contracts import Action, Observation, interval
from .signals import COLORS, image_tensor, synthetic_audio, synthetic_image


class SyntheticWorld:
    """Only observations go to the agent; oracle() is an evaluation-only interface."""

    def __init__(self, seed: int = 17) -> None:
        if type(seed) is not int or not 0 <= seed <= 1_000_000:
            raise ValueError("Seed must be between 0 and 1000000.")
        self.seed = seed
        self.rng = random.Random(seed)
        self._objects = self.rng.sample(range(8), 3)
        self.clock = 0.0
        self.steps = 0
        self.focus = 0
        self.inspected = False
        self.sequence = 0
        self.last_action = -1
        self.pending: list[dict] = []
        self._heard: list[Observation] = []

    def advance(self, elapsed: float, action: Action | None = None) -> list[Observation]:
        interval(elapsed)
        if action is not None:
            action.validate()
            if action.sequence <= self.last_action or action.issued_at > self.clock + 1e-8:
                raise ValueError("Action is duplicate or comes from the future.")
            if action.kind in ("inspect", "emit") and len(self.pending) >= 32:
                raise ValueError("World feedback queue reached its bounded capacity.")
        now = self.clock + elapsed
        if action is not None:
            self._apply(action)
        self.clock = now
        self.steps += 1
        # A simulated person occasionally replaces an object; no boundary marker is sent.
        if self.steps % 32 == 0:
            slot = self.rng.randrange(3)
            alternatives = [value for value in range(8) if value not in self._objects]
            self._objects[slot] = self.rng.choice(alternatives)
        self._heard = []
        remaining = []
        for item in self.pending:
            if item["due"] > now:
                remaining.append(item)
                continue
            self._heard.append(self._observation(
                "audio", synthetic_audio(item["signal"], self.rng), item["due"],
                item["origin"], item["action_id"]))
        self.pending = remaining
        return self.observe()

    def _apply(self, action: Action) -> None:
        self.last_action = action.sequence
        if action.kind == "focus":
            self.focus = action.target
            self.inspected = False
        if action.kind == "inspect":
            self.inspected = True
            self.pending.append({"due": self.clock + .2, "signal": self._objects[self.focus],
                                 "origin": "person", "action_id": action.sequence})
        if action.kind == "emit":
            self.pending.append({"due": self.clock + .3, "signal": action.signal,
                                 "origin": "self", "action_id": action.sequence})

    def _observation(self, modality: str, payload: torch.Tensor, acquired_at: float,
                     origin: str = "environment", action_id: int | None = None,
                     present: bool = True, view: str = "focused") -> Observation:
        result = Observation(modality, payload, acquired_at, self.sequence, origin,
                             present, 1.0 if present else 0.0, action_id, view)
        self.sequence += 1
        return result

    def observe(self) -> list[Observation]:
        visible = self.inspected or self.steps % 13 != 0
        picture = synthetic_image(self._objects[self.focus], self.rng) if visible else Image.new("RGB", (32, 32))
        # Acquisition order can differ from delivery order; each packet carries its own time.
        return [self._observation("image", image_tensor(picture), self.clock,
                                  present=visible), *self._heard]

    def render(self) -> Image.Image:
        """Inspect the scene visually without using its truth labels as model input."""
        scene = Image.new("RGB", (128, 96), (18, 22, 28))
        draw = ImageDraw.Draw(scene)
        person_x = 48 + self.steps % 24
        draw.ellipse((person_x, 6, person_x + 12, 18), fill=(220, 180, 140))
        draw.rectangle((person_x - 2, 18, person_x + 14, 38), fill=(70, 130, 200))
        for slot, identity in enumerate(self._objects):
            x = 10 + slot * 40
            draw.rectangle((x, 55, x + 25, 80), fill=COLORS[identity])
            if slot == self.focus:
                draw.rectangle((x - 2, 53, x + 27, 82), outline=(240, 240, 240), width=2)
        return scene

    def oracle(self) -> dict:
        return {"objects": list(self._objects), "focus": self.focus,
                "steps": self.steps, "clock": self.clock}

    def snapshot(self) -> dict:
        return {"seed": self.seed, "rng": self.rng.getstate(), "objects": list(self._objects),
                "clock": self.clock, "steps": self.steps, "focus": self.focus,
                "inspected": self.inspected, "sequence": self.sequence,
                "last_action": self.last_action, "pending": [dict(item) for item in self.pending]}

    @classmethod
    def restore(cls, payload: dict) -> SyntheticWorld:
        fields = {"seed", "rng", "objects", "clock", "steps", "focus", "inspected",
                  "sequence", "last_action", "pending"}
        if not isinstance(payload, dict) or set(payload) != fields:
            raise ValueError("Invalid world snapshot fields.")
        world = cls(payload["seed"])
        objects = payload["objects"]
        if not isinstance(objects, list) or len(objects) != 3 or len(set(objects)) != 3:
            raise ValueError("World must contain three distinct objects.")
        if any(type(value) is not int or not 0 <= value < 8 for value in objects):
            raise ValueError("Invalid world object code.")
        if not math.isfinite(payload["clock"]) or payload["clock"] < 0:
            raise ValueError("Invalid world clock.")
        for name in ("steps", "sequence"):
            if type(payload[name]) is not int or payload[name] < 0:
                raise ValueError("Invalid world counter.")
        if type(payload["focus"]) is not int or not 0 <= payload["focus"] < 3:
            raise ValueError("Invalid world focus.")
        if type(payload["inspected"]) is not bool or type(payload["last_action"]) is not int or payload["last_action"] < -1:
            raise ValueError("Invalid world action state.")
        pending = payload["pending"]
        if not isinstance(pending, list) or len(pending) > 32:
            raise ValueError("Invalid world queue.")
        for item in pending:
            if not isinstance(item, dict) or set(item) != {"due", "signal", "origin", "action_id"}:
                raise ValueError("Invalid queued feedback fields.")
            if not math.isfinite(item["due"]) or item["due"] <= payload["clock"]:
                raise ValueError("Feedback deadline must follow the world clock.")
            if type(item["signal"]) is not int or not 0 <= item["signal"] < 8:
                raise ValueError("Invalid queued signal.")
            if item["origin"] not in ("self", "person") or type(item["action_id"]) is not int or not 0 <= item["action_id"] <= payload["last_action"]:
                raise ValueError("Invalid queued feedback origin.")
        try:
            world.rng.setstate(payload["rng"])
        except (ValueError, TypeError) as error:
            raise ValueError("Invalid world random state.") from error
        world._objects = list(objects)
        for name in ("clock", "steps", "focus", "inspected", "sequence", "last_action"):
            setattr(world, name, payload[name])
        world.pending = [dict(item) for item in pending]
        return world
