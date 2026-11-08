"""Finite real-time perception/temporal loop beside cancellable language workers."""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from pathlib import Path

import torch

from .episodic_experiment import packets
from .episodic_language import write_report
from .experience_signals import WORDS, samples
from .grounded_language import read_questions
from .grounded_mind import load as load_mind
from .language_coordinator import LanguageCoordinator, load, save
from .language_input import references
from .language_process import LanguageProcess
from .process_metrics import memory_usage, quantiles


def resume_child(checkpoint: Path, folder: Path):
    script = """
import json,sys,time,torch
from pathlib import Path
from scripts.alice_memory.language_coordinator import load
from scripts.alice_memory.checkpoint_io import read_checkpoint
from scripts.alice_memory.language_process import LanguageProcess
torch.set_num_threads(1)
folder=Path(sys.argv[2]);config=folder/'child-backend.json'
config.write_text(json.dumps({'delay':0.}),encoding='utf-8')
factory=lambda operation: LanguageProcess(operation,folder,30,'scripts.tests.alice_fake_language_worker',{'ALICE_FAKE_LANGUAGE_CONFIG':str(config.resolve())})
checkpoint=Path(sys.argv[1])
if read_checkpoint(checkpoint,12000000).get('format')==31:
    from scripts.alice_memory.neural_language import load
a=load(checkpoint,folder,factory)
first_tick=a.agent.tick(.1);hidden=a.temporal.hidden.tolist()
try:
    for _ in range(1000):
        a.tick(.01)
        answer=a.take(1)
        if answer is not None:
            print(json.dumps({'first_tick':first_tick,'hidden':hidden,'answer':answer}));break
        time.sleep(.01)
    else: raise TimeoutError('Checkpoint-only language resume did not complete.')
finally:
    a.close();a.agent.mind.actor.session.memory.close()
"""
    result = subprocess.run([sys.executable, "-c", script, str(checkpoint.resolve()), str(folder.resolve())],
                            cwd=Path.cwd(), check=True, capture_output=True, text=True, timeout=20)
    return json.loads(result.stdout)


