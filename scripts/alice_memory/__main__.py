"""Synthetic neural memory experiments. JSON output; CPU and local files only."""
from __future__ import annotations

import time

_MODULE_IMPORT_STARTED = time.perf_counter()

import argparse
import json
import sys
import wave
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import torch

from .experiment import run
from .network import describe, load_checkpoint
from .signals import load_audio, load_image
from . import online_memory, streaming, temporal, temporal_core, context_memory, context_experiment

_MODULE_IMPORT_SECONDS = time.perf_counter() - _MODULE_IMPORT_STARTED

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    episodic = commands.add_parser("episodic", help="Learn experience recognition, boundaries and directed corrections")
    episodic.add_argument("--seed", type=int, default=17)
    episodic.add_argument("--output", type=Path)
    episodic.add_argument("--max-seconds", type=float, default=300)
    episodic_query = commands.add_parser("episodic-query", help="Recall learned experiences from a partial sensory cue")
    episodic_query.add_argument("--checkpoint", type=Path, required=True)
    episodic_query.add_argument("--view", choices=("initial", "current"), default="current")
    episodic_query.add_argument("--window-start", type=float)
    episodic_query.add_argument("--window-end", type=float)
    episodic_input = episodic_query.add_mutually_exclusive_group(required=True)
    episodic_input.add_argument("--image", type=Path)
    episodic_input.add_argument("--audio", type=Path)
    memory_action = commands.add_parser("memory-action", help="Learn and evaluate actions conditioned on recalled episodes")
    memory_action.add_argument("--checkpoint", type=Path, required=True)
    memory_action.add_argument("--seed", type=int, default=17)
    memory_action.add_argument("--output", type=Path)
    memory_action.add_argument("--max-seconds", type=float, default=300)
    memory_respond = commands.add_parser("memory-respond", help="Produce an action from persisted memory and a sensory cue")
    memory_respond.add_argument("--checkpoint", type=Path, required=True)
    memory_respond.add_argument("--field", type=int, choices=range(4), required=True)
    memory_respond.add_argument("--image", type=Path, required=True)
    memory_respond.add_argument("--view", choices=("initial", "current"), default="current")
    memory_respond.add_argument("--window-start", type=float)
    memory_respond.add_argument("--window-end", type=float)
    loop = commands.add_parser("loop", help="Run a finite causal perception/action world")
    loop.add_argument("--seed", type=int, default=17)
    loop.add_argument("--steps", type=int, default=10000)
    loop.add_argument("--max-seconds", type=float, default=300)
    loop.add_argument("--checkpoint", type=Path)
    loop.add_argument("--output", type=Path)
    loop.add_argument("--realtime", action="store_true")
    predictive = commands.add_parser("predictive-loop", help="Run learned consequence prediction in the causal world")
    predictive.add_argument("--seed", type=int, default=17)
    predictive.add_argument("--steps", type=int, default=10000)
    predictive.add_argument("--max-seconds", type=float, default=300)
    predictive.add_argument("--output", type=Path)
    predictive.add_argument("--realtime", action="store_true")
    predictive_source = predictive.add_mutually_exclusive_group(required=True)
    predictive_source.add_argument("--models", type=Path)
    predictive_source.add_argument("--checkpoint", type=Path)
    predictive_train = commands.add_parser("predictive-train", help="Adapt prediction to longer causal trajectories")
    predictive_train.add_argument("--models", type=Path, required=True)
    predictive_train.add_argument("--seed", type=int, default=17)
    predictive_train.add_argument("--output", type=Path)
    predictive_train.add_argument("--max-seconds", type=float, default=300)
    crossmodal = commands.add_parser("crossmodal", help="Learn paired perception and predict focus consequences")
    crossmodal.add_argument("--seed", type=int, default=17)
    crossmodal.add_argument("--output", type=Path)
    crossmodal.add_argument("--max-seconds", type=float, default=300)
    train = commands.add_parser("run", help="Train and evaluate the synthetic experiment")
    train.add_argument("--seed", type=int, default=17)
    train.add_argument("--output", type=Path)
    stream = commands.add_parser("stream", help="Learn episodes incrementally without replay")
    stream.add_argument("--seed", type=int, default=17)
    stream.add_argument("--output", type=Path)
    time_train = commands.add_parser("time", help="Learn causal temporal continuity on synthetic signals")
    time_train.add_argument("--seed", type=int, default=17)
    time_train.add_argument("--output", type=Path)
    context_train = commands.add_parser("context", help="Test temporal memory routing and access priority")
    context_train.add_argument("--seed", type=int, default=17)
    context_train.add_argument("--output", type=Path)
    context_query = commands.add_parser("context-query", help="Recall from persisted temporal state and current input")
    context_query.add_argument("--checkpoint", required=True, type=Path)
    context_query.add_argument("--elapsed", required=True, type=float)
    context_query.add_argument("--now", required=True, type=float)
    context_inputs = context_query.add_mutually_exclusive_group(required=True)
    context_inputs.add_argument("--image", type=Path)
    context_inputs.add_argument("--audio", type=Path)
    time_query = commands.add_parser("time-query", help="Continue a persisted temporal state by one observation")
    time_query.add_argument("--checkpoint", required=True, type=Path)
    time_query.add_argument("--elapsed", required=True, type=float)
    time_inputs = time_query.add_mutually_exclusive_group(required=True)
    time_inputs.add_argument("--image", type=Path)
    time_inputs.add_argument("--audio", type=Path)
    query = commands.add_parser("query", help="Recall from weights and a PNG or WAV")
    query.add_argument("--checkpoint", required=True, type=Path)
    inputs = query.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--image", type=Path)
    inputs.add_argument("--audio", type=Path)
    stream_query = commands.add_parser("stream-query", help="Recall an episode and interpretation")
    stream_query.add_argument("--checkpoint", required=True, type=Path)
    stream_query.add_argument("--episode", required=True, type=int, choices=range(4))
    stream_query.add_argument("--view", choices=online_memory.VIEWS, default="current")
    stream_inputs = stream_query.add_mutually_exclusive_group(required=True)
    stream_inputs.add_argument("--image", type=Path)
    stream_inputs.add_argument("--audio", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "memory-action":
            from .memory_action_experiment import run as memory_action_run
            output = args.output or Path(__file__).resolve().parents[2] / "bin" / "AliceMemory" / (
                datetime.now().strftime("%Y%m%d-%H%M%S") + "-memory-action-" + uuid4().hex[:8])
            report = memory_action_run(output, args.checkpoint, args.seed, args.max_seconds)
            print(json.dumps({"output": str(output.resolve()), **report}, indent=2, ensure_ascii=False))
            return 0 if report["accepted"] else 2
        if args.command == "memory-respond":
            from .contracts import Observation
            from .memory_actor import load as load_actor
            torch.set_num_threads(2)
            actor = load_actor(args.checkpoint)
            values = load_image(args.image)[0]
            if (args.window_start is None) != (args.window_end is None):
                raise ValueError("Supply both occurrence-window endpoints or neither.")
            window = None if args.window_start is None else (args.window_start, args.window_end)
            result = actor.respond([Observation("image", values, actor.session.clock, 0)], args.field, window, args.view)
            print(json.dumps(result, ensure_ascii=False))
            return 0
        if args.command == "episodic":
            from .episodic_experiment import run as episodic_run
            output = args.output or Path(__file__).resolve().parents[2] / "bin" / "AliceMemory" / (
                datetime.now().strftime("%Y%m%d-%H%M%S") + "-episodic-" + uuid4().hex[:8])
            report = episodic_run(output, args.seed, args.max_seconds)
            print(json.dumps({"output": str(output.resolve()), **report}, indent=2, ensure_ascii=False))
            return 0 if report["accepted"] else 2
        if args.command == "episodic-query":
            from .contracts import Observation
            from .episodic_session import load as load_episodic
            from .episodic_experiment import load_pcm
            torch.set_num_threads(2)
            session = load_episodic(args.checkpoint)
            modality = "image" if args.image else "audio"
            values = load_image(args.image)[0] if args.image else load_pcm(args.audio)
            if (args.window_start is None) != (args.window_end is None):
                raise ValueError("Supply both occurrence-window endpoints or neither.")
            window = None if args.window_start is None else (args.window_start, args.window_end)
            result = session.query([Observation(modality, values, session.clock, 0, "environment")], args.view, window)
            print(json.dumps({"modality": modality, **result}, ensure_ascii=False))
            return 0
        if args.command == "predictive-train":
            from .predictive_training import run as predictive_train_run
            output = args.output or Path(__file__).resolve().parents[2] / "bin" / "AliceMemory" / (
                datetime.now().strftime("%Y%m%d-%H%M%S") + "-predictive-train-" + uuid4().hex[:8])
            report = predictive_train_run(output, args.models, args.seed, args.max_seconds)
            print(json.dumps({"output": str(output.resolve()), **report}, indent=2))
            return 0 if report["accepted"] else 2
        if args.command == "predictive-loop":
            from .predictive_loop import run as predictive_run
            output = args.output or Path(__file__).resolve().parents[2] / "bin" / "AliceMemory" / (
                datetime.now().strftime("%Y%m%d-%H%M%S") + "-predictive-loop-" + uuid4().hex[:8])
            report = predictive_run(output, args.models, args.seed, args.steps, args.max_seconds, args.checkpoint, args.realtime)
            report["module_import_seconds"] = _MODULE_IMPORT_SECONDS
            report["module_total_wall_seconds"] = time.perf_counter() - _MODULE_IMPORT_STARTED
            (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps({"output": str(output.resolve()), **report}, indent=2))
            return 0 if report["accepted"] else 2
        if args.command == "crossmodal":
            from .crossmodal import run as crossmodal_run
            output = args.output or Path(__file__).resolve().parents[2] / "bin" / "AliceMemory" / (
                datetime.now().strftime("%Y%m%d-%H%M%S") + "-crossmodal-" + uuid4().hex[:8])
            report = crossmodal_run(output, args.seed, args.max_seconds)
            print(json.dumps({"output": str(output.resolve()), **report}, indent=2))
            return 0 if report["accepted"] else 2
        if args.command == "loop":
            from .loop_experiment import run as loop_run
            output = args.output or Path(__file__).resolve().parents[2] / "bin" / "AliceMemory" / (
                datetime.now().strftime("%Y%m%d-%H%M%S") + "-loop-" + uuid4().hex[:8])
            report = loop_run(output, args.seed, args.steps, args.max_seconds, args.checkpoint, args.realtime)
            report["module_import_seconds"] = _MODULE_IMPORT_SECONDS
            report["module_total_wall_seconds"] = time.perf_counter() - _MODULE_IMPORT_STARTED
            (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps({"output": str(output.resolve()), **report}, indent=2))
            return 0 if report["accepted"] else 2
        if args.command in ("run", "stream", "time", "context"):
            output = args.output or Path(__file__).resolve().parents[2] / "bin" / "AliceMemory" / (
                datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8])
            experiment = {"run": run, "stream": streaming.run, "time": temporal.run,
                          "context": context_experiment.run}[args.command]
            report = experiment(output, args.seed)
            print(json.dumps({"output": str(output.resolve()), **report}, indent=2))
            return 0 if report["accepted"] else 2
        torch.set_num_threads(2)
        if args.command == "context-query":
            perception, session, memory = context_memory.load_checkpoint(args.checkpoint)
            modality = "image" if args.image else "audio"
            values = load_image(args.image) if args.image else load_audio(args.audio)
            with torch.inference_mode():
                signal = perception.encode(values, modality)
                session.advance(signal, args.elapsed)
                result = memory.read(session.hidden[0], signal[0], args.now)
            print(json.dumps({"modality": modality, **result,
                              "scope": "synthetic latent routing; checkpoint unchanged"}))
            return 0
        if args.command == "time-query":
            perception, session = temporal_core.load_checkpoint(args.checkpoint)
            modality = "image" if args.image else "audio"
            values = load_image(args.image) if args.image else load_audio(args.audio)
            with torch.inference_mode():
                session.advance(perception.encode(values, modality), args.elapsed)
            print(json.dumps({"modality": modality, "predicted_next_identity": session.prediction(),
                              "observations": session.observations,
                              "scope": "synthetic anticipation; checkpoint unchanged; no subjective-time claim"}))
            return 0
        loader = online_memory.load_checkpoint if args.command == "stream-query" else load_checkpoint
        perception, memory = loader(args.checkpoint)
        modality = "image" if args.image else "audio"
        values = load_image(args.image) if args.image else load_audio(args.audio)
        with torch.inference_mode():
            representation = perception.encode(values, modality)
            if args.command == "stream-query":
                keys = online_memory.make_key(representation, args.episode, args.view)
                variance = memory.variance(keys)[0].item()
                recall = (None if variance > streaming.NOVELTY_THRESHOLD else
                          online_memory.describe(memory.recall(keys)[0].tolist()))
                print(json.dumps({"modality": modality, "episode": args.episode, "view": args.view,
                                  "recall": recall, "unknown_context": recall is None,
                                  "variance": variance,
                                  "scope": "finite synthetic contexts; no general novelty detection"}))
                return 0
            prediction = memory.recall(representation)[0].tolist()
        print(json.dumps({"modality": modality, "recall": describe(prediction),
                          "scope": "only the eight synthetic identities; unknowns not detected"}))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, EOFError, TimeoutError, wave.Error) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
