"""Taught abstract operations in the existing mind; no sensory labels or LLM.

The external teacher owns the matrices. The agent receives only requested
input/output lessons; held-out compositions and targets stay in the evaluator.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import torch

from .concept_memory import ConceptLesson, restore as restore_concepts
from .conceptual_mind import ConceptualMind, save
from .continuous_experiment import load_scheduler
from .persistent_runtime import close_agent
from .reactivation_index import source_digest
from .runtime_store import atomic_json


class Teacher:
    def __init__(self, seed):
        generator = torch.Generator().manual_seed(seed)
        self.names = [f"nivo-{seed}", f"zalu-{seed}"]
        self.matrices = {name: torch.randn(2, 2, generator=generator, dtype=torch.float64) * .4 + torch.eye(2) * .5 for name in self.names}
        self.offsets = {name: torch.randn(2, generator=generator, dtype=torch.float64) * .1 for name in self.names}

    def answer(self, name, value):
        return (self.matrices[name] @ torch.tensor(value, dtype=torch.float64) + self.offsets[name]).tolist()

    def expected(self, chain, value):
        for name in chain:
            value = self.answer(name, value)
        return value


def evaluate(memory, teacher, probes):
    results = []
    for chain, value in probes:
        result = memory.compose(chain, value)
        expected = teacher.expected(chain, value)
        error = None if not result["supported"] else float((torch.tensor(result["value"]) - torch.tensor(expected)).abs().max())
        results.append({"chain": chain, "input": value, "supported": result["supported"], "max_error": error,
                        "correct": error is not None and error <= .02})
    return results


def child(checkpoint, probe_path, output):
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    agent, mind, _ = load_scheduler(checkpoint, output.parent / "child-workers")
    try:
        prediction = agent.concepts.compose(probe["chain"], probe["input"])
        tick = agent.tick(.1)
        source_owner = getattr(agent.semantic, "_source", None)
        from .language_coordinator import LanguageCoordinator
        grounded = agent.agent.agent if isinstance(agent.agent, LanguageCoordinator) else agent.agent
        single_owner = agent.agent.mind is mind and grounded.words.perception is mind.actor.session.perception
        if source_owner is not None:
            single_owner = single_owner and source_owner() is mind.actor.session.memory
        atomic_json(output, {"prediction": prediction, "inquiry": tick["concept_inquiry"],
                             "hidden": agent.temporal.hidden.tolist(), "clock": agent.clock,
                             "single_episode_owner": single_owner})
    finally:
        close_agent(agent, mind)


def run(checkpoint, output, seed):
    output.mkdir(parents=True, exist_ok=False)
    source_hash = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    base, mind, _ = load_scheduler(checkpoint, output / "workers")
    agent = ConceptualMind(base)
    report = {"seed": seed, "accepted": False, "live_sensors": False, "language_quality_evaluated": False,
              "scope": "taught affine 2D operations, supplied composition and covariance inquiry",
              "general_conceptual_understanding": False, "source_sha256": source_hash}
    atomic_json(output / "report.json", report)
    try:
        memory = mind.actor.session.memory
        original = [source_digest(block) for block in memory.blocks]
        observed = agent.temporal.observations
        teacher = Teacher(seed)
        first, second = teacher.names
        generator = torch.Generator().manual_seed(seed + 89100)
        probes = []
        for chain in ([first], [second], [first, second], [second, first]):
            probes.extend((chain, torch.randn(2, generator=generator).clamp(-1.8, 1.8).tolist()) for _ in range(16))
        before = evaluate(agent.concepts, teacher, probes)

        def teach(name, value, origin="taught"):
            agent.tick(.1)
            item = ConceptLesson(name, tuple(value), tuple(teacher.answer(name, value)), "synthetic-external-teacher",
                                 agent.concepts.sequence + 1, agent.clock, origin)
            agent.teach_concept(item)

        for value in ([0., 0.], [1., 0.], [-1., 0.], [0., 1.], [0., -1.], [1., 1.]):
            teach(second, value)
        for value in ([0., 0.], [1., 0.], [-1., 0.]):
            teach(first, value)
        baseline = restore_concepts(agent.concepts.snapshot(), agent.clock)
        active_queries = []
        for _ in range(4):
            options = [{"concept": first, "input": [1., 0.], "cost": 0.},
                       {"concept": second, "input": [0., 1.], "cost": 0.},
                       {"concept": first, "input": [0., 1.], "cost": 0.},
                       {"concept": first, "input": [0., -1.], "cost": 0.}]
            number = agent.request_study(options)
            inquiry = agent.tick(.1)["concept_inquiry"]
            active_queries.append(inquiry)
            agent.take_inquiry(number)
            teach(inquiry["concept"], inquiry["input"], "tested")
            item = ConceptLesson(first, (1., 0.), tuple(teacher.answer(first, [1., 0.])), "same-budget-fixed-teacher",
                                 baseline.sequence + 1, agent.clock, "tested")
            baseline.teach(item, agent.clock)
        after = evaluate(agent.concepts, teacher, probes)
        fixed = evaluate(baseline, teacher, probes)
        erased = restore_concepts(agent.concepts.snapshot(), agent.clock)
        for bank in erased.banks.values():
            bank.weights.zero_()
        erased_results = evaluate(erased, teacher, probes)
        swapped = restore_concepts(agent.concepts.snapshot(), agent.clock)
        a = swapped.banks[first].weights.clone()
        swapped.banks[first].weights.copy_(swapped.banks[second].weights)
        swapped.banks[second].weights.copy_(a)
        swapped_results = evaluate(swapped, teacher, probes)
        composed = agent.concepts.hypothesize([first, second], [.3, -.7], agent.clock)
        verification = agent.concepts.verify(composed["id"], teacher.expected([first, second], [.3, -.7]),
                                            "reserved-composition-test", agent.clock)
        untested = agent.concepts.hypothesize([second, first], [-.2, .6], agent.clock)
        # A later correct lesson changes the premise version; old conclusions
        # are not silently presented as conclusions from the new weights.
        teach(first, [.2, -.3])
        invalidated = agent.concepts.hypotheses[composed["id"]]["status"] == "superseded"
        assert agent.concepts.hypotheses[untested["id"]]["status"] == "superseded"
        agent.request_study([{"concept": first, "input": [.4, -.9], "cost": 0.},
                             {"concept": "not-taught", "input": [0., 1.], "cost": 0.}])
        probe = {"chain": [first, second], "input": [.31, -.73]}
        atomic_json(output / "probe.json", probe)
        save(output / "final.pt", agent)
        process = subprocess.run([sys.executable, "-m", "scripts.alice_memory.conceptual_experiment", "--resume",
                                  str(output / "final.pt"), "--probe", str(output / "probe.json"),
                                  "--output", str(output / "resumed.json")], capture_output=True, text=True, timeout=60)
        if process.returncode:
            raise RuntimeError("Conceptual fresh-process check failed: " + process.stderr[-2048:])
        resumed = json.loads((output / "resumed.json").read_text(encoding="utf-8"))
        prediction = agent.concepts.compose(probe["chain"], probe["input"])
        tick = agent.tick(.1)
        exact = (resumed["prediction"] == prediction and resumed["inquiry"] == tick["concept_inquiry"]
                 and resumed["hidden"] == agent.temporal.hidden.tolist() and resumed["clock"] == agent.clock
                 and resumed["single_episode_owner"])
        counts = {name: sum(item["correct"] for item in result) for name, result in
                  (("before", before), ("after", after), ("fixed_queries", fixed), ("erased_weights", erased_results), ("swapped_weights", swapped_results))}
        source_intact = all(torch.equal(value, source_digest(memory.blocks[i])) for i, value in enumerate(original))
        report.update(counts=counts, total_probes=len(probes), probes=after, inquiry_trace=active_queries,
                      external_lessons=agent.concepts.lessons, hypotheses_invalidated=invalidated,
                      composition_verification=verification, fresh_process_exact=exact,
                      old_episode_banks_intact=len(original) if source_intact else 0,
                      observation_count_unchanged=observed == agent.temporal.observations,
                      accepted=counts["before"] == 0 and counts["after"] == len(probes)
                      and counts["fixed_queries"] < counts["after"] and counts["erased_weights"] < 4
                      and counts["swapped_weights"] < 4 and source_intact and observed == agent.temporal.observations
                      and exact and invalidated and verification["status"] == "verified_example")
        atomic_json(output / "report.json", report)
        return report
    finally:
        close_agent(agent, mind)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()
    torch.set_num_threads(1)
    if args.resume:
        if args.probe is None or args.output.exists():
            parser.error("Resume requires a probe and a new result file.")
        child(args.resume, args.probe, args.output)
        return
    if args.checkpoint is None:
        parser.error("An existing grounded/language checkpoint is required.")
    result = run(args.checkpoint, args.output, args.seed)
    print(json.dumps({key: result[key] for key in ("accepted", "seed", "counts", "fresh_process_exact", "old_episode_banks_intact")}))
    if not result["accepted"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
