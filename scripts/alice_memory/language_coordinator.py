"""Bounded language work beside a single-owner, continuously advancing neural mind."""
from __future__ import annotations

import hashlib
import copy
import json
import math
from contextlib import ExitStack
from dataclasses import asdict, fields
from pathlib import Path
from uuid import uuid4

import torch

from .continuous_mind import validate_window
from .episodic_language import evidence_from_recall
from .grounded_mind import GroundedMind, checkpoint_payload as mind_payload, restore as restore_mind
from .expectation_protocol import ExpectationEvidence, validate_expectation_proposal
from .language import LanguageProposal, LocalLanguage, MemoryEvidence
from .language_input import FIELDS, QuestionPlan, references
from .language_process import LanguageProcess
from .loop_checkpoint import atomic_write
from .written_symbols import symbol

TERMINAL = ("completed", "failed", "cancelled")
LEGACY_JOB_FIELDS = {"id", "question", "view", "window", "status", "issued", "expires", "retry_at",
              "plan", "evidence", "fingerprint", "refreshes", "deferrals", "proposal", "error"}
JOB_FIELDS = LEGACY_JOB_FIELDS | {"mode", "validation"}


def fingerprint(evidence: list[dict], mode="recall") -> str:
    # Confidence jitter and extra observations do not change a supported fact.
    names = ("kind", "target", "value") if mode == "expectation" else ("source", "interpretation", "attributes")
    factual = [{key: item[key] for key in names} for item in evidence]
    return hashlib.sha256(json.dumps(factual, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def validate_plan(value: dict, question: str, model: str) -> dict:
    if not isinstance(value, dict) or set(value) != {item.name for item in fields(QuestionPlan)}:
        raise ValueError("Invalid worker question plan fields.")
    names = value["names"]
    if not isinstance(names, list) or len(names) > 8 or any(symbol(name) != name for name in names) or len(set(names)) != len(names) or set(names) != set(references(question)):
        raise ValueError("Worker changed the question references.")
    if value["field"] not in (*FIELDS, "unknown") or type(value["uncertain"]) is not bool or value["meanings_supplied_to_parser"] is not False:
        raise ValueError("Invalid worker question semantics.")
    if (not names or value["field"] == "unknown") and not value["uncertain"]:
        raise ValueError("Unsupported worker plan asserted certainty.")
    if value["model"] != model or value["question_sha256"] != hashlib.sha256(question.encode()).hexdigest():
        raise ValueError("Worker question/model provenance changed.")
    validate_provenance(value)
    return value


def validate_provenance(value):
    if not isinstance(value["model_digest"], str) or not 1 <= len(value["model_digest"]) <= 128:
        raise ValueError("Invalid worker model digest.")
    for name in ("prompt_sha256",):
        digest = value[name]
        if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("Invalid worker prompt provenance.")
    seconds = value["wall_seconds"]
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not 0 <= seconds <= 300:
        raise ValueError("Invalid worker duration.")


def validate_proposal(value: dict, job: dict, model: str) -> dict:
    if job.get("mode", "recall") == "expectation":
        evidence = ExpectationEvidence(**job["evidence"][0]) if job["evidence"] else None
        if evidence is not None and evidence.target != job["plan"]["field"]:
            raise ValueError("Expectation changed the requested field.")
        return validate_expectation_proposal(value, evidence, model)
    if not isinstance(value, dict) or set(value) != {item.name for item in fields(LanguageProposal)}:
        raise ValueError("Invalid worker proposal fields.")
    validate_provenance(value)
    if value["model"] != model or value["free_text_verified"] is not False or type(value["uncertain"]) is not bool or type(value["structured_claims_supported"]) is not bool:
        raise ValueError("Invalid worker proposal flags/model.")
    if not isinstance(value["text"], str) or len(value["text"]) > 4096 or not isinstance(value["claims"], dict) or len(value["claims"]) > 12 or not isinstance(value["violations"], list) or len(value["violations"]) > 24 or any(not isinstance(item, str) or len(item) > 320 for item in value["violations"]):
        raise ValueError("Invalid worker proposal payload.")
    allowed = {(key, content) for item in job["evidence"] for key, content in item["attributes"]}
    if any(not isinstance(key, str) or not isinstance(content, str) or (key, content) not in allowed for key, content in value["claims"].items()):
        raise ValueError("Worker proposal made an unsupported factual claim.")
    target = job["plan"]["field"]
    if target in dict(allowed) and target not in value["claims"]:
        raise ValueError("Worker proposal omitted a requested known attribute.")
    if not allowed and not value["uncertain"]:
        raise ValueError("Worker proposal asserted certainty without evidence.")
    if not value["structured_claims_supported"] or value["violations"]:
        raise ValueError("Worker rejected its own structured claims.")
    document = json.dumps(job["evidence"], ensure_ascii=False, sort_keys=True)
    if value["evidence_sha256"] != hashlib.sha256(document.encode()).hexdigest():
        raise ValueError("Worker proposal used a different evidence bundle.")
    return value


class LanguageCoordinator:
    def __init__(self, agent: GroundedMind, endpoint: str, model: str, folder: Path,
                 worker_factory=None, worker_seconds: float = 120, retry_seconds: float = 5):
        LocalLanguage(endpoint, model)
        if isinstance(worker_seconds, bool) or not isinstance(worker_seconds, (int, float)) or not 0 < worker_seconds <= 120 or isinstance(retry_seconds, bool) or not isinstance(retry_seconds, (int, float)) or not .1 <= retry_seconds <= 60:
            raise ValueError("Invalid language worker/retry budget.")
        self.agent, self.endpoint, self.model = agent, endpoint, model
        self.folder = folder
        self.worker_seconds, self.retry_seconds = worker_seconds, retry_seconds
        self.worker_factory = worker_factory or (lambda operation: LanguageProcess(operation, folder, worker_seconds))
        self.jobs: dict[int, dict] = {}
        self.next_id = 1
        self.source = "alice-" + uuid4().hex
        self.worker, self.active_id = None, None
        self.external_worker_owner = None
        self.closed = False

    @property
    def clock(self):
        return self.agent.clock

    @property
    def mind(self):
        return self.agent.mind

    @property
    def temporal(self):
        return self.agent.temporal

    @property
    def semantic(self):
        return self.agent.semantic

    def submit(self, question: str, view="current", window=None, ttl: float = 300, *, mode="recall") -> int:
        references(question)
        validate_window(window, self.clock)
        if mode not in ("recall", "expectation") or (mode == "expectation" and (view != "current" or window is not None)):
            raise ValueError("Expectations describe learned regularities, not dated episodes.")
        if self.closed or view not in ("initial", "current") or isinstance(ttl, bool) or not isinstance(ttl, (int, float)) or not 5 <= ttl <= 3600:
            raise ValueError("Invalid language request view/lifetime or closed supervisor.")
        if len(self.jobs) >= 4 or self.next_id >= 1000000:
            raise ValueError("Language queue budget reached; previous requests preserved.")
        identifier = self.next_id
        self.jobs[identifier] = {"id": identifier, "question": question, "view": view,
                                 "window": None if window is None else list(window), "status": "waiting_parse",
                                 "issued": self.clock, "expires": self.clock + ttl, "retry_at": self.clock,
                                 "plan": None, "evidence": [], "fingerprint": None,
                                 "refreshes": 0, "deferrals": 0, "proposal": None, "error": None,
                                 "mode": mode, "validation": None}
        self.next_id += 1
        return identifier

    def submit_expectation(self, question: str, ttl: float = 300) -> int:
        return self.submit(question, ttl=ttl, mode="expectation")

    def reserve_worker(self, owner):
        if owner is None:
            raise ValueError("A shared worker reservation requires its owner.")
        if self.closed or self.worker is not None or self.external_worker_owner is not None:
            return False
        self.external_worker_owner = owner
        return True

    def release_worker(self, owner):
        if self.external_worker_owner is not owner:
            raise ValueError("Only the reservation owner can release the shared worker.")
        self.external_worker_owner = None

    def capture_expectation(self, prediction):
        if prediction is None or not prediction["supported"]:
            return []
        from .expectation_language import state_digest
        evidence = ExpectationEvidence(prediction["target"], prediction["value"], prediction["confidence"],
                                       prediction.get("support_policy", "conditional-v2"), state_digest(self.agent))
        evidence.validate()
        return [asdict(evidence)]

    def capture(self, job):
        plan = job["plan"]
        if job["mode"] == "expectation":
            if plan["uncertain"] or plan["field"] not in FIELDS:
                return []
            result = self.agent.expect_names(plan["names"], FIELDS.index(plan["field"]))
            return self.capture_expectation(result["prediction"])
        evidence = ()
        if not plan["uncertain"] and plan["field"] in FIELDS:
            result = self.agent.query_names(plan["names"], job["view"], None if job["window"] is None else tuple(job["window"]))
            if result["result"] is not None:
                evidence = evidence_from_recall(result["result"], self.source)
        return [asdict(item) for item in evidence]

    def cancel(self, identifier: int):
        job = self.jobs[identifier]
        if job["status"] in TERMINAL:
            return
        if self.active_id == identifier:
            self.worker.cancel()
        job.update(status="cancelled", error="cancelled", proposal=None, validation=None)

    def take(self, identifier: int) -> dict | None:
        job = self.jobs[identifier]
        if job["status"] not in TERMINAL or self.active_id == identifier:
            return None
        if job["status"] == "completed":
            current = self.capture(job)
            if fingerprint(current, job["mode"]) != job["fingerprint"]:
                job["refreshes"] += 1
                job.update(status="waiting_expression" if job["refreshes"] <= 2 else "failed",
                           retry_at=self.clock, proposal=None, validation=None, error="evidence_changed_before_delivery")
                return None
            self.record_validation(job, current)
        return self.jobs.pop(identifier)

    def record_validation(self, job, evidence):
        if job["mode"] == "expectation":
            job["validation"] = {"kind": "learned_expectation", "checked_at": self.clock,
                                 "evidence": copy.deepcopy(evidence)}

    def finish(self, job, result):
        if result["status"] == "deferred":
            job["deferrals"] += 1
            job.update(status="waiting_parse" if job["plan"] is None else "waiting_expression",
                       retry_at=self.clock + self.retry_seconds, error="resource_admission_deferred")
            return "deferred"
        if result["status"] != "ready":
            reason = result.get("value")
            job.update(status="failed", error=str(reason)[:2048], proposal=None, validation=None)
            return "failed"
        if job["status"] == "parsing":
            job["plan"] = validate_plan(result["value"], job["question"], self.model)
            job.update(status="waiting_expression", retry_at=self.clock, error=None)
            return "parsed"
        current = self.capture(job)
        if fingerprint(current, job["mode"]) != job["fingerprint"]:
            job["refreshes"] += 1
            if job["refreshes"] > 2:
                job.update(status="failed", error="evidence_kept_changing", proposal=None, validation=None)
                return "failed"
            job.update(status="waiting_expression", retry_at=self.clock, error="evidence_changed_during_generation", proposal=None, validation=None)
            return "evidence_refreshed"
        job["proposal"] = validate_proposal(result["value"], job, self.model)
        self.record_validation(job, current)
        job.update(status="completed", error=None)
        return "completed"

    def poll(self) -> list[dict]:
        if self.closed:
            raise ValueError("Language supervisor is closed.")
        events = []
        for identifier, job in self.jobs.items():
            if job["status"] not in TERMINAL and self.clock > job["expires"]:
                self.cancel(identifier)
                job.update(status="failed", error="language_request_expired")
        if self.worker is not None:
            job = self.jobs[self.active_id]
            try:
                result = self.worker.poll()
                if result is None:
                    return events
                self.worker.close()
                event = job["status"] if job["status"] in TERMINAL else self.finish(job, result)
            except (OSError, RuntimeError, ValueError) as error:
                self.worker.close()
                job.update(status="failed", error=str(error)[:2048], proposal=None, validation=None)
                event = "failed"
            events.append({"job": self.active_id, "event": event})
            self.worker, self.active_id = None, None
        if self.external_worker_owner is not None:
            return events
        waiting = []
        for job in self.jobs.values():
            if job["status"] not in ("waiting_parse", "waiting_expression") or job["retry_at"] > self.clock:
                continue
            pending = getattr(self.agent.semantic, "pending_sources", None)
            if job["mode"] == "expectation" and job["plan"] is not None and pending is not None and pending():
                job.update(retry_at=self.clock + self.retry_seconds, error="memory_learning_pending")
                events.append({"job": job["id"], "event": "waiting_for_memory_learning"})
                continue
            waiting.append(job)
        if not waiting:
            return events
        job = self.choose_waiting(waiting)
        stage = "parse" if job["plan"] is None else "expression"
        if stage == "expression":
            job["evidence"] = self.capture(job)
            job["fingerprint"] = fingerprint(job["evidence"], job["mode"])
        required = [job["plan"]["field"]] if stage == "expression" and job["plan"]["field"] in FIELDS else []
        operation = {"stage": "expectation" if stage == "expression" and job["mode"] == "expectation" else stage,
                     "endpoint": self.endpoint, "model": self.model,
                     "question": job["question"], "view": job["view"], "required": required,
                     "evidence": job["evidence"] if stage == "expression" else []}
        try:
            self.worker = self.worker_factory(operation)
        except (OSError, RuntimeError, ValueError) as error:
            job.update(status="failed", error=str(error)[:2048], proposal=None)
            events.append({"job": job["id"], "event": "failed"})
            return events
        self.active_id = job["id"]
        job["status"] = "parsing" if stage == "parse" else "expressing"
        events.append({"job": job["id"], "event": "started_" + stage})
        return events

    def choose_waiting(self, waiting):
        return min(waiting, key=lambda item: item["id"])

    def tick(self, *args, **kwargs):
        result = self.agent.tick(*args, **kwargs)
        result["language_events"] = self.poll()
        return result

    def perceive(self, *args, **kwargs):
        result = self.agent.perceive(*args, **kwargs)
        result["language_events"] = self.poll()
        return result

    def unobserved_gap(self, elapsed):
        self.agent.unobserved_gap(elapsed)
        return self.poll()

    def close(self):
        if self.worker is not None:
            self.worker.close()
            self.worker, self.active_id = None, None
        self.closed = True

    def snapshot(self):
        jobs = json.loads(json.dumps(list(self.jobs.values()), ensure_ascii=False, allow_nan=False))
        for job in jobs:
            if job["status"] == "parsing":
                job["status"] = "waiting_parse"
            elif job["status"] == "expressing":
                job["status"] = "waiting_expression"
        return {"endpoint": self.endpoint, "model": self.model, "source": self.source, "next_id": self.next_id,
                "worker_seconds": self.worker_seconds, "retry_seconds": self.retry_seconds, "jobs": jobs}


def save(path: Path, agent: LanguageCoordinator):
    atomic_write(path, checkpoint_payload(agent))


def checkpoint_payload(agent: LanguageCoordinator):
    state = agent.snapshot()
    legacy = all(job["mode"] == "recall" for job in state["jobs"])
    if legacy:
        for job in state["jobs"]:
            job.pop("mode")
            job.pop("validation")
    return {"format": 30 if legacy else 39, "agent": mind_payload(agent.agent),
            "language": state, "torch_rng": torch.get_rng_state()}


def load(path: Path, folder: Path, worker_factory=None) -> LanguageCoordinator:
    from .checkpoint_io import read_checkpoint
    return restore(read_checkpoint(path, 12_000_000), folder, worker_factory)


def restore(payload, folder: Path, worker_factory=None):
    if not isinstance(payload, dict) or set(payload) != {"format", "agent", "language", "torch_rng"} or payload["format"] not in (30, 39):
        raise ValueError("Invalid language coordinator checkpoint.")
    rng = payload["torch_rng"]
    if not isinstance(rng, torch.Tensor) or rng.dtype != torch.uint8 or rng.shape != torch.get_rng_state().shape:
        raise ValueError("Invalid language coordinator RNG.")
    state = payload["language"]
    if not isinstance(state, dict) or set(state) != {"endpoint", "model", "source", "next_id", "worker_seconds", "retry_seconds", "jobs"}:
        raise ValueError("Invalid language controller fields.")
    with torch.random.fork_rng(devices=[]), ExitStack() as cleanup:
        agent = restore_mind(payload["agent"])
        from .paged_memory import PagedMemory
        if isinstance(agent.mind.actor.session.memory, PagedMemory):
            cleanup.callback(agent.mind.actor.session.memory.close)
        result = LanguageCoordinator(agent, state["endpoint"], state["model"], folder, worker_factory,
                                     state["worker_seconds"], state["retry_seconds"])
        cleanup.callback(result.close)
        if not isinstance(state["source"], str) or len(state["source"]) != 38 or not state["source"].startswith("alice-") or any(char not in "0123456789abcdef" for char in state["source"][6:]):
            raise ValueError("Invalid persistent language source.")
        if type(state["next_id"]) is not int or not 1 <= state["next_id"] <= 1000000 or not isinstance(state["jobs"], list) or len(state["jobs"]) > 4:
            raise ValueError("Invalid language queue bounds.")
        result.source, result.next_id = state["source"], state["next_id"]
        for job in state["jobs"]:
            job = copy.deepcopy(job)
            if payload["format"] == 30:
                if not isinstance(job, dict) or set(job) != LEGACY_JOB_FIELDS:
                    raise ValueError("Invalid legacy language job fields.")
                job.update(mode="recall", validation=None)
            validate_job(job, result)
            result.jobs[job["id"]] = job
        cleanup.pop_all()
    torch.set_rng_state(rng)
    return result


def validate_job(job, controller):
    if not isinstance(job, dict) or set(job) != JOB_FIELDS or type(job["id"]) is not int or not 1 <= job["id"] < controller.next_id or job["id"] in controller.jobs:
        raise ValueError("Invalid language job identity/fields.")
    references(job["question"])
    window = None if job["window"] is None else tuple(job["window"])
    validate_window(window, controller.clock)
    if job["view"] not in ("initial", "current") or job["status"] not in ("waiting_parse", "waiting_expression", *TERMINAL):
        raise ValueError("Invalid language job phase.")
    if job["mode"] not in ("recall", "expectation") or (job["mode"] == "expectation" and (job["view"] != "current" or job["window"] is not None)):
        raise ValueError("Invalid queued language mode.")
    for name in ("issued", "expires", "retry_at"):
        value = job[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("Invalid language job time.")
    if not 0 <= job["issued"] <= controller.clock or not 5 <= job["expires"] - job["issued"] <= 3600 or not 0 <= job["retry_at"] <= controller.clock + 60:
        raise ValueError("Invalid language job clock bounds.")
    if type(job["refreshes"]) is not int or not 0 <= job["refreshes"] <= 3 or type(job["deferrals"]) is not int or not 0 <= job["deferrals"] <= 1000000:
        raise ValueError("Invalid language job counters.")
    if job["error"] is not None and (not isinstance(job["error"], str) or len(job["error"]) > 2048):
        raise ValueError("Invalid language job error.")
    if not isinstance(job["evidence"], list) or len(job["evidence"]) > 1:
        raise ValueError("Invalid queued evidence.")
    for item in job["evidence"]:
        if job["mode"] == "expectation":
            validate_expectation_evidence(item)
            continue
        if not isinstance(item, dict) or set(item) != {"source", "interpretation", "attributes", "confidence"} or not isinstance(item["attributes"], list):
            raise ValueError("Invalid queued evidence fields.")
        MemoryEvidence(item["source"], item["interpretation"], tuple(tuple(pair) for pair in item["attributes"]), item["confidence"]).validate()
    validate_validation(job, controller.clock)
    if job["plan"] is None:
        if job["evidence"] or job["fingerprint"] is not None or job["proposal"] is not None or job["status"] in ("waiting_expression", "completed"):
            raise ValueError("Unparsed job contains language facts/proposal.")
        return
    validate_plan(job["plan"], job["question"], controller.model)
    if job["fingerprint"] is not None and job["fingerprint"] != fingerprint(job["evidence"], job["mode"]):
        raise ValueError("Queued evidence fingerprint changed.")
    if job["status"] == "waiting_parse":
        raise ValueError("Parsed job cannot await parsing.")
    if job["status"] == "completed":
        validate_proposal(job["proposal"], job, controller.model)
    elif job["proposal"] is not None:
        raise ValueError("Unfinished language job contains a final proposal.")


def validate_expectation_evidence(value):
    if not isinstance(value, dict) or set(value) != {item.name for item in fields(ExpectationEvidence)}:
        raise ValueError("Invalid queued expectation evidence fields.")
    ExpectationEvidence(**value).validate()


def validate_validation(job, clock):
    validation = job["validation"]
    if job["mode"] != "expectation" or job["status"] != "completed":
        if validation is not None:
            raise ValueError("Unfinished or factual job contains expectation validation.")
        return
    if not isinstance(validation, dict) or set(validation) != {"kind", "checked_at", "evidence"} or validation["kind"] != "learned_expectation":
        raise ValueError("Invalid expectation delivery validation.")
    now = validation["checked_at"]
    if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now) or not job["issued"] <= now <= clock:
        raise ValueError("Invalid expectation validation time.")
    if not isinstance(validation["evidence"], list) or len(validation["evidence"]) > 1:
        raise ValueError("Invalid current expectation evidence.")
    for item in validation["evidence"]:
        validate_expectation_evidence(item)
    if fingerprint(validation["evidence"], "expectation") != job["fingerprint"]:
        raise ValueError("Current validation changes the proposed expectation.")
