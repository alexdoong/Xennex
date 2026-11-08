"""Ordered synthetic experiences update neural memory during language generation.

    The sensory simulation advances faster than wall time. This is not a
    real-time benchmark or an evaluation of a pretrained language model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from pathlib import Path

import torch

from .episodic_experiment import packets
from .adaptive_memory_experiment import make_queries
from .episodic_language import write_report
from .expectation_experiment import NAMES
from .expectation_loop_experiment import source_stream
from .experience_signals import samples, WORDS
from .grounded_mind import load as load_mind
from .language_loop_experiment import resume_child
from .language_process import LanguageProcess
from .neural_language import NeuralLanguageCoordinator, load, save
from .neural_task_experiment import load_model
from .process_metrics import Budget, memory_usage
from .reactivation_index import source_digest


def held_out(model, queries, mapping, changed):
    results = []
    for query in queries:
        key = query["key"].reshape(3, 4)
        cue = torch.zeros(4, 4, dtype=torch.float64)
        cue[[0, 1, 3]] = key
        activity, context = int(key[0].argmax()), query["context"]
        expected = WORDS[2][mapping[(activity + context + int(context == 1 or (changed and context == 0))) % 4]]
        predicted = model.predict(cue.flatten())
        results.append({"context": context, "supported": predicted["supported"],
                        "correct": predicted["supported"] and predicted["value"] == expected,
                        "prediction": predicted["value"], "expected": expected})
    return results


def run(checkpoint, task_model, output, seed=17, visits=64):
    if type(visits) is not int or not 8 <= visits <= 96 or visits % 8:
        raise ValueError("Use eight to ninety-six visits in complete rounds of eight.")
    torch.set_num_threads(1)
    output.mkdir(parents=True, exist_ok=False)
    report = {"accepted": False, "completed": False, "seed": seed, "visits": visits,
              "backend": "test", "accelerated_synthetic_time": True, "live_sensors": False,
              "language_quality_evaluated": False, "initial_request_answers": []}
    write_report(output / "report.json", report)
    source_hash = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    agent = load_mind(checkpoint)
    workers, coordinator = [], None
    started = time.perf_counter()
    budget = Budget(100000, 120)

    def factory(operation):
        config = output / (operation["stage"] + "-backend.json")
        config.write_text(json.dumps({"delay": 4. if operation["stage"] == "expectation" else .05}), encoding="utf-8")
        worker = LanguageProcess(operation, output / "workers", 10, "scripts.tests.alice_fake_language_worker",
                                 {"ALICE_FAKE_LANGUAGE_CONFIG": str(config.resolve())}, retain_files=True)
        workers.append(worker)
        return worker

    try:
        memory, session = agent.mind.actor.session.memory, agent.mind.actor.session
        coordinator = NeuralLanguageCoordinator(agent, load_model(task_model, agent), "http://127.0.0.1:11438",
                                                "fixture", output / "workers", factory)
        original_count = len(memory.blocks)
        original = [source_digest(block) for block in memory.blocks]
        facts_before = source_stream(agent, original_count)
        kernel_before = {name: value.clone() for name, value in agent.semantic.bank.state_dict().items()}
        lexical_before = agent.words.bank.weights.clone()
        growth = agent.expand_capacity(original_count + visits + 1)
        names = [NAMES[0][0], NAMES[3][0], NAMES[1][1]]
        question = 'Quem você esperaria durante "' + names[0] + '" em "' + names[1] + '" com "' + names[2] + '"?'
        initial = agent.expect_names(names, 2)["prediction"]
        if not initial["supported"]:
            raise ValueError("Initial learned expectation is unsupported.")
        first = coordinator.submit_expectation(question)
        while coordinator.jobs[first]["status"] != "expressing":
            budget.check(0)
            coordinator.tick(.01)
            if coordinator.jobs[first]["status"] in ("failed", "cancelled"):
                raise ValueError("Initial language operation failed.")
            time.sleep(.01)
        # The world's changed participant rule is solely in the sensory generator.
        mapping = list(range(4))
        random.Random(seed + 803000).shuffle(mapping)
        queries, encoded_queries = make_queries(session, mapping, seed + 100000)
        before_queries = held_out(agent.semantic, queries, mapping, False)
        sensory_rng = random.Random(seed + 1107000)
        schedule_rng = random.Random(seed + 1117000)
        pending = busy_frames = learned = reactivated = 0
        records, events = [], []
        for round_index in range(visits // 8):
            schedule = [(activity, appraisal, mapping[(activity + 1) % 4], 0)
                        for activity in range(4) for appraisal in (0, 2)]
            schedule_rng.shuffle(schedule)
            for truth in schedule:
                budget.check(len(records))
                before_count = len(memory.blocks)
                for frame in range(2):
                    busy_frames += int(coordinator.worker is not None and coordinator.worker.process.poll() is None)
                    elapsed = 3. if frame == 0 else .1
                    image, audio = samples(truth, sensory_rng)
                    response = coordinator.perceive(packets(image, audio, agent.clock + elapsed, session.steps * 2), elapsed)
                    events.extend(response["language_events"])
                    pending += int(not agent.expect_names(names, 2)["prediction"]["supported"])
                if len(memory.blocks) != before_count + 1:
                    raise ValueError("Each ordered visit must create exactly one new episode.")
                result = agent.consolidate_current()
                learned += int(result["learned"])
                reactivated += len(result.get("reactivated", []))
                records.append({"episode": len(memory.blocks) - 1, "truth": truth})
                if first in coordinator.jobs:
                    answer = coordinator.take(first)
                    if answer is not None:
                        report["initial_request_answers"].append(answer)
        prediction = agent.expect_names(names, 2)["prediction"]
        expected = WORDS[2][mapping[1]]
        final_id = coordinator.submit_expectation(question)
        save(output / "pending.pt", coordinator)
        final_answer = None
        while final_answer is None or first in coordinator.jobs:
            budget.check(len(records))
            response = coordinator.tick(.05)
            events.extend(response["language_events"])
            if first in coordinator.jobs:
                answer = coordinator.take(first)
                if answer is not None:
                    report["initial_request_answers"].append(answer)
            if final_answer is None:
                final_answer = coordinator.take(final_id)
            time.sleep(.01)
        save(output / "final.pt", coordinator)
        source_intact = all(torch.equal(digest, source_digest(memory.blocks[i])) for i, digest in enumerate(original))
        new_facts = 0
        for item in records:
            episode = item["episode"]
            cue = memory.blocks[episode].addresses[1].clone()
            cue[2].zero_()
            trace = memory.traces[episode]
            recalled = memory.read(cue.flatten(), agent.clock, window=(trace.started, trace.ended))
            new_facts += int(recalled["recall"]["autor"] == WORDS[2][item["truth"][2]])
        changed = any(not torch.equal(value, agent.semantic.bank.state_dict()[name]) for name, value in kernel_before.items())
        current_sources = agent.semantic.pending_sources()
        after_queries = held_out(agent.semantic, queries, mapping, True)
        coordinator.close()
        memory.close()
        resumed = load(output / "pending.pt", output / "control", factory)
        try:
            expected_tick = resumed.agent.tick(.1)
            expected_hidden = resumed.temporal.hidden.tolist()
            resumed_prediction = resumed.agent.expect_names(names, 2)["prediction"]
        finally:
            resumed.close()
            resumed.agent.mind.actor.session.memory.close()
        child = resume_child(output / "pending.pt", output)
        write_report(output / "resumed.json", child)
        report.update(growth=growth, frames=visits * 2, frames_during_live_worker=busy_frames,
                      unsupported_captures_during_pending_learning=pending, learned_sources=learned,
                      reactivated_sources=reactivated, new_facts_correct=new_facts, old_source_banks_intact=source_intact,
                      old_facts_preserved=source_stream_from_checkpoint(output / "final.pt", output / "fact-audit", original_count) == facts_before,
                      semantic_weights_changed=changed, lexical_weights_unchanged=torch.equal(lexical_before, agent.words.bank.weights),
                      initial_prediction=initial, final_prediction=prediction, evaluator_expected=expected,
                      final_answer=final_answer, pending_sources=current_sources, events=events,
                      initial_request_completed_current=len(report["initial_request_answers"]) == 1
                          and report["initial_request_answers"][0]["status"] == "completed"
                          and report["initial_request_answers"][0]["proposal"]["expectations"] == {"autor": expected}
                          and not report["initial_request_answers"][0]["proposal"]["factual_claims"],
                      held_out_encoded=encoded_queries, held_out_before=before_queries, held_out_after=after_queries,
                      new_rule_held_out_correct=sum(item["correct"] for item in after_queries if item["context"] == 0),
                      unchanged_rules_held_out_correct=sum(item["correct"] for item in after_queries if item["context"] != 0),
                      fresh_process_first_tick_equal=child["first_tick"] == expected_tick and child["hidden"] == expected_hidden,
                      fresh_process_expectation_correct=child["answer"]["status"] == "completed"
                          and child["answer"]["proposal"]["expectations"] == {"autor": expected}
                          and not child["answer"]["proposal"]["factual_claims"],
                      restored_prediction_equal=resumed_prediction == prediction,
                      source_file_unchanged=hashlib.sha256(checkpoint.read_bytes()).hexdigest() == source_hash,
                      workers_terminal=all(worker.process.poll() is not None for worker in workers),
                      wall_seconds=time.perf_counter() - started, resources=memory_usage(), completed=True)
        report["accepted"] = bool(source_intact and report["old_facts_preserved"] and changed and new_facts == visits
                                  and learned == visits and busy_frames > 0 and pending > 0 and not current_sources
                                  and encoded_queries == 32 and report["new_rule_held_out_correct"] == 8
                                  and report["unchanged_rules_held_out_correct"] == 24
                                  and prediction["supported"] and prediction["value"] == expected
                                  and final_answer["status"] == "completed" and final_answer["proposal"]["expectations"] == {"autor": expected}
                                  and report["fresh_process_first_tick_equal"] and report["restored_prediction_equal"]
                                  and report["fresh_process_expectation_correct"]
                                  and report["initial_request_completed_current"]
                                  and report["lexical_weights_unchanged"] and report["source_file_unchanged"] and report["workers_terminal"])
        write_report(output / "report.json", report)
        return report
    except (Exception, KeyboardInterrupt) as error:
        report["error"] = type(error).__name__ + ": " + str(error)[:2048]
        write_report(output / "report.json", report)
        raise
    finally:
        if coordinator is not None:
            coordinator.close()
        agent.mind.actor.session.memory.close()


def source_stream_from_checkpoint(path, folder, count):
    restored = load(path, folder)
    try:
        return source_stream(restored.agent, count)
    finally:
        restored.close()
        restored.agent.mind.actor.session.memory.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--task-model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--visits", type=int, default=64)
    args = parser.parse_args()
    report = run(args.checkpoint, args.task_model, args.output, args.seed, args.visits)
    print(json.dumps({key: report[key] for key in ("accepted", "learned_sources", "new_facts_correct", "final_prediction", "wall_seconds")}))
    raise SystemExit(0 if report["accepted"] else 1)


if __name__ == "__main__":
    main()
