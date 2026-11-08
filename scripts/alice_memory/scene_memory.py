"""Simultaneous event tracks sharing one clock, encoders and neural episode store.

Region localization is supplied by the sensory contract; correspondence is
learned. Missing/ambiguous participant evidence never creates an attribution.
This is an episodic subsystem, not yet the full temporal/language coordinator.
"""
from __future__ import annotations

import math
from contextlib import ExitStack
from pathlib import Path

import torch

from .contracts import interval
from .episodic_memory import EpisodicMemory, cue_valid
from .episodic_session import checkpoint_payload as base_payload, restore as restore_base
from .experience_perception import semantic
from .loop_checkpoint import atomic_write
from .paged_memory import PagedMemory
from .scene_binding import EventBinding, ParticipantBinding, event_source, source
from .scene_signals import SceneObservation


class ConcurrentSession:
    binding_class = ParticipantBinding
    binding_source_for = staticmethod(source)
    checkpoint_format = 33
    representation = "simultaneous-localized-events-v1"
    track_limit = 4

    def __init__(self, base, binding: ParticipantBinding, binding_source: dict):
        if type(base.memory) not in (EpisodicMemory, PagedMemory) or not base.boundary.mask_unobserved:
            raise ValueError("Concurrent curriculum requires a masked episodic subsystem.")
        if binding_source != self.binding_source_for(base.perception):
            raise ValueError("Participant binding belongs to another sensory representation.")
        if type(binding) is not self.binding_class or any(value.device.type != "cpu" or value.dtype != torch.float32 or not torch.isfinite(value).all() for value in binding.state_dict().values()):
            raise ValueError("Invalid participant-binding weights.")
        self.base, self.binding = base, binding.eval().requires_grad_(False)
        self.binding_source = dict(binding_source)
        self.tracks: list[dict] = []
        self.current_regions: list[dict] = []

    @property
    def clock(self):
        return self.base.clock

    @property
    def memory(self):
        return self.base.memory

    def eligible(self, cues):
        return cues

    def duplicate_regions(self, cues):
        if len(cues) == 2 and self.binding(cues[0]["cue"].float().unsqueeze(0), cues[1]["cue"].float().unsqueeze(0)).sigmoid().item() >= .8:
            return [item["region"] for item in cues]
        return []

    def candidates(self, item):
        candidates = []
        for identifier, track in enumerate(self.tracks):
            probability = self.binding(track["previous"].unsqueeze(0), item["cue"].float().unsqueeze(0)).sigmoid().item()
            if probability >= .8:
                candidates.append(identifier)
        return candidates

    def order_key(self, item):
        return int(item["cue"].reshape(4, 4)[2].argmax())

    @torch.no_grad()
    def step(self, observations: list[SceneObservation], elapsed: float) -> dict:
        interval(elapsed)
        if not isinstance(observations, list) or len(observations) > 8:
            raise ValueError("Expected at most eight scene observations.")
        now = self.clock + elapsed
        prepared = []
        for packet in observations:
            if not isinstance(packet, SceneObservation):
                raise ValueError("Expected a scene observation contract.")
            regions = packet.regions()
            if packet.acquired_at > now + 1e-8:
                raise ValueError("Scene comes from the future.")
            prepared.append((packet, regions))
        sequences, times = dict(self.base.last_sequence), dict(self.base.last_acquisition)
        accepted, stale = [], 0
        for packet, regions in sorted(prepared, key=lambda item: (item[0].acquired_at, item[0].sequence)):
            stream = packet.modality + ":" + packet.origin
            if packet.sequence <= sequences.get(stream, -1) or packet.acquired_at < times.get(stream, -1):
                stale += 1
                continue
            sequences[stream], times[stream] = packet.sequence, packet.acquired_at
            if packet.present and packet.quality > 0 and packet.origin != "self":
                accepted.append((packet, regions))
        if accepted:
            newest = max(item[0].acquired_at for item in accepted)
            synchronized = [item for item in accepted if newest - item[0].acquired_at <= .025]
            stale += len(accepted) - len(synchronized)
            accepted = synchronized
        cues, current_regions = [], []
        for region in range(2):
            parts = [item[1][region] for item in accepted]
            if not parts:
                continue
            probabilities, joint = self.base.interpret(parts)
            cue, known = semantic(probabilities)
            current_regions.append({"region": region, "cue": cue, "known": known,
                                    "joint": joint, "acquired_at": newest})
            if known[2]:
                cues.append({"region": region, "cue": cue, "known": known, "joint": joint})
        cues = self.eligible(cues)
        ambiguous = self.duplicate_regions(cues)
        cues = [item for item in cues if item["region"] not in ambiguous]
        plans = []
        for item in cues:
            candidates = self.candidates(item)
            if len(candidates) > 1:
                ambiguous.append(item["region"])
                continue
            identifier = candidates[0] if candidates else None
            track = self.tracks[identifier] if identifier is not None else None
            gap = now - track["last_seen"] if track else 0.
            probability = (self.base.boundary(item["cue"].float().unsqueeze(0), track["previous"].unsqueeze(0),
                           torch.tensor([[gap]]), torch.ones(1, 1)).sigmoid().item() if track else 1.)
            plans.append({**item, "track": identifier, "boundary": probability,
                          "episode": None if track is None or probability >= .5 else track["episode"]})
        reused = [item["track"] for item in plans if item["track"] is not None]
        duplicate = {identifier for identifier in reused if reused.count(identifier) > 1}
        ambiguous.extend(item["region"] for item in plans if item["track"] in duplicate)
        plans = [item for item in plans if item["track"] not in duplicate]
        new_tracks = sum(item["track"] is None for item in plans)
        new_episodes = sum(item["episode"] is None for item in plans)
        if len(self.tracks) + new_tracks > self.track_limit or len(self.memory.blocks) + new_episodes > self.memory.capacity:
            raise ValueError("Concurrent capacity reached; all existing experiences preserved.")
        # Canonical learned-category order makes bookkeeping independent of which
        # visual half/stereo channel contains a participant. No simulator ID here.
        plans.sort(key=self.order_key)
        events = []
        with self.memory.atomic_observations([item["episode"] for item in plans if item["episode"] is not None]):
            for item in plans:
                item["written_episode"] = self.memory.observe_at(item["cue"], now, item["episode"])
        for item in plans:
            episode = item["written_episode"]
            identifier = item["track"]
            if identifier is None:
                identifier = len(self.tracks)
                self.tracks.append({"previous": torch.zeros(16), "last_seen": now, "episode": episode})
            track = self.tracks[identifier]
            previous = track["previous"].reshape(4, 4).clone()
            previous[item["known"]] = item["cue"].float().reshape(4, 4)[item["known"]]
            track.update(previous=previous.flatten(), last_seen=now, episode=episode)
            events.append({"region": item["region"], "track": identifier, "episode": episode,
                           "new_episode": item["episode"] is None, "boundary_probability": item["boundary"]})
        self.memory.clock = self.base.clock = now
        self.base.steps += 1
        self.base.stale += stale
        self.base.last_sequence, self.base.last_acquisition = sequences, times
        self.current_regions = current_regions
        self.base.since_observation = 0. if plans else self.base.since_observation + elapsed
        if plans:
            self.base.previous = self.tracks[events[0]["track"]]["previous"].clone().unsqueeze(0)
            self.base.joint = plans[0]["joint"].clone()
            self.base.seen, self.base.last_boundary = True, plans[0]["boundary"]
        return {"clock": now, "events": events, "ambiguous_regions": sorted(ambiguous),
                "unassigned_regions": sorted(set(range(2)) - {item["region"] for item in plans}),
                "encoded_packets": len(accepted), "stale": stale}

    def tick(self, elapsed):
        return self.step([], elapsed)

    def snapshot(self):
        return {**self.binding_snapshot(), "base": base_payload(self.base)}

    def binding_snapshot(self):
        """Track state without another copy of the shared episodic archive."""
        return {"format": self.checkpoint_format, "representation": self.representation,
                "binding": {name: value.clone() for name, value in self.binding.state_dict().items()},
                "binding_source": dict(self.binding_source),
                "tracks": [{**track, "previous": track["previous"].clone()} for track in self.tracks]}


