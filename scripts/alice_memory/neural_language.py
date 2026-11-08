"""Neural working questions control retrieval and context-dependent scheduling."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import torch

from .episodic_language import evidence_from_recall
from .contracts import interval
from .language_coordinator import LanguageCoordinator, restore as restore_base
from .language_input import FIELDS, references
from .loop_checkpoint import atomic_write
from .neural_tasks import TaskSlots, restore as restore_tasks, source


class NeuralLanguageCoordinator(LanguageCoordinator):
    def __init__(self, agent, model, endpoint, model_name, folder, worker_factory=None,
                 worker_seconds=120, retry_seconds=5, attention_mode="learned"):
        super().__init__(agent, endpoint, model_name, folder, worker_factory, worker_seconds, retry_seconds)
        if attention_mode not in ("learned", "fifo"):
            raise ValueError("Unknown neural language attention control.")
        if agent.temporal.hidden.shape != (1, 64):
            raise ValueError("Neural language attention requires the paired 64-dimensional temporal state.")
        self.tasks = TaskSlots(model, source(agent))
        self.attention_mode = attention_mode
        self.last_attention = []

    def activate(self, job):
        grounding = self.agent.words.cue(references(job["question"]))
        cue = grounding["cue"] if grounding["supported"] else torch.zeros(16, dtype=torch.float64)
        plan = job["plan"]
        field = FIELDS.index(plan["field"]) if plan is not None and plan["field"] in FIELDS else 4
        enabled = grounding["supported"] and (plan is None or not plan["uncertain"])
        self.tasks.store(job["id"], cue, field, enabled)

    def submit(self, *args, **kwargs):
        identifier = super().submit(*args, **kwargs)
        try:
            self.activate(self.jobs[identifier])
        except (RuntimeError, ValueError):
            self.jobs.pop(identifier)
            raise
        return identifier

    def finish(self, job, result):
        event = super().finish(job, result)
        if event == "parsed":
            self.activate(job)
        return event

    def capture(self, job):
        plan = job["plan"]
        if plan is None or plan["uncertain"] or plan["field"] not in FIELDS:
            return []
        decoded = self.tasks.decode(job["id"])
        if not decoded["supported"] or decoded["field"] != FIELDS.index(plan["field"]):
            return []
        if job["mode"] == "expectation":
            if decoded["field"] != self.semantic.target:
                return []
            return self.capture_expectation(self.semantic.predict(decoded["cue"]))
        # No cue/names/text/expected fact from job metadata reaches factual lookup.
        recalled = self.mind.actor.session.memory.read(decoded["cue"], self.clock, job["view"],
                                                       None if job["window"] is None else tuple(job["window"]))
        return [asdict(item) for item in evidence_from_recall(recalled, self.source)]

    def choose_waiting(self, waiting):
        self.last_attention = [{"job": job["id"], "score": self.tasks.score(job["id"], self.temporal.hidden)} for job in waiting]
        if self.attention_mode == "fifo":
            return super().choose_waiting(waiting)
        scores = {item["job"]: item["score"] for item in self.last_attention}
        return max(waiting, key=lambda job: (scores[job["id"]], -job["id"]))

    def poll(self):
        events = super().poll()
        for job in self.jobs.values():
            if job["status"] in ("failed", "cancelled"):
                self.tasks.release(job["id"])
        return events

    def tick(self, elapsed: float, mode: str = "learned"):
        interval(elapsed)
        if mode not in ("learned", "fixed", "surprise"):
            raise ValueError("Invalid internal salience control.")
        pending = [job for job in self.jobs.values() if job["status"] not in ("completed", "failed", "cancelled") and self.clock <= job["expires"]]
        supported = [job for job in pending if self.tasks.decode(job["id"])["supported"]]
        attention = None
        if supported:
            job = self.choose_waiting(supported)
            decoded = self.tasks.decode(job["id"])
            if self.mind.task is None:
                self.mind.last_cue = decoded["cue"].clone()
            attention = {"job": job["id"], "origin": "query_hypothesis", "autobiographical_write": False}
        elif not pending and self.mind.task is None:
            cue = self.mind.actor.session.previous[0].double().clone()
            cue.reshape(4, 4)[(1, 2), :] = 0
            self.mind.last_cue = cue
        result = self.agent.tick(elapsed, mode, pending_intent=bool(pending))
        result["cognitive_attention"] = attention
        result["language_events"] = self.poll()
        return result

    def cancel(self, identifier):
        super().cancel(identifier)
        if self.jobs[identifier]["status"] == "cancelled":
            self.tasks.release(identifier)

    def take(self, identifier):
        result = super().take(identifier)
        if result is not None:
            self.tasks.release(identifier)
        return result


def save(path: Path, coordinator):
    atomic_write(path, checkpoint_payload(coordinator))


def checkpoint_payload(coordinator):
    from .language_coordinator import checkpoint_payload as base_payload
    return {"format": 31, "agent": base_payload(coordinator), "tasks": coordinator.tasks.snapshot(),
            "attention_mode": coordinator.attention_mode, "torch_rng": torch.get_rng_state()}


def load(path: Path, folder: Path, worker_factory=None):
    from .checkpoint_io import read_checkpoint
    return restore(read_checkpoint(path, 12_000_000), folder, worker_factory)


def restore(payload, folder, worker_factory=None):
    if not isinstance(payload, dict) or set(payload) != {"format", "agent", "tasks", "attention_mode", "torch_rng"} or payload["format"] != 31:
        raise ValueError("Invalid neural language checkpoint fields.")
    rng = payload["torch_rng"]
    if not isinstance(rng, torch.Tensor) or rng.dtype != torch.uint8 or rng.shape != torch.get_rng_state().shape:
        raise ValueError("Invalid neural language RNG.")
    nested_rng = payload["agent"].get("torch_rng") if isinstance(payload["agent"], dict) else None
    if not isinstance(nested_rng, torch.Tensor) or not torch.equal(rng, nested_rng):
        raise ValueError("Neural/base language RNG checkpoints differ.")
    with torch.random.fork_rng(devices=[]):
        torch.set_rng_state(rng)
        base = restore_base(payload["agent"], folder, worker_factory)
        try:
            tasks = restore_tasks(payload["tasks"], base.agent)
            result = NeuralLanguageCoordinator(base.agent, tasks.model, base.endpoint, base.model, folder,
                                               worker_factory, base.worker_seconds, base.retry_seconds, payload["attention_mode"])
            result.jobs, result.next_id, result.source = base.jobs, base.next_id, base.source
            result.tasks = tasks
            owners = set(tasks.identifiers[tasks.identifiers != -1].tolist())
            required = {job["id"] for job in result.jobs.values() if job["status"] not in ("failed", "cancelled")}
            if owners != required:
                raise ValueError("Neural task ownership and language queue differ.")
        except (RuntimeError, ValueError, TypeError):
            base.close()
            memory = base.mind.actor.session.memory
            if hasattr(memory, "close"):
                memory.close()
            raise
    torch.set_rng_state(rng)
    return result
