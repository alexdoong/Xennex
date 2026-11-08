"""Finite lexical/semantic/language integration, with an explicit fixture control.

The fixture checks dataflow, not pretrained language quality. Lexical lessons
are batch pairs of raw sensory encodings and written names, not live encounters.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
import time
from pathlib import Path

import torch

from .adaptive_memory import recalled_pair
from .consolidating_mind import load as load_source
from .episodic_experiment import packets
from .episodic_language import write_report
from .expectation_language import ExpectationLanguage, GroundedExpectationLanguage
from .experience_signals import WORDS, samples
from .grounded_mind import GroundedMind, load, save
from .language_input import references
from .process_metrics import Budget
from .language import AdmissionDeferred

NAMES = (("vimuq", "fabe", "fabi", "fabo"), ("neva", "nave", "navi", "navo"),
         ("zaba", "zabe", "zabi", "zabo"), ("torbe", "rave", "ravi", "ravo"))


class FixtureLanguage(ExpectationLanguage):
    def __init__(self):
        super().__init__("http://127.0.0.1:11438", "fixture")

    def metadata(self):
        return {"size": 1, "digest": "fixture", "name": self.model}

    def admit(self, metadata):
        pass

    def _request(self, path, body=None):
        prompt = body["messages"][1]["content"]
        if "names" in body["format"]["properties"]:
            names = references(prompt)
            draft = {"field": "autor", "names": names, "uncertain": not names}
        else:
            evidence = json.loads(prompt.split("\nPERGUNTA:")[0].split("\n", 1)[1])
            draft = {"text": "Sem expectativa aprendida." if evidence is None else
                            "Pelo padrão aprendido, eu esperaria " + evidence["value"] + ".",
                     "expectations": {} if evidence is None else {evidence["target"]: evidence["value"]},
                     "factual_claims": {}, "uncertain": evidence is None}
        return {"done": True, "done_reason": "stop", "message": {"content": json.dumps(draft)}}


def source_stream(agent):
    memory = agent.mind.actor.session.memory
    stream = hashlib.sha256()
    for episode in range(len(memory.blocks)):
        pair = recalled_pair(memory, episode, agent.clock, agent.semantic.target)
        if pair is None:
            raise ValueError("Existing source fact cannot be recalled.")
        stream.update(json.dumps({"key": pair["key"].tolist(), "value": pair["value"].tolist()}, sort_keys=True).encode())
    return stream.hexdigest()


def resumed(checkpoint, output, question):
    torch.set_num_threads(1)
    agent = load(checkpoint)
    try:
        result = GroundedExpectationLanguage(agent, FixtureLanguage()).query(question)
        write_report(output, result)
    finally:
        agent.mind.actor.session.memory.close()


def run(checkpoint, output, seed=17, backend="fixture", endpoint="http://127.0.0.1:11438", model="qwen3.5:4b"):
    torch.set_num_threads(1)
    budget, started = Budget(100000, 180), time.perf_counter()
    output.mkdir(parents=True, exist_ok=False)
    source_hash = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    agent = GroundedMind(load_source(checkpoint))
    session = agent.mind.actor.session
    language = FixtureLanguage() if backend == "fixture" else ExpectationLanguage(endpoint, model)
    bridge = GroundedExpectationLanguage(agent, language)
    report = {"format": "expectation-language-v1", "seed": seed, "backend": backend,
              "language_quality_evaluated": backend == "installed", "free_text_verified": False,
              "lexical_curriculum": "batch raw sensory/name pairs, without creating episodes",
              "completed": False, "accepted": False, "cases": []}
    write_report(output / "report.json", report)
    try:
        before_sources = source_stream(agent)
        semantic_before = agent.semantic.transaction_state()
        rng = random.Random(seed + 987000)
        lessons = []
        with torch.no_grad():
            for field in range(4):
                for category in range(4):
                    truth = [0] * 4
                    truth[field] = category
                    for frame in range(12):
                        image, sound = samples(tuple(truth), rng, tuple(index == field for index in range(4)))
                        modality = ("image", "audio", "both")[frame % 3]
                        observations = packets(image, sound, agent.clock, frame * 2, modality)
                        _, joint = session.interpret(observations)
                        agent.words.teach(NAMES[field][category], joint[0], agent.clock)
                    learned = agent.words.lookup(NAMES[field][category])
                    lessons.append(learned["supported"] and (learned["field"], learned["category"]) == (field, category))
        report["names_correct"] = sum(lessons)
        save(output / "grounded.pt", agent)
        mapping = list(range(4))
        random.Random(seed + 803000).shuffle(mapping)
        for context in range(4):
            for activity in range(4):
                for appraisal in (1, 3):
                    budget.check(len(report["cases"]))
                    question = ('Quem você esperaria durante "' + NAMES[0][activity] + '" em "' +
                                NAMES[3][context] + '" com "' + NAMES[1][appraisal] + '"?')
                    # This target stays in the evaluator; no model or bridge receives it.
                    expected = WORDS[2][mapping[(activity + context + (context == 1)) % 4]]
                    query_started = time.perf_counter()
                    result = bridge.query(question)
                    query_seconds = time.perf_counter() - query_started
                    correct = result["accepted"] and result["proposal"]["expectations"] == {"autor": expected}
                    report["cases"].append({"question": question, "expected": expected, "correct": correct,
                                            "query_seconds": query_seconds, "result": result})
                    write_report(output / "report.json", report)
        missing = bridge.query('Quem você esperaria durante "unknownsymbol" em "torbe"?')
        missing_abstained = missing["accepted"] and not missing["proposal"]["expectations"] and missing["proposal"]["uncertain"]
        sources_intact = before_sources == source_stream(agent)
        semantic_intact = all(torch.equal(value, agent.semantic.state_dict()[name]) for name, value in semantic_before[0].items())
        semantic_intact &= torch.equal(semantic_before[1], agent.semantic.index.generator.get_state())
        question = report["cases"][0]["question"]
        expected_resume = report["cases"][0]["result"]
        agent.mind.actor.session.memory.close()
        # Fixture resume is a process/state test, including when the parent used a real model.
        subprocess.run([sys.executable, "-m", "scripts.alice_memory.expectation_experiment", "--resume",
                        str((output / "grounded.pt").resolve()), "--output", str((output / "resumed.json").resolve()),
                        "--question", question], check=True, timeout=45, capture_output=True, text=True)
        resumed_result = json.loads((output / "resumed.json").read_text(encoding="utf-8"))
        resume_equal = (resumed_result["accepted"] and resumed_result["grounding"] == expected_resume["grounding"]
                        and resumed_result["evidence"] == expected_resume["evidence"]
                        and resumed_result["proposal"]["expectations"] == expected_resume["proposal"]["expectations"])
        correct = sum(case["correct"] for case in report["cases"])
        report.update(completed=True, correct=correct, total=len(report["cases"]), unknown_abstained=missing_abstained,
                      semantic_weights_and_rng_unchanged=bool(semantic_intact), source_facts_preserved=sources_intact,
                      source_sha256=source_hash, source_file_unchanged=source_hash == hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                      fresh_process_expectation_equal=resume_equal, seconds=time.perf_counter() - started,
                      accepted=bool(correct == 32 and all(lessons) and missing_abstained and semantic_intact and sources_intact and resume_equal))
        write_report(output / "report.json", report)
        return report
    except (Exception, KeyboardInterrupt) as error:
        report["error"] = type(error).__name__ + ": " + str(error)[:2048]
        if isinstance(error, AdmissionDeferred):
            report["admission_deferred"] = {"used_bytes": error.used_bytes, "total_bytes": error.total_bytes,
                                             "reserve_bytes": error.reserve_bytes}
        write_report(output / "report.json", report)
        raise
    finally:
        agent.mind.actor.session.memory.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--backend", choices=("fixture", "installed"), default="fixture")
    parser.add_argument("--endpoint", default="http://127.0.0.1:11438")
    parser.add_argument("--model", default="qwen3.5:4b")
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--question")
    args = parser.parse_args()
    if args.resume:
        resumed(args.resume, args.output, args.question)
    elif args.checkpoint:
        report = run(args.checkpoint, args.output, args.seed, args.backend, args.endpoint, args.model)
        print(json.dumps({key: report[key] for key in ("accepted", "correct", "total", "names_correct", "seconds")}))
    else:
        parser.error("A checkpoint or resume checkpoint is required.")


if __name__ == "__main__":
    main()