class ConcurrentEventSession(ConcurrentSession):
    """A participant can own several identifiable simultaneous event tracks."""
    binding_class = EventBinding
    binding_source_for = staticmethod(event_source)
    checkpoint_format = 34
    representation = "simultaneous-localized-events-v2"
    track_limit = 64

    def eligible(self, cues):
        # Unknown activity/participant/context cannot uniquely identify this event.
        return [item for item in cues if bool(item["known"][[0, 2, 3]].all())]

    def order_key(self, item):
        return tuple(int(item["cue"].reshape(4, 4)[field].argmax()) for field in (2, 0, 3))


def save(path: Path, session):
    atomic_write(path, session.snapshot())


def restore(payload: dict):
    if not isinstance(payload, dict) or set(payload) != {"format", "representation", "base", "binding", "binding_source", "tracks"} or type(payload["format"]) is not int or payload["format"] not in (33, 34):
        raise ValueError("Invalid concurrent checkpoint.")
    with torch.random.fork_rng(devices=[]), ExitStack() as cleanup:
        base = restore_base(payload["base"])
        if isinstance(base.memory, PagedMemory):
            cleanup.callback(base.memory.close)
        for name, value in base.snapshot().items():
            setattr(base, name, value)  # Own tensors/watermarks instead of aliasing the caller's payload.
        result = restore_binding(base, {name: value for name, value in payload.items() if name != "base"})
        cleanup.pop_all()
    torch.set_rng_state(payload["base"]["torch_rng"])
    return result


