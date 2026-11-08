"""Installed LLM parses Portuguese; learned names retrieve episodic neural facts."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
from dataclasses import asdict
from pathlib import Path

import torch

from .episodic_language import evidence_from_recall, write_report
from .grounded_mind import load
from .language import LocalLanguage
from .language_input import FIELDS, LanguageInput


def read_questions(path: Path) -> list[dict]:
    if path.stat().st_size > 65536:
        raise ValueError("Grounded question bundle exceeds its size budget.")
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or set(document) != {"format", "cases"} or type(document["format"]) is not int or document["format"] != 1:
        raise ValueError("Invalid grounded question bundle.")
    cases = document["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= 16:
        raise ValueError("Expected one to sixteen controlled questions.")
    for item in cases:
        if not isinstance(item, dict) or set(item) != {"case", "question", "field", "view", "window", "expected"}:
            raise ValueError("Invalid controlled question fields.")
        if not isinstance(item["case"], str) or not 1 <= len(item["case"]) <= 64 or not isinstance(item["question"], str) or not 1 <= len(item["question"]) <= 4000 or item["field"] not in (*FIELDS, "unknown") or item["view"] not in ("initial", "current"):
            raise ValueError("Invalid controlled question metadata.")
        expected = item["expected"]
        if not isinstance(expected, dict) or len(expected) > 4 or any(key not in FIELDS or not isinstance(value, str) or not 1 <= len(value) <= 256 for key, value in expected.items()):
            raise ValueError("Invalid evaluator-only expected attributes.")
        window = item["window"]
        if window is not None and (not isinstance(window, list) or len(window) != 2
                or any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in window)
                or not 0 <= window[0] <= window[1]):
            raise ValueError("Invalid controlled occurrence-time window.")
    if len({item["case"] for item in cases}) != len(cases):
        raise ValueError("Duplicate controlled question case.")
    return cases


def learned_digest(agent) -> str:
    # Include every page's weights, not its route/address index. Visits stay bounded.
    digest = hashlib.sha256()
    states = [agent.words.state_dict(), agent.semantic.bank.state_dict(),
              agent.mind.actor.session.perception.state_dict(), agent.mind.actor.policy.state_dict()]
    for block in agent.mind.actor.session.memory.blocks:
        stream = io.BytesIO()
        torch.save([bank.state_dict() for bank in block.banks], stream)
        digest.update(stream.getvalue())
    stream = io.BytesIO()
    torch.save(states, stream)
    digest.update(stream.getvalue())
    return digest.hexdigest()


def run(endpoint: str, model: str, checkpoint: Path, questions: Path, output: Path) -> dict:
    torch.set_num_threads(1)
    cases = read_questions(questions)
    output.mkdir(parents=True, exist_ok=False)
    agent = load(checkpoint)
    source = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    language = LocalLanguage(endpoint, model, wait_seconds=15)
    parser = LanguageInput(language)
    results = []
    report = {"model": model, "checkpoint_sha256": source,
              "questions_sha256": hashlib.sha256(questions.read_bytes()).hexdigest(),
              "scope": "Portuguese syntax plus written-name associative weights and selective episodic evidence",
              "definitions_supplied_to_parser": False, "direct_llm_latent_coupling": False,
              "free_text_requires_review": True, "completed": False, "accepted": False,
              "case_count": len(cases), "completed_cases": 0, "cases": results}
    write_report(output / "report.json", report)
    try:
        before = learned_digest(agent)
        report["learned_weights_before_sha256"] = before
        write_report(output / "report.json", report)
        for case in cases:
            result = {"case": case["case"], "question": case["question"], "view": case["view"], "accepted": False}
            try:
                # Only the question goes to the parser; evaluator fields/expected values never do.
                plan = parser.parse(case["question"])
                result["plan"] = asdict(plan)
                grounding, evidence, action = None, (), None
                window = None if case["window"] is None else tuple(case["window"])
                if not plan.uncertain and plan.field in FIELDS:
                    grounding = agent.query_names(list(plan.names), case["view"], window)
                    if grounding["result"] is not None:
                        evidence = evidence_from_recall(grounding["result"], "grounded-" + source[:16])
                    if grounding["grounding_supported"] and case["view"] == "current":
                        queued = agent.request_names(list(plan.names), FIELDS.index(plan.field), window)
                        if queued["queued"]:
                            action = agent.tick(.1)["action"]
                required = (plan.field,) if plan.field in FIELDS else ()
                proposal = asdict(language.propose(case["question"], evidence, case["view"], required))
                expected = case["expected"]
                recovered = all(proposal["claims"].get(key) == value for key, value in expected.items())
                abstained = bool(proposal["uncertain"] and not proposal["claims"]) if not expected else None
                result.update({"grounding": grounding, "action": action, "proposal": proposal,
                               "parsed_field_correct": plan.field == case["field"],
                               "expected_claims_recovered": recovered, "unsupported_question_abstained": abstained,
                               "accepted": bool(plan.field == case["field"] and proposal["structured_claims_supported"]
                                                and recovered and (abstained if not expected else True))})
            except (OSError, RuntimeError, ValueError) as error:
                result["error"] = str(error)
            results.append(result)
            report["completed_cases"] = len(results)
            write_report(output / "report.json", report)
        after = learned_digest(agent)
        unchanged = before == after
        report.update({"completed": True, "learned_weights_after_sha256": after,
                       "learned_weights_unchanged": unchanged,
                       "accepted": unchanged and all(item["accepted"] for item in results)})
        write_report(output / "report.json", report)
    except (Exception, KeyboardInterrupt) as error:
        report["fatal_error"] = type(error).__name__ + ": " + str(error)
        write_report(output / "report.json", report)
        raise
    finally:
        agent.mind.actor.session.memory.close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--model", default="qwen3.5:4b")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.endpoint, args.model, args.checkpoint, args.questions, args.output)
    print(json.dumps({"output": str(args.output.resolve()), "accepted": report["accepted"],
                      "cases": [{"case": item["case"], "accepted": item["accepted"]} for item in report["cases"]]}))


if __name__ == "__main__":
    main()
