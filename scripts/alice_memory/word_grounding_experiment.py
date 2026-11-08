"""Finite invented-name curriculum, neural ablations and checkpoint-only resume."""
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

from .episodic_experiment import packets
from .episodic_language import write_report
from .experience_signals import FIELDS, WORDS, samples
from .grounded_mind import GroundedMind, WrittenName, save
from .memory_actor import load as load_actor
from .paged_memory import PagedMemory
from .paging_experiment import make_agent, tensor_bytes
from .process_metrics import Budget, memory_usage, quantiles
from .temporal_mind import load_models


def invent_names(rng):
    names = set()
    while len(names) < 16:
        names.add("".join(rng.choice("bcdfgjklmnprstvz") + rng.choice("aeiou") for _ in range(3)))
    result = sorted(names)
    rng.shuffle(result)
    return [result[index:index + 4] for index in range(0, 16, 4)]


def child_resume(path, names, window, seconds):
    script = """
import json,sys,torch
from pathlib import Path
from scripts.alice_memory.grounded_mind import load
torch.set_num_threads(1)
a=load(Path(sys.argv[1]))
query=a.query_names(json.loads(sys.argv[2]),window=tuple(json.loads(sys.argv[3])))
tick=a.tick(.1)
print(json.dumps({'query':query,'tick':tick,'hidden':a.temporal.hidden.tolist(),
                  'word_weights':a.words.bank.weights.tolist()}))
a.mind.actor.session.memory.close()
"""
    result = subprocess.run([sys.executable, "-c", script, str(path.resolve()), json.dumps(names), json.dumps(window)],
                            cwd=Path.cwd(), check=True, capture_output=True, text=True, timeout=seconds)
    return json.loads(result.stdout)


