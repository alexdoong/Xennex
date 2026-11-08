"""Opt-in finite GPU language worker using Xennex's measured Windows telemetry.

Requires the built LocalAiTests harness. This experimental worker is not the
production resource authority; checkpoints still use the CPU worker by default.
The full cold-model reserve remains in both RAM and VRAM, even for GPU offload.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .episodic_language import write_report
from .language import AdmissionDeferred, LocalLanguage
from .language_worker import execute, read_operation
from .process_metrics import physical_memory
from .expectation_protocol import ExpectationLanguage

GIB = 1024 ** 3


def resource_snapshot() -> dict:
    if sys.platform != "win32":
        raise RuntimeError("GPU admission requires Windows resource telemetry.")
    harness = Path(__file__).resolve().parents[2] / "bin/LocalAiTests/net8.0/LocalAiTests.dll"
    if not harness.is_file():
        raise RuntimeError("Build scripts/tests/LocalAiTests before GPU inference.")
    # No caller-provided command or assembly; read-only telemetry, finite timeout.
    result = subprocess.run(["dotnet", str(harness), "--resources"], check=True,
                            capture_output=True, encoding="utf-8", timeout=5,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    if len(result.stdout.encode("utf-8")) > 65536 or len(result.stderr.encode("utf-8")) > 65536:
        raise ValueError("Resource telemetry exceeds its output budget.")
    value = json.loads(result.stdout)
    validate_snapshot(value)
    return value


def validate_snapshot(value: dict) -> None:
    if not isinstance(value, dict):
        raise ValueError("Invalid resource telemetry object.")
    for total, used in (("ramTotalGb", "ramUsedGb"), ("vramTotalGb", "vramUsedGb")):
        for name in (total, used):
            number = value.get(name)
            if isinstance(number, bool) or not isinstance(number, (float, int)) or not math.isfinite(number):
                raise ValueError("Measured RAM and VRAM are required for GPU admission.")
        if not 0 < value[total] <= 4096 or not 0 <= value[used] <= value[total]:
            raise ValueError("Invalid resource telemetry bounds.")
    if not isinstance(value.get("gpuName"), str) or not value["gpuName"].strip():
        raise ValueError("Measured dedicated GPU identity is required.")
    try:
        captured = datetime.fromisoformat(value["capturedAt"].replace("Z", "+00:00"))
        if captured.tzinfo is None or not 0 <= (datetime.now(timezone.utc) - captured).total_seconds() <= 5:
            raise ValueError("Stale resource telemetry.")
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("Invalid resource telemetry timestamp.") from error


class GpuLanguage(LocalLanguage):
    def admit(self, metadata: dict) -> None:
        if type(metadata.get("size")) is not int or metadata["size"] <= 0:
            raise ValueError("Measured model size is required.")
        reserve = metadata["size"] * 1.25 + 256 * 1024 ** 2
        deadline = time.monotonic() + self.wait_seconds
        self.admission_record = {"device": "gpu", "admitted": False,
                                 "reserve_ram_bytes": reserve, "reserve_vram_bytes": reserve,
                                 "snapshot": None}
        while True:
            try:
                snapshot = resource_snapshot()
                # Check again at use, including injected telemetry in deterministic tests.
                validate_snapshot(snapshot)
            except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
                self.admission_record["error"] = str(error)[:256]
                deferred = AdmissionDeferred(physical_memory(), reserve)
                deferred.args = ("GPU resource telemetry unavailable; inference waits: " + str(error)[:256],)
                raise deferred from error
            ram = {"used_bytes": snapshot["ramUsedGb"] * GIB,
                   "total_bytes": snapshot["ramTotalGb"] * GIB}
            self.admission_record["snapshot"] = snapshot
            if ram["used_bytes"] + reserve > ram["total_bytes"] * .75:
                deferred = AdmissionDeferred(ram, reserve)
            elif snapshot["vramUsedGb"] * GIB + reserve > snapshot["vramTotalGb"] * GIB * .75:
                deferred = AdmissionDeferred(ram, reserve)
                deferred.args = ("Language inference waits for the configured 75% VRAM budget.",)
            else:
                self.admission_record["admitted"] = True
                return
            if time.monotonic() >= deadline:
                raise deferred
            time.sleep(min(.25, max(0, deadline - time.monotonic())))

    def _request(self, path: str, body: dict | None = None) -> dict:
        if path == "/api/chat":
            # Copy the CPU request: preserve its prompt, schema and output bounds.
            body = {**body, "options": {**body["options"], "num_gpu": -1}}
        return super()._request(path, body)


class GpuExpectationLanguage(GpuLanguage, ExpectationLanguage):
    """The same measured GPU admission with the expectation-only contract."""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    instances = []
    operation = read_operation(args.request)

    def factory(*parameters, **options):
        kind = GpuExpectationLanguage if operation["stage"] == "expectation" else GpuLanguage
        language = kind(*parameters, **options)
        instances.append(language)
        return language

    result = execute(operation, factory)
    if instances and hasattr(instances[0], "admission_record"):
        write_report(args.output.with_name("gpu-admission.json"), instances[0].admission_record)
    write_report(args.output, result)


if __name__ == "__main__":
    main()
