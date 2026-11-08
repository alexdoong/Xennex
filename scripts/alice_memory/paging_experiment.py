"""Finite capacity evaluation: learned neural pages, exact routing and resume."""
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

from .consolidating_mind import ConsolidatingMind, save
from .continuous_mind import ContinuousMind
from .episodic_experiment import packets
from .episodic_memory import EpisodicMemory
from .episodic_session import EpisodicSession
from .experience_perception import semantic
from .experience_signals import FIELDS, WORDS, samples
from .importance import Consequence
from .memory_actor import MemoryActor, load as load_actor
from .paged_memory import PagedMemory
from .process_metrics import Budget, memory_usage, quantiles
from .temporal_mind import TemporalMind, load_models


def tensor_bytes(values) -> int:
    return sum(value.numel() * value.element_size() for value in values)


def make_agent(template, source, core, memory):
    session = EpisodicSession(template.session.perception, template.session.boundary, memory)
    return ConsolidatingMind(TemporalMind(ContinuousMind(MemoryActor(session, template.policy)), core, source),
                             forgetting=1.)


def forget_residents(memory):
    """Evaluator cache control; persist learned pages before eviction."""
    for index in list(memory.cache):
        memory.persist(index)
    memory.cache.clear()


def child_resume(path: Path, timeout: float) -> dict:
    script = """
import json,sys,time,torch
from pathlib import Path
from scripts.alice_memory.consolidating_mind import load
from scripts.alice_memory.process_metrics import memory_usage
torch.set_num_threads(1)
started=time.perf_counter()
a=load(Path(sys.argv[1]))
load_seconds=time.perf_counter()-started
result=a.tick(.1)
print(json.dumps({'tick':result,'hidden':a.temporal.hidden.tolist(),'clock':a.clock,
                  'semantic':a.semantic.bank.weights.tolist(),
                  'episodes':len(a.mind.actor.session.memory.blocks),
                  'resident':len(a.mind.actor.session.memory.cache),
                  'load_seconds':load_seconds,'memory':memory_usage()}))
a.mind.actor.session.memory.close()
"""
    result = subprocess.run([sys.executable, "-c", script, str(path.resolve())], cwd=Path.cwd(),
                            capture_output=True, text=True, check=True, timeout=timeout)
    return json.loads(result.stdout)