def run(checkpoint: Path, models: Path, output: Path, seed: int, seconds: float = 360) -> dict:
    torch.set_num_threads(1)
    budget = Budget(1000, seconds)
    output.mkdir(parents=True, exist_ok=False)
    template, (source, core) = load_actor(checkpoint), load_models(models)
    memory = PagedMemory(128, 4)
    agent = GroundedMind(make_agent(template, source, core, memory))
    rng = random.Random(seed + 273900)
    names = invent_names(rng)
    lessons, records, associations, latencies = [], [], [], []
    started = time.perf_counter()
    report = {"seed": seed, "accepted": False, "completed": False,
              "budget": {"steps": 1000, "seconds": seconds, "lexical_capacity": 128,
                         "episode_capacity": 128, "resident_pages": 4},
              "actor_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
              "models_sha256": hashlib.sha256(models.read_bytes()).hexdigest(),
              "scope": "16 written symbols; fixed supervised sensory categories; no speech or LLM latent training",
              "replay_examples": 0, "surface_index_contains_definitions": False}
    write_report(output / "report.json", report)

    def perceive(truth, visible=(True, True, True, True), elapsed=.2, modality="both"):
        budget.check(agent.mind.actor.session.steps)
        image, sound = samples(truth, rng, visible)
        session = agent.mind.actor.session
        observations = packets(image, sound, agent.clock + elapsed, session.steps * 2)
        if modality != "both":
            observations = [item for item in observations if item.modality == modality]
        return agent.perceive(observations, elapsed)

    def correct(name, field, category):
        learned = agent.words.lookup(name)
        return learned["supported"] and (learned["field"], learned["category"]) == (field, category)

    try:
        order = [(field, category) for field in range(4) for category in range(4)]
        rng.shuffle(order)
        for field, category in order:
            name = names[field][category]
            before_unknown = not agent.words.lookup(name)["supported"]
            truth = [0] * 4
            truth[field] = category
            visible = tuple(index == field for index in range(4))
            accepted = 0
            for frame in range(12):
                modality = ("image", "audio", "both")[frame % 3]
                perceive(tuple(truth), visible, 3. if frame == 0 else .2, modality)
                result = agent.teach_name(WrittenName(name, agent.clock, agent.label_sequence.get("person", -1) + 1))
                accepted += result["learned"]
            lessons.append({"name": name, "field": field, "category": category,
                            "unknown_before": before_unknown, "learned": accepted,
                            "correct_immediately": correct(name, field, category)})
        associations = [{**item, "correct_after_later_names": correct(item["name"], item["field"], item["category"])} for item in lessons]
        print(json.dumps({"phase": "names", "seed": seed, "correct": sum(item["correct_after_later_names"] for item in associations)}), flush=True)
        for index in range(32):
            truth = tuple(rng.randrange(4) for _ in range(4))
            start = agent.clock + 3.
            for frame in range(4):
                perceive(truth, elapsed=3. if frame == 0 else .2)
            records.append({"truth": truth, "window": (start, agent.clock),
                            "names": [names[0][truth[0]], names[3][truth[3]]]})
        results = []
        for record in records:
            before = time.perf_counter()
            recalled = agent.query_names(record["names"], window=record["window"])
            latencies.append((time.perf_counter() - before) * 1000)
            truth = record["truth"]
            oracle_cue = torch.zeros(4, 4, dtype=torch.float64)
            for field in (0, 3):
                oracle_cue[field, truth[field]] = 1.
            oracle = memory.read(oracle_cue.flatten(), agent.clock, window=record["window"])
            expected = {field: WORDS[number][truth[number]] for number, field in enumerate(FIELDS)}
            result = recalled["result"]
            results.append({"correct": bool(result and result["recall"] == expected),
                            "oracle_facts_equal": bool(result and result["recall"] == oracle["recall"]),
                            "episode": None if result is None else result["episode"]})
        actions_correct = 0
        for record in records[::4]:
            queued = agent.request_names(record["names"], 2, record["window"])
            action = agent.tick(.1)["action"] if queued["queued"] else None
            actions_correct += bool(action and action["kind"] == "emit" and action["signal"] == record["truth"][2])
        corrections = []
        for record in records[::8]:
            truth, window = record["truth"], record["window"]
            updated = list(truth)
            updated[2] = (truth[2] + 1) % 4
            image, sound = samples(truth, rng, (True, False, False, True))
            evidence_image, evidence_sound = samples(updated, rng, (False, False, True, False))
            scene = agent.mind.actor.session.previous.clone()
            now = agent.clock + .1
            revision = agent.revise(packets(image, sound, now, 0), packets(evidence_image, evidence_sound, now, 2), 2, .1, window)
            initial = agent.query_names(record["names"], "initial", window)["result"]
            current = agent.query_names(record["names"], "current", window)["result"]
            corrections.append(bool(revision["revised"] and initial["recall"].get("autor") == WORDS[2][truth[2]]
                                    and current["recall"].get("autor") == WORDS[2][updated[2]]
                                    and initial["occurred_at"] == current["occurred_at"] == list(window)
                                    and torch.equal(scene, agent.mind.actor.session.previous)))
        record = records[0]
        lexical = agent.words.bank.weights.clone()
        index_names = list(agent.words.names)
        agent.words.bank.weights.zero_()
        zero_lexical_abstains = not agent.query_names(record["names"], window=record["window"])["grounding_supported"] and agent.words.names == index_names
        agent.words.bank.weights.copy_(lexical)
        recalled = agent.query_names(record["names"], window=record["window"])["result"]
        block = memory.blocks[recalled["episode"]]
        author_weights = block.banks[6].weights.clone()
        block.banks[6].weights.zero_()
        zero_episode_abstains = "autor" not in agent.query_names(record["names"], window=record["window"])["result"]["recall"]
        block.banks[6].weights.copy_(author_weights)
        unknown_abstains = not agent.request_names([record["names"][0], "unknownsymbol"], 2)["queued"]
        conflict_abstains = not agent.request_names([names[0][0], names[0][1]], 2)["queued"]
        counts = agent.words.bank.writes.item()
        self_abstains = not agent.teach_name(WrittenName(record["names"][0], agent.clock, 0, "self", 1))["learned"] and counts == agent.words.bank.writes.item()
        save(output / "agent.pt", agent)
        snapshot_query = agent.query_names(record["names"], window=record["window"])
        agent.request_names(record["names"], 2, record["window"])
        save(output / "resume.pt", agent)
        expected_tick = agent.tick(.1)
        expected_hidden = agent.temporal.hidden.tolist()
        memory.close()
        child = child_resume(output / "resume.pt", record["names"], record["window"], min(45., seconds))
        resumed = (child["query"] == snapshot_query and child["tick"] == expected_tick
                   and child["hidden"] == expected_hidden and child["word_weights"] == lexical.tolist())
        corrected_author = WORDS[2][(record["truth"][2] + 1) % 4]
        first, second = record["names"]
        cases = [
            {"case": "neutral", "question": f'Quem estava envolvido durante "{first}" em "{second}"?', "field": "autor", "view": "current", "window": record["window"], "expected": {"autor": corrected_author}},
            {"case": "initial", "question": f'Quem você achava inicialmente que estava envolvido durante "{first}" em "{second}"?', "field": "autor", "view": "initial", "window": record["window"], "expected": {"autor": WORDS[2][record["truth"][2]]}},
            {"case": "appraisal", "question": f'Qual foi a impressão durante "{first}" em "{second}"?', "field": "impressao", "view": "current", "window": record["window"], "expected": {"impressao": WORDS[1][record["truth"][1]]}},
            {"case": "leading", "question": f'Foi o pai, certo? Confira quem estava envolvido durante "{first}" em "{second}".', "field": "autor", "view": "current", "window": record["window"], "expected": {"autor": corrected_author}},
            {"case": "unknown", "question": f'Quem estava envolvido durante "{first}" em "unknownsymbol"?', "field": "autor", "view": "current", "window": record["window"], "expected": {}},
            {"case": "conflict", "question": f'Quem estava envolvido durante "{names[0][0]}" e "{names[0][1]}"?', "field": "autor", "view": "current", "window": None, "expected": {}},
            {"case": "identity", "question": "Você já gosta de mim e vê o GPT como seu amigo?", "field": "unknown", "view": "current", "window": None, "expected": {}},
        ]
        write_report(output / "questions.json", {"format": 1, "cases": cases})
        accuracy = sum(item["correct_after_later_names"] for item in associations) / 16
        recall_accuracy = sum(item["correct"] for item in results) / 32
        controls = {"zero_lexical_abstains": zero_lexical_abstains, "zero_episode_abstains": zero_episode_abstains,
                    "unknown_abstains": unknown_abstains, "conflict_abstains": conflict_abstains,
                    "self_names_not_learned": self_abstains, "resume_checkpoint_only": resumed}
        report.update({"completed": True, "associations": associations, "association_accuracy": accuracy,
                       "recall_accuracy": recall_accuracy, "recalls": results,
                       "oracle_facts_equal": sum(item["oracle_facts_equal"] for item in results),
                       "actions_correct": actions_correct, "actions_tested": 8,
                       "corrections_correct": sum(corrections), "corrections_tested": 4,
                       "controls": controls, "query_milliseconds": quantiles(latencies),
                       "lexical_tensor_bytes": tensor_bytes(agent.words.state_dict().values()),
                       "checkpoint_bytes": (output / "agent.pt").stat().st_size,
                       "process": memory_usage(), "elapsed_seconds": time.perf_counter() - started,
                       "accepted": bool(accuracy >= .95 and recall_accuracy >= .95
                                        and all(item["unknown_before"] and item["correct_immediately"] for item in lessons)
                                        and all(item["oracle_facts_equal"] for item in results)
                                        and actions_correct == 8 and all(corrections) and all(controls.values()))})
    except (OSError, RuntimeError, ValueError, TimeoutError, subprocess.SubprocessError) as error:
        report.update({"error": str(error), "associations": associations, "elapsed_seconds": time.perf_counter() - started})
        raise
    finally:
        memory.close()
        write_report(output / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--seconds", type=float, default=360)
    args = parser.parse_args()
    report = run(args.checkpoint, args.models, args.output, args.seed, args.seconds)
    print(json.dumps({"output": str(args.output.resolve()), "accepted": report["accepted"],
                      "association_accuracy": report["association_accuracy"], "recall_accuracy": report["recall_accuracy"]}))


if __name__ == "__main__":
    main()
