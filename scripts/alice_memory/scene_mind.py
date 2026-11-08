"""Localized concurrent events in one temporal, lexical and episodic mind.

Attention is an explicit region choice in this synthetic curriculum. Event
correspondence is learned; temporal prediction still attends one region, and
its quality on concurrent scenes has not been calibrated.
"""
from __future__ import annotations

import copy
import sqlite3
from contextlib import ExitStack

import torch

from .grounded_mind import GroundedMind, base_checkpoint_payload, restore as restore_grounded
from .paged_memory import PagedMemory
from .scene_memory import ConcurrentEventSession, restore_binding


def region_valid(region):
    if type(region) is not int or region not in (0, 1):
        raise ValueError("Attention requires one of the two localized regions.")


class SceneGroundedMind(GroundedMind):
    def __init__(self, grounded: GroundedMind, binding, binding_source, focus_region=0):
        region_valid(focus_region)
        if type(grounded) is not GroundedMind:
            raise ValueError("A scene driver requires an unwrapped grounded mind.")
        base = grounded.mind.actor.session
        if abs(grounded.temporal.clock - base.clock) > 1e-8:
            raise ValueError("Scene and temporal clocks must agree.")
        self.scene = ConcurrentEventSession(base, binding, binding_source)
        self.agent, self.words = grounded.agent, grounded.words
        self.context = None
        self.label_sequence, self.label_time = dict(grounded.label_sequence), dict(grounded.label_time)
        self.focus_region = focus_region

    @torch.no_grad()
    def perceive(self, observations, elapsed: float, focus_region=None) -> dict:
        focus = self.focus_region if focus_region is None else focus_region
        region_valid(focus)
        previous_episodes = [track["episode"] for track in self.scene.tracks]
        frame = self.scene.step(observations, elapsed)
        self.focus_region = focus
        attended = next((item for item in self.scene.current_regions if item["region"] == focus), None)
        event = next((item for item in frame["events"] if item["region"] == focus), None)
        base = self.scene.base
        if attended is not None:
            # Present evidence stays distinct from merged historical track cues.
            base.joint = attended["joint"].clone()
            base.previous = attended["cue"].float().unsqueeze(0).clone()
            base.seen = bool(attended["known"].any())
            base.since_observation = 0.
            base.last_boundary = event["boundary_probability"] if event else 0.
        result = {**frame, "episode": event["episode"] if event else None,
                  "new_episode": event["new_episode"] if event else False,
                  "boundary_probability": event["boundary_probability"] if event else 0.,
                  "known": attended["known"].tolist() if attended else [False] * 4,
                  "encoded": frame["encoded_packets"] if attended else 0,
                  "attended_region": focus, "attention_source": "explicit_region"}
        cue = attended["cue"] if attended is not None else None
        self.mind.after_perception(result, elapsed, attended_cue=cue)
        result = self.agent.agent.after_perception(result, elapsed)
        self.context = None
        if attended is not None and sum(result["known"]) == 1:
            self.context = {"latent": base.joint[0].clone(), "acquired_at": attended["acquired_at"],
                            "step": base.steps, "consumed": False}
        closed = [previous_episodes[item["track"]] for item in frame["events"]
                  if item["new_episode"] and item["track"] < len(previous_episodes)]
        return {**result, "consolidation": self._consolidate(closed)}

    def _consolidate(self, episodes):
        episodes = sorted(set(episodes))
        if not episodes:
            return {"learned": False, "sources": []}
        if self.semantic.bank.writes.item() + self.semantic.max_writes_per_source * len(episodes) > self.semantic.update_budget:
            return {"learned": False, "deferred": True, "reason": "semantic_update_budget", "sources": episodes}
        state = self.semantic.transaction_state()
        try:
            results = [self.semantic.consolidate(self.scene.memory, episode, self.clock) for episode in episodes]
        except BaseException as error:
            self.semantic.rollback(state)
            if isinstance(error, (OSError, sqlite3.Error)):
                return {"learned": False, "deferred": True, "reason": "source_storage_unavailable", "sources": episodes}
            raise
        return {"learned": any(item["learned"] for item in results), "sources": episodes, "results": results}

    def consolidate_current(self):
        return self._consolidate(track["episode"] for track in self.scene.tracks)

    def snapshot(self):
        return {"format": 35, "agent": base_checkpoint_payload(self),
                "scene": self.scene.binding_snapshot(), "focus_region": self.focus_region,
                "torch_rng": torch.get_rng_state()}


def restore(payload):
    fields = {"format", "agent", "scene", "focus_region", "torch_rng"}
    if not isinstance(payload, dict) or set(payload) != fields or type(payload["format"]) is not int or payload["format"] != 35:
        raise ValueError("Invalid scene mind checkpoint.")
    region_valid(payload["focus_region"])
    rng = payload["torch_rng"]
    if not isinstance(rng, torch.Tensor) or rng.dtype != torch.uint8 or rng.shape != torch.get_rng_state().shape:
        raise ValueError("Invalid scene mind RNG.")
    if not isinstance(payload["agent"], dict) or payload["agent"].get("format") != 29:
        raise ValueError("Invalid shared grounded checkpoint.")
    base_rng = payload["agent"].get("torch_rng")
    if not isinstance(base_rng, torch.Tensor) or not torch.equal(rng, base_rng):
        raise ValueError("Scene and grounded checkpoint RNGs differ.")
    with torch.random.fork_rng(devices=[]), ExitStack() as cleanup:
        grounded = restore_grounded(copy.deepcopy(payload["agent"]))
        memory = grounded.mind.actor.session.memory
        if isinstance(memory, PagedMemory):
            cleanup.callback(memory.close)
        scene = restore_binding(grounded.mind.actor.session, payload["scene"])
        if type(scene) is not ConcurrentEventSession:
            raise ValueError("Scene mind requires event correspondence.")
        result = SceneGroundedMind(grounded, scene.binding, scene.binding_source, payload["focus_region"])
        result.scene = scene
        result.context = grounded.context
        cleanup.pop_all()
    torch.set_rng_state(rng)
    return result