def run(checkpoint: Path, models: Path, output: Path, seed: int, seconds: float = 300) -> dict:
    torch.set_num_threads(1)
    budget = Budget(10000, seconds)
    template, (source, core) = load_actor(checkpoint), load_models(models)
    output.mkdir(parents=True, exist_ok=False)
    memory = PagedMemory(512, 4)
    agent = make_agent(template, source, core, memory)
    reference = make_agent(template, source, core, EpisodicMemory(128))
    rng = random.Random(seed + 253000)
    records, max_resident = [], 0
    write_latencies = []
    started = time.perf_counter()
    try:
        for index in range(512):
            truth = tuple(rng.randrange(4) for _ in range(4))
            start = agent.clock + 3.
            for frame in range(4):
                budget.check(agent.mind.actor.session.steps)
                image, sound = samples(truth, rng)
                elapsed = 3. if frame == 0 else .2
                session = agent.mind.actor.session
                before = time.perf_counter()
                agent.perceive(packets(image, sound, agent.clock + elapsed, session.steps * 2), elapsed)
                write_latencies.append((time.perf_counter() - before) * 1000)
                max_resident = max(max_resident, len(memory.cache))
                if index < 128:
                    ref_session = reference.mind.actor.session
                    reference.perceive(packets(image, sound, reference.clock + elapsed, ref_session.steps * 2), elapsed)
            records.append((truth, (start, agent.clock)))
            if (index + 1) % 128 == 0:
                print(json.dumps({"phase": "stream", "episodes": len(memory.blocks),
                                  "resident": len(memory.cache)}), flush=True)
        agent.consolidate_current()
        reference.consolidate_current()
        stream_seconds = time.perf_counter() - started
        session = agent.mind.actor.session
        query_rng = random.Random(seed + 263000)
        correct, reference_equal, decisions_equal, max_error = 0, 0, 0, 0.
        cold_latency, warm_latency = [], []
        for index, (truth, window) in enumerate(records):
            budget.check(session.steps)
            image, sound = samples(truth, query_rng, (True, True, False, True))
            cues = packets(image, sound, agent.clock, 0)
            forget_residents(memory)
            before = time.perf_counter()
            recalled = session.query(cues, window=window)
            cold_latency.append((time.perf_counter() - before) * 1000)
            before = time.perf_counter()
            repeated = session.query(cues, window=window)
            warm_latency.append((time.perf_counter() - before) * 1000)
            expected = {field: WORDS[number][truth[number]] for number, field in enumerate(FIELDS)}
            correct += recalled["recall"] == expected and recalled == repeated
            max_resident = max(max_resident, len(memory.cache))
            if index < 128:
                ref = reference.mind.actor.session.query(packets(image, sound, reference.clock, 0), window=window)
                error = (torch.tensor(recalled["distributions"], dtype=torch.float64)
                         - torch.tensor(ref["distributions"], dtype=torch.float64)).abs().max().item()
                max_error = max(max_error, error)
                # The address count differs intentionally (512 vs 128).
                reference_equal += all(recalled[key] == ref[key] for key in recalled if key != "addresses_compared")
                if index % 8 == 0:
                    action = agent.mind.actor.respond(cues, 2, window=window)["action"]
                    ref_action = reference.mind.actor.respond(packets(image, sound, reference.clock, 0),
                                                             2, window=window)["action"]
                    decisions_equal += (action["kind"], action["signal"]) == (ref_action["kind"], ref_action["signal"])
        revisions_correct = 0
        current_scene = session.previous.clone()
        query_rng = random.Random(seed + 273000)
        for index in range(0, 128, 8):
            budget.check(session.steps)
            truth, window = records[index]
            corrected = list(truth)
            corrected[2] = (truth[2] + 1) % 4
            cue_image, cue_sound = samples(truth, query_rng, (True, True, False, True))
            evidence_image, evidence_sound = samples(corrected, query_rng, (False, False, True, False))
            forget_residents(memory)
            now = agent.clock + .1
            result = agent.revise(packets(cue_image, cue_sound, now, 0),
                                  packets(evidence_image, evidence_sound, now, 2), 2, .1, window)
            cues = packets(cue_image, cue_sound, agent.clock, 0)
            initial, current = session.query(cues, "initial", window), session.query(cues, "current", window)
            revisions_correct += (result["revised"] and initial["recall"]["autor"] == WORDS[2][truth[2]]
                                  and current["recall"]["autor"] == WORDS[2][corrected[2]]
                                  and initial["occurred_at"] == list(window) == current["occurred_at"]
                                  and initial["learned_at"][2] < current["learned_at"][2]
                                  and torch.equal(current_scene, session.previous))
            max_resident = max(max_resident, len(memory.cache))
        truth, window = records[0]
        image, sound = samples(truth, query_rng, (True, False, False, True))
        cues = packets(image, sound, agent.clock, 0)
        ambiguous = session.query(cues)
        agent.request(cues, 2, window)
        response = agent.tick(.1)
        action = response["action"]
        credit = agent.consequences([Consequence(action["sequence"], agent.clock + .1, 1., 1., 0.)], .1)
        cue, _ = semantic(session.interpret(packets(image, sound, agent.clock, 0))[0])
        loads_before = memory.loads
        ranked = agent.mind.importance.rank(memory, cue, 2, agent.clock)
        old_value_routing = bool(ranked) and ranked[0]["episode"] == 0 and memory.loads == loads_before
        resident_bytes = tensor_bytes(value for block in memory.cache.values() for value in block.state_dict().values())
        pool_bytes = tensor_bytes(memory.pool.values())
        importance_bytes = tensor_bytes(agent.mind.importance.state_dict().values())
        for index in list(memory.cache):
            memory.persist(index)
        disk_bytes = memory.path.stat().st_size
        source_path = memory.path
        before = time.perf_counter()
        save(output / "agent.pt", agent)
        save_seconds = time.perf_counter() - before
        expected_tick = agent.tick(.1)
        expected_hidden = agent.temporal.hidden.tolist()
        expected_semantic = agent.semantic.bank.weights.tolist()
        memory.close()
        resumed = child_resume(output / "agent.pt", min(60., seconds))
        resume_equal = (resumed["tick"] == expected_tick and resumed["hidden"] == expected_hidden
                        and resumed["semantic"] == expected_semantic and resumed["clock"] == agent.clock
                        and not source_path.exists() and resumed["episodes"] == 512 and resumed["resident"] <= 4)
        accepted = (len(memory.blocks) == 512 and correct / 512 >= .99 and reference_equal == 128
                    and max_error <= 1e-8 and decisions_equal == 16 and revisions_correct == 16
                    and max_resident <= 4 and ambiguous["ambiguous"] and ambiguous["recall"] is None
                    and response["recall"]["episode"] == 0 and credit["accepted"] == 1
                    and old_value_routing and resume_equal)
        report = {"format": 28, "seed": seed, "world_seed": seed + 253000, "accepted": accepted,
                  "episodes": len(memory.blocks), "session_steps": session.steps,
                  "external_observations": agent.temporal.observations, "stream_seconds": stream_seconds,
                  "all_fields_accuracy": correct / 512, "resident_reference_equal": reference_equal,
                  "reference_count": 128, "maximum_probability_error": max_error,
                  "policy_decisions_equal": decisions_equal, "policy_decisions_count": 16,
                  "cold_revisions_correct": revisions_correct, "cold_revisions_count": 16,
                  "ambiguous_abstention": ambiguous["ambiguous"] and ambiguous["recall"] is None,
                  "old_valuable_episode_selected_without_page_reads": old_value_routing,
                  "old_episode_answered_by_pending_task": response["recall"]["episode"] == 0,
                  "consequences_accepted": credit["accepted"],
                  "max_resident_episodes": max_resident, "hot_limit": 4,
                  "page_loads": memory.loads, "page_hits": memory.hits, "page_evictions": memory.evictions,
                  "latency_ms": {"paired_observation": quantiles(write_latencies),
                                 "cold_query": quantiles(cold_latency), "warm_query": quantiles(warm_latency)},
                  "tensor_bytes": {"resident_neural_pages": resident_bytes, "resident_route_index": pool_bytes,
                                   "importance": importance_bytes,
                                   "full_pages_if_resident": 512 * tensor_bytes(memory.cache[next(iter(memory.cache))].state_dict().values()),
                                   "semantic": tensor_bytes(agent.semantic.state_dict().values())},
                  "disk_bytes": disk_bytes, "checkpoint_bytes": (output / "agent.pt").stat().st_size,
                  "save_seconds": save_seconds, "fresh_process_load_seconds": resumed["load_seconds"],
                  "next_tick_equal_fresh_process_without_original_archive": resume_equal,
                  "fresh_process_memory": resumed["memory"], "evaluator_memory": memory_usage(),
                  "semantic_writes": int(agent.semantic.bank.writes),
                  "source_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                  "models_sha256": hashlib.sha256(models.read_bytes()).hexdigest(),
                  "scope": "512 supervised synthetic four-frame episodes; exact indexed windows supplied by evaluator; raw reserved cues; no live senses, ANN, forgetting, history replay or claim of total constant RAM"}
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report
    finally:
        memory.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--models", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--max-seconds", type=float, default=300)
    args = parser.parse_args()
    report = run(args.checkpoint, args.models, args.output, args.seed, args.max_seconds)
    print(json.dumps({"output": str(args.output.resolve()), "accepted": report["accepted"],
                      "accuracy": report["all_fields_accuracy"], "max_resident": report["max_resident_episodes"],
                      "resume_equal": report["next_tick_equal_fresh_process_without_original_archive"]}))
    raise SystemExit(0 if report["accepted"] else 2)


if __name__ == "__main__":
    main()
