"""Bounded taught affine concepts, weight-based composition and inquiries.

The affine family and composition algorithm are supplied capabilities. The
transformations are learned. Covariance is a coverage heuristic, not confidence
that arbitrary concepts or a nonlinear teaching source have been understood.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import torch

from .online_memory import OnlineMemory

MAX_CONCEPTS = 32
MAX_LESSONS = 512
MAX_HYPOTHESES = 32


def identifier(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 96 or any(ord(char) < 32 for char in value):
        raise ValueError("Invalid conceptual identifier.")
    return value


def scalar(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError("Invalid conceptual scalar.")
    return float(value)


def vector(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("Expected a bounded two-dimensional vector.")
    return torch.tensor([scalar(item, -64, 64) for item in value], dtype=torch.float64)


def key(value):
    return torch.cat((vector(value), torch.ones(1, dtype=torch.float64)))


@dataclass(frozen=True)
class ConceptLesson:
    concept: str
    input: tuple[float, float]
    output: tuple[float, float]
    source: str
    sequence: int
    acquired_at: float
    origin: str = "taught"


class ConceptMemory:
    def __init__(self):
        self.banks = {}
        self.sources = {}
        self.hypotheses = {}
        self.sequence = -1
        self.lessons = 0
        self.next_hypothesis = 1

    def teach(self, lesson, now):
        if not isinstance(lesson, ConceptLesson):
            raise ValueError("Concept learning requires a typed external lesson.")
        name, source = identifier(lesson.concept), identifier(lesson.source)
        x, y = key(lesson.input), vector(lesson.output)
        scalar(now, 0, 1e12)
        scalar(lesson.acquired_at, 0, now)
        if lesson.origin not in ("taught", "tested") or type(lesson.sequence) is not int or not 0 <= lesson.sequence <= 1000000:
            raise ValueError("A deduction cannot teach itself as external evidence.")
        if lesson.sequence <= self.sequence:
            return {"learned": False, "reason": "stale_lesson"}
        if self.lessons >= MAX_LESSONS or (name not in self.banks and len(self.banks) >= MAX_CONCEPTS):
            raise ValueError("Conceptual learning budget reached.")
        candidate = OnlineMemory(3, 2)
        if name in self.banks:
            candidate.load_state_dict(self.banks[name].state_dict())
        candidate.write(x, y, strength=10.)
        if not all(torch.isfinite(item).all() for item in candidate.state_dict().values()):
            raise ValueError("Concept update diverged; prior state retained.")
        self.banks[name] = candidate
        self.sources.setdefault(name, []).append({"source": source, "origin": lesson.origin,
                                                 "sequence": lesson.sequence, "acquired_at": lesson.acquired_at})
        self.sequence, self.lessons = lesson.sequence, self.lessons + 1
        invalidated = []
        for number, hypothesis in self.hypotheses.items():
            if name in hypothesis["premises"] and hypothesis["status"] != "superseded":
                hypothesis["status"] = "superseded"
                invalidated.append(number)
        return {"learned": True, "kind": lesson.origin, "version": int(candidate.writes), "invalidated": invalidated}

    def uncertainty(self, concept, value):
        identifier(concept)
        x = key(value)
        bank = self.banks.get(concept)
        if bank is None:
            return 1000.
        return max(0., float(bank.variance(x))) / float(x @ x)

    def predict(self, concept, value):
        x = key(value)
        uncertainty = self.uncertainty(concept, value)
        bank = self.banks.get(concept)
        supported = bank is not None and int(bank.writes) >= 3 and uncertainty <= .1
        output = None if not supported else (bank.weights @ x).tolist()
        if output is not None and any(abs(item) > 64 for item in output):
            supported, output = False, None
        return {"kind": "deduced", "supported": supported, "value": output,
                "uncertainty": uncertainty, "uncertainty_is_calibrated": False,
                "version": None if bank is None else int(bank.writes), "autobiographical_write": False}

    def compose(self, concepts, value):
        if not isinstance(concepts, (tuple, list)) or not 1 <= len(concepts) <= 8:
            raise ValueError("Expected one to eight conceptual premises.")
        current = vector(value).tolist()
        premises = {}
        for name in concepts:
            result = self.predict(name, current)
            if not result["supported"]:
                return {"kind": "deduced", "supported": False, "value": None,
                        "missing": name, "premises": premises, "autobiographical_write": False}
            premises[name] = result["version"]
            current = result["value"]
        return {"kind": "deduced", "supported": True, "value": current,
                "premises": premises, "autobiographical_write": False}

    def hypothesize(self, concepts, value, now):
        scalar(now, 0, 1e12)
        result = self.compose(concepts, value)
        if not result["supported"]:
            return result
        if len(self.hypotheses) >= MAX_HYPOTHESES:
            raise ValueError("Conceptual hypothesis budget reached.")
        number = self.next_hypothesis
        self.hypotheses[number] = {"chain": list(concepts), "input": vector(value).tolist(),
                                   "prediction": result["value"], "premises": result["premises"],
                                   "status": "untested", "created_at": now, "verification": None}
        self.next_hypothesis += 1
        return {**result, "id": number, "status": "untested"}

    def verify(self, number, value, source, now):
        scalar(now, 0, 1e12)
        identifier(source)
        actual = vector(value)
        if type(number) is not int or number not in self.hypotheses:
            raise ValueError("Unknown conceptual hypothesis.")
        hypothesis = self.hypotheses[number]
        if now < hypothesis["created_at"]:
            raise ValueError("Verification precedes its hypothesis.")
        if hypothesis["status"] != "untested":
            return {"accepted": False, "reason": hypothesis["status"]}
        error = float((actual - vector(hypothesis["prediction"])).abs().max())
        hypothesis["status"] = "verified_example" if error <= .02 else "contradicted"
        hypothesis["verification"] = {"source": source, "checked_at": now, "max_error": error}
        return {"accepted": True, "status": hypothesis["status"], "max_error": error,
                "general_proof": False, "learned_from_own_prediction": False}

    def choose_inquiry(self, options):
        if not isinstance(options, list) or not 1 <= len(options) <= 64:
            raise ValueError("Expected one to sixty-four allowed inquiry options.")
        scored = []
        for index, option in enumerate(options):
            if not isinstance(option, dict) or set(option) != {"concept", "input", "cost"}:
                raise ValueError("Invalid inquiry fields.")
            cost = scalar(option["cost"], 0, 100)
            uncertainty = self.uncertainty(option["concept"], option["input"])
            scored.append((uncertainty / (1. + cost), -index, uncertainty))
        score, negative, uncertainty = max(scored)
        option = options[-negative]
        return {"concept": option["concept"], "input": vector(option["input"]).tolist(), "cost": option["cost"],
                "uncertainty": uncertainty, "score": score, "reason": "weight_covariance_and_cost",
                "general_curiosity": False}

    def snapshot(self):
        import copy
        return {"format": 1, "banks": {name: {key: value.clone() for key, value in bank.state_dict().items()} for name, bank in self.banks.items()},
                "sources": copy.deepcopy(self.sources), "hypotheses": copy.deepcopy(self.hypotheses),
                "sequence": self.sequence, "lessons": self.lessons, "next_hypothesis": self.next_hypothesis}


def restore(payload, now):
    import copy
    fields = {"format", "banks", "sources", "hypotheses", "sequence", "lessons", "next_hypothesis"}
    if not isinstance(payload, dict) or set(payload) != fields or type(payload["format"]) is not int or payload["format"] != 1:
        raise ValueError("Invalid conceptual checkpoint.")
    scalar(now, 0, 1e12)
    result = ConceptMemory()
    banks, sources, hypotheses = payload["banks"], payload["sources"], payload["hypotheses"]
    if not isinstance(banks, dict) or len(banks) > MAX_CONCEPTS or not isinstance(sources, dict) or sources.keys() != banks.keys() or not isinstance(hypotheses, dict) or len(hypotheses) > MAX_HYPOTHESES:
        raise ValueError("Invalid conceptual checkpoint bounds.")
    seen = []
    for name, state in banks.items():
        identifier(name)
        bank = OnlineMemory(3, 2)
        expected = bank.state_dict()
        if not isinstance(state, dict) or state.keys() != expected.keys() or any(not isinstance(item, torch.Tensor) or item.device.type != "cpu" or item.dtype != expected[key].dtype or item.shape != expected[key].shape or not torch.isfinite(item).all() for key, item in state.items()):
            raise ValueError("Invalid conceptual weight tensors.")
        bank.load_state_dict(state)
        if not 1 <= int(bank.writes) <= MAX_LESSONS or bank.weights.abs().max() > 10000 or not torch.allclose(bank.precision, bank.precision.T, atol=1e-8, rtol=0) or torch.linalg.cholesky_ex(bank.precision).info.item() != 0:
            raise ValueError("Invalid conceptual covariance/writes.")
        records = sources[name]
        if not isinstance(records, list) or len(records) != int(bank.writes):
            raise ValueError("Invalid conceptual source count.")
        for item in records:
            if not isinstance(item, dict) or set(item) != {"source", "origin", "sequence", "acquired_at"} or item["origin"] not in ("taught", "tested") or type(item["sequence"]) is not int or not 0 <= item["sequence"] <= 1000000:
                raise ValueError("Invalid conceptual source provenance.")
            identifier(item["source"])
            scalar(item["acquired_at"], 0, now)
            seen.append(item["sequence"])
        if [item["sequence"] for item in records] != sorted(item["sequence"] for item in records):
            raise ValueError("Nonmonotonic conceptual provenance.")
        result.banks[name] = bank
    if type(payload["lessons"]) is not int or not 0 <= payload["lessons"] <= MAX_LESSONS or len(seen) != payload["lessons"] or len(seen) != len(set(seen)) or type(payload["sequence"]) is not int or payload["sequence"] != max(seen, default=-1):
        raise ValueError("Invalid conceptual lesson counters.")
    for number, item in hypotheses.items():
        if type(number) is not int or number < 1 or not isinstance(item, dict) or set(item) != {"chain", "input", "prediction", "premises", "status", "created_at", "verification"}:
            raise ValueError("Invalid saved conceptual hypothesis.")
        vector(item["input"])
        vector(item["prediction"])
        scalar(item["created_at"], 0, now)
        chain = item["chain"]
        if not isinstance(chain, list) or not 1 <= len(chain) <= 8 or not isinstance(item["premises"], dict) or set(chain) != set(item["premises"]) or any(name not in banks for name in chain) or item["status"] not in ("untested", "verified_example", "contradicted", "superseded"):
            raise ValueError("Invalid saved conceptual premise/status.")
        for name, version in item["premises"].items():
            if type(version) is not int or not 3 <= version <= int(result.banks[name].writes) or (item["status"] != "superseded" and version != int(result.banks[name].writes)):
                raise ValueError("Stale conceptual hypothesis marked current.")
        if item["status"] != "superseded":
            current = result.compose(chain, item["input"])
            if not current["supported"] or current["value"] != item["prediction"]:
                raise ValueError("Saved hypothesis disagrees with its current learned premises.")
        verification = item["verification"]
        if verification is not None:
            if not isinstance(verification, dict) or set(verification) != {"source", "checked_at", "max_error"}:
                raise ValueError("Invalid conceptual verification.")
            identifier(verification["source"])
            scalar(verification["checked_at"], item["created_at"], now)
            error = scalar(verification["max_error"], 0, 128)
            if (item["status"] == "verified_example" and error > .02) or (item["status"] == "contradicted" and error <= .02):
                raise ValueError("Verification status disagrees with error.")
        if (item["status"] in ("verified_example", "contradicted")) != (verification is not None) and item["status"] != "superseded":
            raise ValueError("Missing or premature conceptual verification.")
    if type(payload["next_hypothesis"]) is not int or not 1 <= payload["next_hypothesis"] <= MAX_HYPOTHESES + 1 or set(hypotheses) != set(range(1, payload["next_hypothesis"])):
        raise ValueError("Invalid conceptual hypothesis sequence.")
    result.sources, result.hypotheses = copy.deepcopy(sources), copy.deepcopy(hypotheses)
    result.sequence, result.lessons, result.next_hypothesis = payload["sequence"], payload["lessons"], payload["next_hypothesis"]
    return result
