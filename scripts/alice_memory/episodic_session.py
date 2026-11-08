"""Causal perception, learned event boundaries and persistent episodic memory."""
from __future__ import annotations

import math
from dataclasses import asdict
from pathlib import Path

import torch
from torch.nn import functional as F

from .contracts import Observation, interval
from .episodic_memory import BeliefRevision, EpisodeBlock, EpisodeTrace, EpisodicMemory
from .event_boundary import EventBoundary
from .experience_perception import ExperiencePerception, semantic
from .loop_checkpoint import atomic_write
from .signals import audio_features


class EpisodicSession:
    def __init__(self, perception: ExperiencePerception, boundary: EventBoundary,
                 memory: EpisodicMemory | None = None) -> None:
        self.perception, self.boundary = perception, boundary
        self.memory = memory if memory is not None else EpisodicMemory()
        self.clock = 0.
        self.steps = 0
        self.previous = torch.zeros(1, 16)
        self.joint = torch.zeros(1, 32)
        self.seen = False
        self.since_observation = 0.
        self.last_sequence: dict[str, int] = {}
        self.last_acquisition: dict[str, float] = {}
        self.stale = 0
        self.last_boundary = 0.

    @torch.no_grad()
    def interpret(self, packets: list[Observation]) -> tuple[torch.Tensor, torch.Tensor]:
        """Only synchronized, already validated and accepted external packets."""
        encoded, distributions, qualities = [], [], []
        for packet in packets:
            values = packet.payload.unsqueeze(0)
            if packet.modality == "audio":
                values = audio_features(values)
            latent = self.perception.encode(values, packet.modality)
            encoded.append(latent[0])
            distributions.append(self.perception.probabilities(latent)[0])
            qualities.append(packet.quality)
        joint = F.normalize((torch.stack(encoded) * torch.tensor(qualities).unsqueeze(-1)).sum(0), dim=0).unsqueeze(0)
        probabilities = torch.stack(distributions)
        confidences, categories = probabilities.max(-1)
        known = (confidences >= .8) & (categories < 4)
        output = torch.zeros(4, 5)
        for field in range(4):
            supported = known[:, field]
            if not supported.any() or categories[supported, field].unique().numel() != 1:
                output[field, 4] = 1
                continue
            weights = torch.tensor(qualities)[supported]
            output[field] = (probabilities[supported, field] * weights.unsqueeze(-1)).sum(0) / weights.sum()
        return output, joint

    @torch.no_grad()
    def step(self, observations: list[Observation], elapsed: float) -> dict:
        interval(elapsed)
        if not isinstance(observations, list) or len(observations) > 32:
            raise ValueError("Expected at most 32 sensory packets.")
        now = self.clock + elapsed
        for packet in observations:
            packet.validate()
            if packet.acquired_at > now + 1e-8:
                raise ValueError("Experience packet comes from the future.")
        sequences, times = dict(self.last_sequence), dict(self.last_acquisition)
        packets = []
        stale = 0
        for packet in sorted(observations, key=lambda item: (item.acquired_at, item.sequence)):
            stream = packet.modality + ":" + packet.origin
            if packet.sequence <= sequences.get(stream, -1) or packet.acquired_at < times.get(stream, -1):
                stale += 1
                continue
            sequences[stream], times[stream] = packet.sequence, packet.acquired_at
            if packet.present and packet.quality > 0 and packet.origin != "self":
                packets.append(packet)
        # Delayed sound from a previous scene cannot silently contaminate this one.
        if packets:
            acquired = max(packet.acquired_at for packet in packets)
            synchronized = [packet for packet in packets if acquired - packet.acquired_at <= .025]
            stale += len(packets) - len(synchronized)
            packets = synchronized
        probabilities, joint = self.interpret(packets) if packets else (torch.zeros(4, 5), self.joint)
        cue, known = semantic(probabilities)
        gap = self.since_observation + elapsed
        probability = (self.boundary(cue.float().unsqueeze(0), self.previous, torch.tensor([[gap]]),
                                     torch.tensor([[float(self.seen)]]))).sigmoid().item() if known.any() else 0.
        new = not self.seen or probability >= .5
        # Overflow/validation are checked before committing session counters.
        episode = self.memory.observe(cue, now, bool(new))
        self.clock = now
        self.steps += 1
        self.last_sequence, self.last_acquisition = sequences, times
        self.stale += stale
        self.last_boundary = probability
        self.joint = joint
        self.since_observation = 0. if known.any() else gap
        if known.any():
            if self.boundary.mask_unobserved:
                previous = self.previous.reshape(4, 4).clone()
                previous[known] = cue.float().reshape(4, 4)[known]
                self.previous = previous.flatten().unsqueeze(0)
            else:
                self.previous = cue.float().unsqueeze(0)
            self.seen = True
        return {"episode": episode, "boundary_probability": probability,
                "new_episode": episode is not None and new, "known": known.tolist(),
                "encoded": len(packets), "stale": stale}

    def tick(self, elapsed: float) -> dict:
        return self.step([], elapsed)

    def validate_cues(self, packets: list[Observation], now: float) -> None:
        if not isinstance(packets, list) or not 1 <= len(packets) <= 2:
            raise ValueError("A query/evidence needs one or two sensory cues.")
        for packet in packets:
            packet.validate()
            if packet.origin == "self" or not packet.present or packet.quality == 0 or packet.acquired_at > now + 1e-8:
                raise ValueError("Invalid query/evidence origin, presence or acquisition.")
        if max(packet.acquired_at for packet in packets) - min(packet.acquired_at for packet in packets) > .025:
            raise ValueError("Query/evidence modalities are not synchronized.")

    @torch.no_grad()
    def query(self, packets: list[Observation], view: str = "current",
              window: tuple[float, float] | None = None) -> dict:
        self.validate_cues(packets, self.clock)
        probabilities, _ = self.interpret(packets)
        cue, _ = semantic(probabilities)
        return self.memory.read(cue, self.clock, view, window)

    @torch.no_grad()
    def revise(self, cues: list[Observation], evidence: list[Observation], field: int,
               elapsed: float, window: tuple[float, float] | None = None) -> dict:
        interval(elapsed)
        now = self.clock + elapsed
        self.validate_cues(cues, now)
        self.validate_cues(evidence, now)
        if type(field) is not int or not 0 <= field < 4:
            raise ValueError("Invalid revision field.")
        cue, _ = semantic(self.interpret(cues)[0])
        probabilities = self.interpret(evidence)[0][field]
        source = "person" if any(packet.origin == "person" for packet in evidence) else "environment"
        result = self.memory.revise(cue, field, probabilities, now, window, source)
        self.memory.clock = now
        self.clock = now
        self.steps += 1
        self.since_observation += elapsed
        return result

    def snapshot(self) -> dict:
        return {"clock": self.clock, "steps": self.steps, "previous": self.previous.clone(),
                "joint": self.joint.clone(), "seen": self.seen,
                "since_observation": self.since_observation,
                "last_sequence": dict(self.last_sequence), "last_acquisition": dict(self.last_acquisition),
                "stale": self.stale, "last_boundary": self.last_boundary}