def run(checkpoint: Path, questions: Path, output: Path, seed=17, backend="test",
        endpoint="http://127.0.0.1:11438", model="qwen3.5:4b", seconds=30., task_model: Path | None = None,
        device="cpu") -> dict:
    maximum = 120 if backend == "installed" else 40
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 10 <= seconds <= maximum or backend not in ("test", "installed"):
        raise ValueError("Loop requires 10–40 s for test or 10–120 s for an installed backend.")
    if device not in ("cpu", "gpu") or (device == "gpu" and backend != "installed"):
        raise ValueError("GPU mode requires the installed backend.")
    torch.set_num_threads(1)
    case = read_questions(questions)[0]
    output.mkdir(parents=True, exist_ok=False)
    agent = load_mind(checkpoint)
    config = output / "backend.json"
    config.write_text(json.dumps({"delay": 1.5}), encoding="utf-8")
    created = []

    def factory(operation):
        module = "scripts.alice_memory.language_gpu_worker" if device == "gpu" else "scripts.alice_memory.language_worker"
        worker = (LanguageProcess(operation, output / "workers", 90, module, retain_files=True) if backend == "installed" else
                  LanguageProcess(operation, output / "workers", 30, "scripts.tests.alice_fake_language_worker",
                                  {"ALICE_FAKE_LANGUAGE_CONFIG": str(config.resolve())}, retain_files=True))
        created.append(worker)
        return worker

    save_agent, load_agent = save, load
    if task_model is None:
        coordinator = LanguageCoordinator(agent, endpoint, model if backend == "installed" else "fixture", output / "workers", factory)
    else:
        from .neural_task_experiment import load_model
        from .neural_language import NeuralLanguageCoordinator, save as save_agent, load as load_agent
        cognitive = load_model(task_model, agent)
        coordinator = NeuralLanguageCoordinator(agent, cognitive, endpoint, model if backend == "installed" else "fixture", output / "workers", factory)
    names, window = references(case["question"]), tuple(case["window"])
    original = agent.query_names(names, window=window)["result"]["recall"]["autor"]
    initial_author = agent.query_names(names, "initial", window)["result"]["recall"]["autor"]
    corrected = (WORDS[2].index(original) + 1) % 4
    concepts = [0, 0, 0, 0]
    for name in names:
        learned = agent.words.lookup(name)
        concepts[learned["field"]] = learned["category"]
    records, answers, latencies, lags = [], [], [], []
    session = agent.mind.actor.session
    old_episodes, old_observations = len(session.memory.blocks), agent.temporal.observations
    old_clock = agent.clock
    old_lexical = agent.words.bank.weights.clone()
    first = coordinator.submit(case["question"], window=window)
    initial_job, cancelled_job = None, None
    started, previous, cpu_started = time.perf_counter(), time.perf_counter(), time.process_time()
    rng = random.Random(seed + 283900)
    revised, checkpointed, first_revision, ticks_busy = False, False, None, 0
    frames = 0
    attended_ticks, attended_evocations = 0, 0
    task_state = None if task_model is None else {name: value.clone() for name, value in coordinator.tasks.model.state_dict().items()}
    report = {"backend": backend, "device": device, "gpu_offload_verified": False,
              "seed": seed, "accepted": False, "completed": False,
              "acceptance_scope": "continuity_and_worker_lifecycle" if backend == "installed" else "continuity_revision_and_resume_with_test_backend",
              "budget": {"seconds": seconds, "ticks": int(seconds * 10), "queue": 4, "operation_seconds_max": 120},
              "live_sensors": False, "test_backend_is_language_quality_evidence": False,
              "neural_working_tasks": task_model is not None,
              "neural_tasks_are_internal_llm_activations": False}
    write_report(output / "report.json", report)
    try:
        for step in range(int(seconds * 10)):
            deadline = started + (step + 1) * .1
            time.sleep(max(0., deadline - time.perf_counter()))
            now = time.perf_counter()
            elapsed, duration = now - previous, now - started
            previous = now
            ticks_busy += coordinator.worker is not None and coordinator.worker.process.poll() is None
            if frames < 3 and duration >= 2 + frames * 7:
                truth = tuple((int(session.previous[0].reshape(4, 4)[field].argmax()) + 1) % 4 for field in range(4))
                image, sound = samples(truth, rng)
                response = coordinator.perceive(packets(image, sound, agent.clock + elapsed, session.steps * 2), elapsed)
                frames += 1
            else:
                response = coordinator.tick(elapsed)
            attended = response.get("cognitive_attention") is not None
            attended_ticks += int(attended)
            attended_evocations += int(attended and response.get("evoked") is not None)
            job = coordinator.jobs.get(first)
            if backend == "test" and job is not None and job["status"] == "expressing" and not checkpointed:
                save_agent(output / "pending.pt", coordinator)
                checkpointed = True
            if job is not None and job["status"] == "expressing" and duration >= 2 and not revised:
                cue_image, cue_sound = samples(tuple(concepts), rng, (True, False, False, True))
                concepts[2] = corrected
                evidence_image, evidence_sound = samples(tuple(concepts), rng, (False, False, True, False))
                changed = agent.revise(packets(cue_image, cue_sound, agent.clock, 0), packets(evidence_image, evidence_sound, agent.clock, 2), 2, 0., window)
                revised = changed["revised"]
            for identifier in list(coordinator.jobs):
                answer = coordinator.take(identifier)
                if answer is not None:
                    answers.append(answer)
            if answers and initial_job is None and backend == "test":
                initial_job = coordinator.submit(case["question"], "initial", window)
            if duration >= seconds - 3 and cancelled_job is None:
                cancelled_job = coordinator.submit(case["question"], window=window)
            if cancelled_job is not None and coordinator.active_id == cancelled_job:
                coordinator.cancel(cancelled_job)
            records.extend(response["language_events"])
            latencies.append((time.perf_counter() - now) * 1000)
            lags.append(max(0., now - deadline) * 1000)
            if time.perf_counter() - started > seconds + 30:
                raise TimeoutError("Finite language loop reached its wall-clock budget.")
        save_agent(output / "mind.pt", coordinator)
        parent_cpu, wall = time.process_time() - cpu_started, time.perf_counter() - started
        coordinator.close()
        session.memory.close()
        all_stopped = all(worker.process.poll() is not None for worker in created)
        resumed = None
        if checkpointed:
            # Reference restoration belongs to evaluation, outside the timed loop.
            reference = load_agent(output / "pending.pt", output / "reference")
            first_revision = {"tick": reference.agent.tick(.1), "hidden": reference.temporal.hidden.tolist()}
            reference.close()
            reference.agent.mind.actor.session.memory.close()
            child = resume_child(output / "pending.pt", output)
            resumed = (child["first_tick"] == first_revision["tick"] and child["hidden"] == first_revision["hidden"]
                       and child["answer"]["status"] == "completed" and child["answer"]["proposal"]["claims"].get("autor") == original)
            write_report(output / "resume-report.json", child)
        responses = {item["id"]: item for item in answers}
        current_correct = first in responses and responses[first]["status"] == "completed" and responses[first]["proposal"]["claims"].get("autor") == WORDS[2][corrected]
        initial_correct = initial_job in responses and responses[initial_job]["status"] == "completed" and responses[initial_job]["proposal"]["claims"].get("autor") == initial_author
        continuity = (agent.clock - old_clock >= seconds - .1 and agent.temporal.observations == old_observations + frames
                      and len(session.memory.blocks) >= old_episodes + frames and ticks_busy > 5
                      and torch.equal(old_lexical, agent.words.bank.weights) and all_stopped
                      and abs(agent.temporal.clock - agent.clock) < 1e-8)
        task_weights_unchanged = task_state is None or all(torch.equal(value, task_state[name]) for name, value in coordinator.tasks.model.state_dict().items())
        neural_accepted = task_model is None or (attended_ticks > 0 and attended_evocations > 0 and task_weights_unchanged)
        report.update({"completed": True, "ticks": len(latencies), "ticks_with_worker_live": ticks_busy,
                       "new_perceptions": frames, "episodes_before": old_episodes, "episodes_after": len(session.memory.blocks),
                       "temporal_observations_before": old_observations, "temporal_observations_after": agent.temporal.observations,
                       "clock_advanced": agent.clock - old_clock, "revision_applied": revised,
                       "current_answer_correct": bool(current_correct), "initial_answer_correct": bool(initial_correct),
                       "resume_checkpoint_only": resumed, "lexical_weights_unchanged": torch.equal(old_lexical, agent.words.bank.weights),
                       "workers_created": len(created), "workers_all_stopped": all_stopped, "events": records,
                       "pending_jobs": coordinator.snapshot()["jobs"], "answers": answers,
                       "tick_milliseconds": quantiles(latencies), "lag_milliseconds": quantiles(lags),
                       "parent_cpu_seconds": parent_cpu, "wall_seconds": wall, "parent_single_core_fraction": parent_cpu / wall,
                       "process": memory_usage(), "continuity_accepted": bool(continuity),
                       "language_acceptance": bool(current_correct) if backend == "installed" and revised and first in responses else None,
                       "language_quality_assessed": backend == "installed" and bool(current_correct),
                       "neural_attended_ticks": attended_ticks, "neural_attended_evocations": attended_evocations,
                       "task_model_weights_unchanged": task_weights_unchanged, "neural_attention_accepted": bool(neural_accepted),
                       "accepted": bool(continuity and neural_accepted and (revised and current_correct and initial_correct and resumed if backend == "test" else True))})
    except (Exception, KeyboardInterrupt) as error:
        report["error"] = type(error).__name__ + ": " + str(error)
        raise
    finally:
        coordinator.close()
        session.memory.close()
        write_report(output / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--backend", choices=("test", "installed"), default="installed")
    parser.add_argument("--endpoint", default="http://127.0.0.1:11438")
    parser.add_argument("--model", default="qwen3.5:4b")
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--task-model", type=Path)
    parser.add_argument("--device", choices=("cpu", "gpu"), default="cpu")
    args = parser.parse_args()
    report = run(args.checkpoint, args.questions, args.output, args.seed, args.backend, args.endpoint, args.model, args.seconds, args.task_model, args.device)
    print(json.dumps({"output": str(args.output.resolve()), "accepted": report["accepted"], "continuity": report["continuity_accepted"]}))


if __name__ == "__main__":
    main()
