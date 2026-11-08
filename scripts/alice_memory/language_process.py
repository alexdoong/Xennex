"""Owned finite subprocess with nonblocking polling and bounded JSON exchange."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

from .episodic_language import write_report


class LanguageProcess:
    def __init__(self, operation: dict, folder: Path, seconds: float = 120,
                 module: str = "scripts.alice_memory.language_worker", environment: dict | None = None,
                 retain_files: bool = False):
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 0 < seconds <= 120:
            raise ValueError("Language worker deadline must be between zero and 120 seconds.")
        self.token = uuid4().hex
        self.stage = operation["stage"]
        if type(retain_files) is not bool:
            raise ValueError("Invalid worker exchange retention.")
        self.retain_files = retain_files
        self.root = folder.resolve()
        self.folder = self.root / self.token
        self.folder.mkdir(parents=True, exist_ok=False)
        self.request, self.output = self.folder / "request.json", self.folder / "result.json"
        payload = {**operation, "format": 1, "token": self.token}
        if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > 32768:
            raise ValueError("Language operation exceeds its input budget.")
        write_report(self.request, payload)
        self.deadline = time.monotonic() + seconds
        self.process = None
        self.stopping = None
        self.result = None
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        worker_environment = os.environ.copy()
        worker_environment["PYTHONIOENCODING"] = "utf-8"
        if environment:
            worker_environment.update(environment)
        with (self.folder / "stdout.log").open("wb") as stdout, (self.folder / "stderr.log").open("wb") as stderr:
            self.process = subprocess.Popen([sys.executable, "-m", module, "--request", str(self.request.resolve()),
                                             "--output", str(self.output.resolve())], cwd=Path(__file__).resolve().parents[2],
                                            stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                            creationflags=flags, env=worker_environment)

    def cancel(self, reason="cancelled"):
        if self.process is not None and self.process.poll() is None:
            self.stopping = reason
            self.process.kill()

    def poll(self) -> dict | None:
        if self.result is not None:
            return self.result
        if self.process.poll() is None and self.stopping is None:
            if any(path.stat().st_size > 65536 for path in (self.folder / "stdout.log", self.folder / "stderr.log")):
                self.cancel("worker_log_budget")
        if self.process.poll() is None:
            if time.monotonic() >= self.deadline and self.stopping is None:
                self.cancel("worker_deadline")
            return None
        if self.stopping is not None:
            self.result = {"status": "failed", "value": {"reason": self.stopping}}
            return self.result
        if self.process.returncode != 0 or not self.output.is_file():
            self.result = {"status": "failed", "value": {"reason": "worker_exited_without_result"}}
            return self.result
        if self.output.stat().st_size > 65536:
            raise ValueError("Language worker result exceeds its output budget.")
        value = json.loads(self.output.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or set(value) != {"format", "token", "stage", "status", "value"} or type(value["format"]) is not int or value["format"] != 1 or value["token"] != self.token or value["stage"] != self.stage or value["status"] not in ("ready", "failed", "deferred"):
            raise ValueError("Language worker returned an invalid envelope.")
        self.result = value
        return value

    def close(self):
        self.cancel()
        if self.process is not None:
            self.process.wait(timeout=5)
        if not self.retain_files and self.folder.exists():
            if self.folder.resolve().parent != self.root:
                raise ValueError("Worker exchange left its owned directory.")
            for path in (self.request, self.output, self.folder / "stdout.log", self.folder / "stderr.log",
                         self.folder / "gpu-admission.json"):
                path.unlink(missing_ok=True)
            # Killing the worker during atomic publication can leave its staging
            # file behind. Only recognized exchange names inside this UUID folder
            # belong to this process; unexpected entries remain an explicit error.
            for path in self.folder.iterdir():
                if re.fullmatch(r'(?:request\.json|result\.json|gpu-admission\.json)\.[0-9a-f]{32}\.tmp', path.name):
                    path.unlink()
            self.folder.rmdir()

