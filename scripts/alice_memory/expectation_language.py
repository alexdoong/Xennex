"""Selective language expression of learned expectations, distinct from recall.

No proposal is written to memory. Free prose remains unverified; structured
expectations and empty factual claims are independently checked at the boundary.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from dataclasses import asdict
from pathlib import Path

import torch

from .episodic_language import write_report
from .experience_signals import FIELDS, WORDS
from .grounded_mind import load
from .expectation_protocol import ExpectationEvidence, ExpectationProposal, ExpectationLanguage, validate_expectation_proposal
from .language_input import LanguageInput, references



def state_digest(agent):
    """Bind learned interpretation and source progress without paging all weights.

    The neural predictor verifies the actual witness weights again at delivery.
    Source changes through the owner advance observation/revision metadata.
    This is not a full forensic scan of every cold page on each question.
    """
    stream = io.BytesIO()
    torch.save([agent.words.state_dict(), agent.semantic.state_dict(),
                agent.mind.actor.session.perception.state_dict()], stream)
    digest = hashlib.sha256(stream.getvalue())
    digest.update(json.dumps(agent.words.names, ensure_ascii=False).encode())
    memory = agent.mind.actor.session.memory
    metadata = [(trace.identifier, trace.started, trace.ended, trace.observations,
                 block.revisions.tolist(), block.learned_at.tolist())
                for trace, block in zip(memory.traces, memory.blocks)]
    digest.update(json.dumps(metadata).encode())
    return digest.hexdigest()


class GroundedExpectationLanguage:
    def __init__(self, agent, language: ExpectationLanguage):
        self.agent, self.language = agent, language

    def query(self, question: str):
        # Parser sees only language; no target labels or experience definitions.
        plan = LanguageInput(self.language).parse(question)
        before = state_digest(self.agent)
        captured = None
        prediction = None
        if not plan.uncertain and plan.field in FIELDS:
            captured = self.agent.expect_names(list(plan.names), FIELDS.index(plan.field))
            prediction = captured["prediction"]
        evidence = None
        if prediction is not None and prediction["supported"]:
            evidence = ExpectationEvidence(prediction["target"], prediction["value"], prediction["confidence"],
                                           prediction.get("support_policy", "conditional-v2"), before)
        proposal = self.language.propose_expectation(question, evidence)
        try:
            if not isinstance(proposal, ExpectationProposal):
                raise ValueError("Invalid expectation proposal type.")
            validate_expectation_proposal(asdict(proposal), evidence, self.language.model)
            accepted = True
        except ValueError:
            accepted = False
        after = state_digest(self.agent)
        refreshed = None if captured is None else self.agent.expect_names(list(plan.names), FIELDS.index(plan.field))
        unchanged = before == after and captured == refreshed
        return {"kind": "learned_expectation", "plan": asdict(plan), "grounding": captured,
                "evidence": None if evidence is None else asdict(evidence),
                "proposal": asdict(proposal) if accepted and unchanged else None,
                "accepted": bool(accepted and unchanged), "state_unchanged": unchanged,
                "reason": "supported_structured_expectation" if accepted and unchanged else
                          "state_changed_during_generation" if not unchanged else "invalid_language_proposal",
                "free_text_verified": False, "autobiographical_write": False}


def question_from_file(path: Path):
    if path.stat().st_size > 16003:
        raise ValueError("Question file exceeds its byte budget.")
    question = path.read_text(encoding="utf-8-sig")
    references(question)
    return question


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--model", default="qwen3.5:4b")
    question_args = parser.add_mutually_exclusive_group(required=True)
    question_args.add_argument("--question")
    question_args.add_argument("--question-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    question = question_from_file(args.question_file) if args.question_file else args.question
    references(question)
    torch.set_num_threads(1)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    agent = load(args.checkpoint)
    try:
        bridge = GroundedExpectationLanguage(agent, ExpectationLanguage(args.endpoint, args.model))
        report = bridge.query(question)
        write_report(args.output, report)
        print(json.dumps({"output": str(args.output.resolve()), "accepted": report["accepted"]}))
    finally:
        memory = agent.mind.actor.session.memory
        if hasattr(memory, "close"):
            memory.close()


if __name__ == "__main__":
    main()