def save(path: Path, session: EpisodicSession) -> None:
    atomic_write(path, checkpoint_payload(session))


def checkpoint_payload(session: EpisodicSession) -> dict:
    if abs(session.clock - session.memory.clock) > 1e-8:
        raise ValueError("Cannot checkpoint unsynchronized episodic state.")
    payload = {"format": 10, "representation": "synthetic-experience-v1",
            "perception": session.perception.state_dict(), "boundary": session.boundary.state_dict(),
            "memory": session.memory.state_dict(), "metadata": session.memory.metadata(),
            "session": session.snapshot(), "torch_rng": torch.get_rng_state()}
    if session.boundary.mask_unobserved:
        payload.update(format=13, representation="synthetic-experience-v2", boundary_masked=True)
    from .paged_memory import PagedMemory
    if isinstance(session.memory, PagedMemory):
        if not session.boundary.mask_unobserved:
            raise ValueError("Paged sessions require the masked boundary model.")
        payload.update(format=24, representation="synthetic-experience-paged-v1")
    return payload


def load(path: Path) -> EpisodicSession:
    from .checkpoint_io import read_checkpoint
    payload = read_checkpoint(path)
    return restore(payload)


def restore(payload: dict) -> EpisodicSession:
    fields = {"format", "representation", "perception", "boundary", "memory", "metadata", "session", "torch_rng"}
    if isinstance(payload, dict) and payload.get("format") in (13, 24):
        fields.add("boundary_masked")
    if not isinstance(payload, dict) or set(payload) != fields or payload["format"] not in (10, 13, 24):
        raise ValueError("Invalid episodic checkpoint format/representation.")
    representations = {10: "synthetic-experience-v1", 13: "synthetic-experience-v2", 24: "synthetic-experience-paged-v1"}
    if payload["representation"] != representations[payload["format"]] or (payload["format"] != 10 and payload["boundary_masked"] is not True):
        raise ValueError("Invalid episodic representation configuration.")
    rng = payload["torch_rng"]
    if not isinstance(rng, torch.Tensor) or rng.dtype != torch.uint8 or rng.shape != torch.get_rng_state().shape:
        raise ValueError("Invalid episodic RNG snapshot.")
    with torch.random.fork_rng(devices=[]):
        metadata = payload["metadata"]
        metadata_fields = {"capacity", "clock", "traces", "revisions"}
        if payload["format"] == 24:
            metadata_fields.add("hot_limit")
        if not isinstance(metadata, dict) or set(metadata) != metadata_fields:
            raise ValueError("Invalid episodic metadata.")
        paged = payload["format"] == 24
        if not isinstance(metadata["traces"], list) or not isinstance(metadata["revisions"], list):
            raise ValueError("Invalid episode/revision lists.")
        if paged:
            from .paged_memory import restore_archive
            memory = restore_archive(payload["memory"], metadata)
        else:
            memory = EpisodicMemory(metadata["capacity"])
        if len(metadata["traces"]) > memory.capacity or len(metadata["revisions"]) > memory.revision_capacity:
            raise ValueError("Invalid episode/revision count.")
        clock = metadata["clock"]
        if isinstance(clock, bool) or not isinstance(clock, (int, float)) or not math.isfinite(clock) or clock < 0:
            raise ValueError("Invalid episodic memory clock.")
        if not paged:
            memory.blocks.extend(EpisodeBlock() for _ in metadata["traces"])
            memory.load_state_dict(payload["memory"], strict=True)
        memory.clock = clock
        for index, value in enumerate(metadata["traces"]):
            trace = EpisodeTrace(**value)
            if any(isinstance(time, bool) or not isinstance(time, (int, float)) or not math.isfinite(time) for time in (trace.started, trace.ended)):
                raise ValueError("Invalid episode timestamps.")
            if type(trace.identifier) is not int or trace.identifier != index or type(trace.observations) is not int or trace.observations < 1 or not 0 <= trace.started <= trace.ended <= clock:
                raise ValueError("Invalid episode trace.")
            memory.traces.append(trace)
        for value in metadata["revisions"]:
            record = BeliefRevision(**value)
            if type(record.episode) is not int or not 0 <= record.episode < len(memory.blocks) or type(record.field) is not int or not 0 <= record.field < 4 or not memory.traces[record.episode].started <= record.learned_at <= clock or record.source not in ("person", "environment") or not .8 <= record.confidence <= 1:
                raise ValueError("Invalid belief revision.")
            for digest in (record.evidence_sha256, record.previous_weights_sha256, record.new_weights_sha256):
                if not isinstance(digest, str) or len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
                    raise ValueError("Invalid revision digest.")
            memory.revision_log.append(record)
        for index, block in enumerate(memory.blocks):
            if not torch.isfinite(block.addresses).all() or (block.addresses < 0).any() or (block.addresses.sum(-1) > 1.00001).any() or (block.learned_at < 0).any() or (block.learned_at > clock).any() or (block.revisions < 0).any():
                raise ValueError("Invalid episodic index.")
            if not torch.allclose(block.addresses.sum(-1)[block.known], torch.ones_like(block.addresses.sum(-1)[block.known]), atol=1e-5):
                raise ValueError("Invalid known episode address normalization.")
            for field in range(4):
                records = [record for record in memory.revision_log if record.episode == index and record.field == field]
                if block.revisions[field].item() != len(records) or (records and block.learned_at[1, field].item() != records[-1].learned_at):
                    raise ValueError("Revision record and fast-weight index disagree.")
            for bank_index, bank in enumerate(block.banks):
                if not torch.isfinite(bank.weights).all() or not torch.isfinite(bank.precision).all() or not torch.allclose(bank.precision, bank.precision.T, atol=1e-8) or torch.linalg.cholesky_ex(bank.precision).info.item() != 0 or bank.writes.item() < 0:
                    raise ValueError("Invalid episodic fast weights.")
                if bool(block.known.flatten()[bank_index]) != (bank.writes.item() > 0):
                    raise ValueError("Known field mask and fast weights disagree.")
        perception, boundary = ExperiencePerception(), EventBoundary(mask_unobserved=payload["format"] != 10)
        perception.load_state_dict(payload["perception"], strict=True)
        boundary.load_state_dict(payload["boundary"], strict=True)
        if any(not torch.isfinite(value).all() for model in (perception, boundary) for value in model.state_dict().values()):
            raise ValueError("Nonfinite episodic model weights.")
        perception.eval().requires_grad_(False)
        boundary.eval().requires_grad_(False)
        session = EpisodicSession(perception, boundary, memory)
        state = payload["session"]
        if not isinstance(state, dict) or set(state) != set(session.snapshot()):
            raise ValueError("Invalid episodic session fields.")
        for key in ("clock", "since_observation", "last_boundary"):
            if isinstance(state[key], bool) or not isinstance(state[key], (int, float)) or not math.isfinite(state[key]) or state[key] < 0:
                raise ValueError("Invalid episodic session scalar.")
        for key in ("steps", "stale"):
            if type(state[key]) is not int or state[key] < 0:
                raise ValueError("Invalid episodic session counter.")
        for key, shape in (("previous", (1, 16)), ("joint", (1, 32))):
            if not isinstance(state[key], torch.Tensor) or state[key].shape != shape or state[key].dtype != torch.float32 or not torch.isfinite(state[key]).all():
                raise ValueError("Invalid episodic session tensor.")
        if type(state["seen"]) is not bool or state["last_boundary"] > 1 or abs(state["clock"] - clock) > 1e-8:
            raise ValueError("Inconsistent episodic session state.")
        sequences, times = state["last_sequence"], state["last_acquisition"]
        streams = {modality + ":" + origin for modality in ("image", "audio") for origin in ("environment", "person", "self")}
        if not isinstance(sequences, dict) or not isinstance(times, dict) or set(sequences) != set(times) or not set(sequences) <= streams or any(type(value) is not int or value < 0 for value in sequences.values()) or any(not math.isfinite(value) or not 0 <= value <= clock for value in times.values()):
            raise ValueError("Invalid episodic watermarks.")
        for key, value in state.items():
            setattr(session, key, value)
    torch.set_rng_state(rng)
    return session