def restore_binding(base, payload: dict):
    """Restore tracks against an already restored, shared sensory subsystem."""
    fields = {"format", "representation", "binding", "binding_source", "tracks"}
    if not isinstance(payload, dict) or set(payload) != fields or type(payload["format"]) is not int or payload["format"] not in (33, 34):
        raise ValueError("Invalid concurrent binding checkpoint.")
    session_type = ConcurrentEventSession if payload["format"] == 34 else ConcurrentSession
    if payload["representation"] != session_type.representation:
        raise ValueError("Invalid concurrent checkpoint representation.")
    with torch.random.fork_rng(devices=[]):
        binding = session_type.binding_class()
        expected = binding.state_dict()
        state = payload["binding"]
        if not isinstance(state, dict) or set(state) != set(expected) or any(not isinstance(state[name], torch.Tensor) or state[name].device.type != "cpu" or state[name].dtype != value.dtype or state[name].shape != value.shape for name, value in expected.items()):
            raise ValueError("Invalid participant-binding tensor layout.")
        binding.load_state_dict(payload["binding"], strict=True)
        result = session_type(base, binding, payload["binding_source"])
        tracks = payload["tracks"]
        if not isinstance(tracks, list) or len(tracks) > result.track_limit:
            raise ValueError("Invalid concurrent track count.")
        episodes = set()
        for track in tracks:
            if not isinstance(track, dict) or set(track) != {"previous", "last_seen", "episode"}:
                raise ValueError("Invalid concurrent track fields.")
            previous, now, episode = track["previous"], track["last_seen"], track["episode"]
            if not isinstance(previous, torch.Tensor) or previous.device.type != "cpu" or previous.dtype != torch.float32 or previous.shape != (16,):
                raise ValueError("Invalid concurrent perceptual state.")
            known = cue_valid(previous.double())
            if not known[2] or isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now) or not 0 <= now <= base.clock:
                raise ValueError("Invalid concurrent track time/participant.")
            if payload["format"] == 34 and not known[[0, 2, 3]].all():
                raise ValueError("Invalid concurrent event anchors.")
            if type(episode) is not int or not 0 <= episode < len(base.memory.blocks) or episode in episodes or base.memory.traces[episode].ended != now:
                raise ValueError("Invalid concurrent episode ownership.")
            episodes.add(episode)
            result.tracks.append({"previous": previous.clone(), "last_seen": now, "episode": episode})
    return result


def load(path):
    from .checkpoint_io import read_checkpoint
    return restore(read_checkpoint(path))
