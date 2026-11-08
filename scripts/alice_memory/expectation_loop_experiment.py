"""Finite shared neural mind with recall and expectations in asynchronous workers."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from pathlib import Path

import torch

from .adaptive_memory import recalled_pair
from .episodic_experiment import packets
from .episodic_language import write_report
from .expectation_experiment import NAMES
from .experience_signals import samples
from .grounded_mind import load as load_mind
from .language_loop_experiment import resume_child
from .language_process import LanguageProcess
from .neural_language import NeuralLanguageCoordinator, save, load
from .neural_task_experiment import load_model
from .process_metrics import Budget, memory_usage, quantiles


def source_stream(agent, count):
    result = hashlib.sha256()
    for episode in range(count):
        pair = recalled_pair(agent.mind.actor.session.memory, episode, agent.clock, agent.semantic.target)
        if pair is None:
            raise ValueError("A pre-existing source fact became unavailable.")
        result.update(json.dumps({"key": pair["key"].tolist(), "value": pair["value"].tolist()}, sort_keys=True).encode())
    return result.hexdigest()


def run(checkpoint, task_model, output, seed=17, seconds=12., backend="test", endpoint="http://127.0.0.1:11438",
        model="qwen3.5:4b", device="cpu"):
    if not 10 <= seconds <= (120 if backend == "installed" else 30) or backend not in ("test", "installed"):
        raise ValueError("Finite expectation loop requires 10–30 s for test or 10–120 s for installed language.")
    if device not in ("cpu", "gpu") or (device == "gpu" and backend != "installed"):
        raise ValueError("GPU mode requires the installed backend.")
    torch.set_num_threads(1)
    output.mkdir(parents=True, exist_ok=False)
    agent = load_mind(checkpoint)
    created = []

    def factory(operation):
        if backend == "installed":
            module = "scripts.alice_memory.language_gpu_worker" if device == "gpu" else "scripts.alice_memory.language_worker"
            worker = LanguageProcess(operation, output / "workers", 90, module, retain_files=True)
        else:
            config = output / (operation["stage"] + "-backend.json")
            config.write_text(json.dumps({"delay": 4. if operation["stage"] == "expectation" else .15}), encoding="utf-8")
            worker = LanguageProcess(operation, output / "workers", 10, "scripts.tests.alice_fake_language_worker",
                                     {"ALICE_FAKE_LANGUAGE_CONFIG": str(config.resolve())}, retain_files=True)
        created.append(worker)
        return worker

    coordinator = None
    report = {"backend": backend, "device": device, "seed": seed, "accepted": False, "completed": False,
              "live_sensors": False, "language_quality_evaluated": False,
              "free_text_verified": False, "seconds": seconds, "answers": []}
    write_report(output / "report.json", report)
    try:
        task = load_model(task_model, agent)
        coordinator = NeuralLanguageCoordinator(agent, task, endpoint, model if backend == "installed" else "fixture", output / "workers", factory)
        session, memory = agent.mind.actor.session, agent.mind.actor.session.memory
        old_count, old_observations, old_clock = len(memory.blocks), agent.temporal.observations, agent.clock
        original_stream = source_stream(agent, old_count)
        semantic_before = agent.semantic.transaction_state()
        lexical_before = agent.words.bank.weights.clone()
        question = 'Quem você esperaria durante "' + NAMES[0][0] + '" em "' + NAMES[3][0] + '" com "' + NAMES[1][1] + '"?'
        expected = agent.expect_names([NAMES[0][0], NAMES[3][0], NAMES[1][1]], 2)["prediction"]
        if not expected["supported"]:
            raise ValueError("This paired curriculum lacks a supported initial expectation.")
        # Address and timestamp select a controlled episode. Its answer comes from weights.
        candidates = [index for index, block in enumerate(memory.blocks)
                      if block.addresses[1, 0].argmax().item() == 0 and block.addresses[1, 3].argmax().item() == 0]
        trace = memory.traces[candidates[0]]
        window = (trace.started, trace.ended)
        factual_question = 'Quem estava durante "' + NAMES[0][0] + '" em "' + NAMES[3][0] + '"?'
        factual = agent.query_names([NAMES[0][0], NAMES[3][0]], window=window)["result"]["recall"]["autor"]
        first = coordinator.submit_expectation(question)
        factual_id, second, saved = None, None, False
        frames = busy_ticks = 0
        latency, lag, events = [], [], []
        rng = random.Random(seed + 1017000)
        activity = (int(session.previous[0].reshape(4, 4)[0].argmax()) + 1) % 4
        started = previous = time.perf_counter()
        budget = Budget(100000, seconds + 30)
        for step in range(int(seconds * 10)):
            deadline = started + (step + 1) * .1
            time.sleep(max(0., deadline - time.perf_counter()))
            now = time.perf_counter()
            elapsed, duration = now - previous, now - started
            previous = now
            budget.check(step)
            busy_ticks += int(coordinator.worker is not None and coordinator.worker.process.poll() is None)
            if frames < 7 and duration >= 3.5 + frames * .1:
                image, sound = samples((activity, 0, 0, 0), rng, (True, False, False, False))
                response = coordinator.perceive(packets(image, sound, agent.clock + elapsed, session.steps * 2), elapsed)
                frames += 1
            else:
                response = coordinator.tick(elapsed)
            if factual_id is None and coordinator.jobs.get(first, {}).get("status") == "expressing":
                factual_id = coordinator.submit(factual_question, window=window)
            if frames and not saved and coordinator.jobs.get(first, {}).get("status") == "expressing":
                save(output / "pending.pt", coordinator)
                saved = True
            for identifier in list(coordinator.jobs):
                answer = coordinator.take(identifier)
                if answer is not None:
                    report["answers"].append(answer)
            if report["answers"] and second is None:
                second = coordinator.submit_expectation(question.replace(NAMES[1][1], NAMES[1][3]))
            events.extend(response["language_events"])
            latency.append((time.perf_counter() - now) * 1000)
            lag.append(max(0., now - deadline) * 1000)
        save(output / "final.pt", coordinator)
        intact = original_stream == source_stream(agent, old_count)
        semantic_intact = all(torch.equal(value, agent.semantic.state_dict()[name]) for name, value in semantic_before[0].items())
        lexical_intact = torch.equal(lexical_before, agent.words.bank.weights)
        answers = report["answers"]
        expected_answers = [answer for answer in answers if answer["mode"] == "expectation" and answer["status"] == "completed"]
        factual_answers = [answer for answer in answers if answer["mode"] == "recall" and answer["status"] == "completed"]
        correct = len(expected_answers) == 2 and all(answer["proposal"]["expectations"] == {"autor": expected["value"]}
                  and not answer["proposal"]["factual_claims"] and answer["validation"] is not None for answer in expected_answers)
        correct &= len(factual_answers) == 1 and factual_answers[0]["proposal"]["claims"] == {"autor": factual}
        refreshed_validation = bool(expected_answers and expected_answers[0]["evidence"] and expected_answers[0]["validation"]["evidence"]
            and expected_answers[0]["evidence"][0]["state_sha256"] != expected_answers[0]["validation"]["evidence"][0]["state_sha256"])
        report.update(ticks=int(seconds * 10), ticks_during_live_worker=busy_ticks, frames=frames,
                      temporal_observations_added=agent.temporal.observations - old_observations,
                      clock_advanced=agent.clock - old_clock, iteration_ms=quantiles(latency), deadline_lag_ms=quantiles(lag),
                      source_facts_preserved=intact, source_facts=old_count, semantic_state_unchanged=semantic_intact,
                      lexical_weights_unchanged=lexical_intact, current_validation_after_background_perception=refreshed_validation,
                      all_expected_answers_correct=bool(correct), events=events, resources=memory_usage())
        coordinator.close()
        memory.close()
        if saved:
            control = load(output / "pending.pt", output / "control")
            try:
                expected_tick = control.agent.tick(.1)
                expected_hidden = control.temporal.hidden.tolist()
            finally:
                control.close()
                control.agent.mind.actor.session.memory.close()
            child = resume_child(output / "pending.pt", output)
            write_report(output / "resumed.json", child)
            report["fresh_process_first_tick_equal"] = child["first_tick"] == expected_tick and child["hidden"] == expected_hidden
            report["fresh_process_expectation_correct"] = child["answer"]["mode"] == "expectation" and child["answer"]["proposal"]["expectations"] == {"autor": expected["value"]}
        else:
            report.update(fresh_process_first_tick_equal=False, fresh_process_expectation_correct=False)
        report["workers_terminal"] = all(worker.process.poll() is not None for worker in created)
        report.update(completed=True, accepted=bool(correct and intact and semantic_intact and lexical_intact and frames == 7
                       and busy_ticks > 20 and saved and report["fresh_process_first_tick_equal"] and report["fresh_process_expectation_correct"]
                       and report["workers_terminal"]))
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--task-model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--seconds", type=float, default=12.)
    parser.add_argument("--backend", choices=("test", "installed"), default="test")
    parser.add_argument("--endpoint", default="http://127.0.0.1:11438")
    parser.add_argument("--model", default="qwen3.5:4b")
    parser.add_argument("--device", choices=("cpu", "gpu"), default="cpu")
    args = parser.parse_args()
    report = run(args.checkpoint, args.task_model, args.output, args.seed, args.seconds, args.backend, args.endpoint, args.model, args.device)
    print(json.dumps({key: report[key] for key in ("accepted", "ticks", "ticks_during_live_worker", "frames", "all_expected_answers_correct", "fresh_process_expectation_correct")}))
    raise SystemExit(0 if report["accepted"] else 1)


if __name__ == "__main__":
    main()
