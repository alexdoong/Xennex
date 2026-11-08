"""Finite .NET/Torch RLS comparison; sensory models and language stay in Python.

Fixtures are evaluator artifacts. The native bank retains weights/covariance,
not the fixture's observations. Timing excludes generation, JSON and restore.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

import torch

from .episodic_memory import EpisodeBlock, partial_keys
from .experience_perception import semantic
from .experience_signals import samples
from .memory_actor import load
from .online_memory import OnlineMemory
from .process_metrics import memory_usage
from .signals import audio_features
from .word_grounding import key as symbol_key


def state(bank: OnlineMemory) -> dict:
    return {"keySize": bank.weights.shape[1], "valueSize": bank.weights.shape[0],
            "weights": bank.weights.flatten().tolist(),
            "precision": bank.precision.flatten().tolist(), "writes": int(bank.writes)}


def restore(payload: dict) -> OnlineMemory:
    bank = OnlineMemory(payload["keySize"], payload["valueSize"])
    bank.weights.copy_(torch.tensor(payload["weights"], dtype=torch.float64).reshape_as(bank.weights))
    bank.precision.copy_(torch.tensor(payload["precision"], dtype=torch.float64).reshape_as(bank.precision))
    bank.writes.fill_(payload["writes"])
    return bank


def replay(case: dict) -> OnlineMemory:
    bank = restore(case["initial"])
    for item in case["steps"]:
        bank.write(torch.tensor(item["key"], dtype=torch.float64),
                   torch.tensor(item["value"], dtype=torch.float64), item["strength"])
    return bank


@torch.no_grad()
def fixture(seed: int, actor_path: Path) -> dict:
    perception = load(actor_path).session.perception
    rng = random.Random(seed)
    banks, records = [], {}
    original = OnlineMemory.write

    def capture(bank, key, value, strength=1):
        if id(bank) in records:
            records[id(bank)]["steps"].append({"key": key.tolist(), "value": value.tolist(), "strength": strength})
        original(bank, key, value, strength)

    with patch.object(OnlineMemory, "write", capture):
        for episode in range(4):
            block = EpisodeBlock()
            values = tuple(rng.randrange(4) for _ in range(4))
            for index, bank in enumerate(block.banks):
                case = {"name": f"episode-{episode}-bank-{index}", "initial": state(bank), "steps": [], "queries": []}
                records[id(bank)] = case
                banks.append(case)
            for frame in range(3):
                image, audio = samples(values, rng)
                modality = "image" if frame % 2 == 0 else "audio"
                inputs = image.unsqueeze(0) if modality == "image" else audio_features(audio.unsqueeze(0))
                latent = perception.encode(inputs, modality)[0]
                cue, known = semantic(perception.probabilities(latent.unsqueeze(0))[0])
                if not bool(known.all()):
                    raise ValueError("Native fixture requires a reliably perceived synthetic scene.")
                block.observe(cue, frame + 1.)
            for bank in block.banks:
                case = records[id(bank)]
                case["queries"] = [item.tolist() for item in partial_keys(cue)]
            # Keep bank owners alive until their object IDs have left the capture registry.
            records.clear()

        lexical = OnlineMemory(256, 32)
        lexical_case = {"name": "lexical", "initial": state(lexical), "steps": [], "queries": []}
        records[id(lexical)] = lexical_case
        banks.append(lexical_case)
        for frame in range(4):
            for concept in range(16):
                field, category = divmod(concept, 4)
                values = tuple(category if index == field else rng.randrange(4) for index in range(4))
                image, audio = samples(values, rng, tuple(index == field for index in range(4)))
                modality = "image" if frame % 2 == 0 else "audio"
                inputs = image.unsqueeze(0) if modality == "image" else audio_features(audio.unsqueeze(0))
                latent = perception.encode(inputs, modality)[0]
                key = symbol_key(f"native{concept}")
                lexical.write(key, latent.double(), (.3, 1., 4., 10000.)[frame])
        lexical_case["queries"] = [symbol_key(f"native{index}").tolist() for index in range(17)]
    return {"format": 1, "banks": banks}


def quantiles(values: list[float]) -> dict:
    ordered = sorted(values)
    return {name: ordered[math.ceil(fraction * len(ordered)) - 1]
            for name, fraction in (("p50Ms", .5), ("p95Ms", .95), ("p99Ms", .99))}


@torch.no_grad()
def benchmark(case: dict) -> dict:
    vectors = [(torch.tensor(item["key"], dtype=torch.float64),
                torch.tensor(item["value"], dtype=torch.float64), item["strength"]) for item in case["steps"]]
    bank = restore(case["initial"])
    for key, value, strength in vectors:
        bank.write(key, value, strength)
        bank.weights @ key
        bank.variance(key)
    timings, elapsed = [], 0.
    for _ in range(3):
        bank = restore(case["initial"])
        started = time.perf_counter()
        for key, value, strength in vectors:
            tick = time.perf_counter()
            bank.write(key, value, strength)
            bank.weights @ key
            bank.variance(key)
            timings.append((time.perf_counter() - tick) * 1000)
        elapsed += time.perf_counter() - started
        if elapsed > 120:
            raise TimeoutError("Torch kernel exceeded 120 s.")
    return {**quantiles(timings), "operations": len(timings), "seconds": elapsed,
            "stateBytes": sum(value.numel() * value.element_size() for value in bank.state_dict().values()),
            "allocatedBytes": None, "scratchBytes": None}


def compare(left, right) -> dict:
    left, right = torch.tensor(left, dtype=torch.float64), torch.tensor(right, dtype=torch.float64)
    if left.shape != right.shape:
        return {"passed": False, "shapeMismatch": True}
    return {"passed": bool(torch.allclose(left, right, atol=1e-8, rtol=1e-8)),
            "maxAbsoluteError": float((left - right).abs().max())}


@torch.no_grad()
def evaluate(case: dict, result: dict, perception=None) -> dict:
    bank = replay(case)
    expected = state(bank)
    weights = compare(result["state"]["weights"], expected["weights"])
    precision = compare(result["state"]["precision"], expected["precision"])
    key_values = [torch.tensor(key, dtype=torch.float64) for key in case["queries"]]
    reads = [compare(probe["value"], (bank.weights @ key).tolist()) for probe, key in zip(result["probes"], key_values)]
    variances = compare([probe["variance"] for probe in result["probes"]], [float(bank.variance(key)) for key in key_values])
    decisions = all(int(torch.tensor(probe["value"]).argmax()) == int((bank.weights @ key).argmax())
                    for probe, key in zip(result["probes"], key_values))
    decoded = None
    if perception is not None and case["name"] == "lexical":
        native_latents = torch.nn.functional.normalize(torch.tensor([probe["value"] for probe in result["probes"]], dtype=torch.float32), dim=1)
        torch_latents = torch.nn.functional.normalize(torch.stack([bank.weights @ key for key in key_values]).float(), dim=1)
        decoded = bool(torch.equal(perception.probabilities(native_latents).argmax(-1), perception.probabilities(torch_latents).argmax(-1)))
    # Independent weighted batch ridge oracle is used only by this evaluator.
    keys = torch.tensor([item["key"] for item in case["steps"]], dtype=torch.float64)
    values = torch.tensor([item["value"] for item in case["steps"]], dtype=torch.float64)
    strengths = torch.tensor([item["strength"] for item in case["steps"]], dtype=torch.float64)
    normal = keys.T @ (keys * strengths.unsqueeze(1)) + torch.eye(keys.shape[1], dtype=torch.float64) * .001
    ridge = torch.linalg.solve(normal, keys.T @ (values * strengths.unsqueeze(1))).T
    batch = compare(result["state"]["weights"], ridge.flatten().tolist())
    first = case["steps"][0]
    bank.write(torch.tensor(first["key"], dtype=torch.float64), torch.tensor(first["value"], dtype=torch.float64), first["strength"])
    next_weights = compare(result["resumed"]["weights"], bank.weights.flatten().tolist())
    next_precision = compare(result["resumed"]["precision"], bank.precision.flatten().tolist())
    counts = result["state"]["writes"] == expected["writes"] and result["resumed"]["writes"] == int(bank.writes)
    checks = [weights, precision, variances, batch, next_weights, next_precision, *reads]
    return {"name": case["name"], "passed": all(item["passed"] for item in checks) and decisions and counts and decoded is not False,
            "weights": weights, "precision": precision, "readsMaxError": max(item["maxAbsoluteError"] for item in reads),
            "variances": variances, "batchRidge": batch, "nextWeights": next_weights, "nextPrecision": next_precision,
            "decisionsEqual": decisions, "decodedFieldsEqual": decoded, "countersEqual": counts,
            "native": result["measurement"], "torch": benchmark(case)}


def run(seed: int, output: Path, actor: Path, runtime: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    started, cpu = time.perf_counter(), time.process_time()
    inputs = fixture(seed, actor)
    path = output / "fixture.json"
    path.write_text(json.dumps(inputs, allow_nan=False), encoding="utf-8")
    command = ["dotnet", str(runtime.resolve()), str(path.resolve()), str((output / "native.json").resolve())]
    environment = dict(os.environ, DOTNET_TieredCompilation="0")
    remaining = 120 - (time.perf_counter() - started)
    if remaining <= 0:
        raise TimeoutError("Native experiment exceeded total 120 s budget.")
    native = subprocess.run(command, capture_output=True, text=True, timeout=remaining,
                            env=environment,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    (output / "native.stderr.txt").write_text(native.stderr, encoding="utf-8")
    if native.returncode:
        raise RuntimeError(f"Native benchmark failed: {native.stderr[:2048]}")
    results = json.loads((output / "native.json").read_text(encoding="utf-8"))
    if len(results["banks"]) != len(inputs["banks"]):
        raise ValueError("Missing native bank results.")
    perception = load(actor).session.perception
    checks = []
    for case, result in zip(inputs["banks"], results["banks"]):
        checks.append(evaluate(case, result, perception))
        if time.perf_counter() - started > 120:
            raise TimeoutError("Native experiment exceeded total 120 s budget.")
    report = {"format": 1, "seed": seed, "accepted": all(item["passed"] for item in checks),
              "scope": "RLS kernel only; synthetic percept-derived workload, no production adoption",
              "tolerance": {"atol": 1e-8, "rtol": 1e-8}, "torchThreads": torch.get_num_threads(),
              "nativeEnvironment": {"DOTNET_TieredCompilation": "0"},
              "updates": sum(len(case["steps"]) for case in inputs["banks"]), "banks": checks,
              "fixtureSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "actorSha256": hashlib.sha256(actor.read_bytes()).hexdigest(),
              "runtimeSha256": hashlib.sha256(runtime.read_bytes()).hexdigest(),
              "wallSeconds": time.perf_counter() - started, "pythonCpuSeconds": time.process_time() - cpu,
              "pythonMemory": memory_usage(), "nativeProcess": {key: value for key, value in results.items() if key != "banks"},
              "limits": ["process RSS includes fixture/JSON, kernel timing excludes them",
                         "Torch allocation/scratch not measured; compare state and latency separately",
                         "scalar .NET reference is not a Rust or complete mind benchmark",
                         "fixed ordering native then Torch; not an isolated causal speedup estimate"]}
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--actor", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, default=Path("bin/AliceRuntimeTests/net8.0/AliceRuntimeTests.dll"))
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    torch.set_num_threads(1)
    result = run(options.seed, options.output, options.actor, options.runtime)
    print(json.dumps({"accepted": result["accepted"], "seed": result["seed"], "updates": result["updates"],
                      "wallSeconds": result["wallSeconds"], "report": str(options.output / "report.json")}))
    raise SystemExit(0 if result["accepted"] else 1)
