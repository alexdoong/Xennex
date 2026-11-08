"""Single-owner durable generations with one bounded asynchronous writer."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from .loop_checkpoint import atomic_write

GENERATION = re.compile(r"alice-[0-9a-f]{32}\.pt\Z")
MAX_CHECKPOINT = 80_000_000


def atomic_json(path, value):
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


class RuntimeLease:
    def __init__(self, root):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.stream = None
        path = self.root / "lease.lock"
        if path.is_symlink() or path.resolve().parent != self.root:
            raise ValueError("Invalid runtime lease path.")
        stream = path.open("a+b")
        try:
            if not path.stat().st_size:
                stream.write(b"\0")
                stream.flush()
            stream.seek(0)
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            stream.close()
            raise
        self.stream = stream

    def close(self):
        if self.stream is not None:
            self.stream.close()
            self.stream = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class RuntimeStore:
    def __init__(self, root):
        self.lease = RuntimeLease(root)
        self.root = self.lease.root
        self.executor = None
        self.future = None
        self.manifest = None
        self.last_error = None
        self.committed = 0
        self.recovery_errors = []
        self.closed = False
        self.native_page_index = None
        try:
            path = self.root / "current.json"
            if path.exists():
                self.manifest = self.read_manifest()
            elif any(self.root.glob("alice-*.pt")):
                raise ValueError("Runtime generations exist without a valid commit pointer.")
            marker = self.root / "store.json"
            if marker.exists():
                if marker.is_symlink() or marker.stat().st_size > 1024:
                    raise ValueError("Invalid runtime ownership marker.")
                owner = json.loads(marker.read_text(encoding="utf-8"))
                if not isinstance(owner, dict) or set(owner) != {"format", "kind"} or owner != {"format": 1, "kind": "alice-runtime-store"}:
                    raise ValueError("Invalid runtime ownership marker.")
            else:
                if self.manifest is None and any(item.name != "lease.lock" for item in self.root.iterdir()):
                    raise ValueError("A new runtime requires an empty dedicated directory.")
                if self.manifest is not None:
                    # Migrate this turn's earlier stores only after checking committed hashes.
                    self.candidates()
                atomic_json(marker, {"format": 1, "kind": "alice-runtime-store"})
            self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="alice-persistence")
        except BaseException:
            self.lease.close()
            raise

    def path(self, name):
        if not isinstance(name, str) or GENERATION.fullmatch(name) is None:
            raise ValueError("Invalid runtime generation filename.")
        path = self.root / name
        if path.is_symlink() or path.resolve().parent != self.root:
            raise ValueError("Runtime generation escapes its store.")
        return path

    def read_manifest(self):
        path = self.root / "current.json"
        if path.is_symlink() or path.stat().st_size > 4096:
            raise ValueError("Invalid runtime commit pointer.")
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or set(value) != {"format", "current", "previous"} or value["format"] != 1:
            raise ValueError("Invalid runtime commit format.")
        for record in (value["current"], value["previous"]):
            if record is None:
                continue
            if not isinstance(record, dict) or set(record) != {"file", "sha256", "captured_wall", "clock", "size"}:
                raise ValueError("Invalid runtime generation record.")
            self.path(record["file"])
            if not isinstance(record["sha256"], str) or re.fullmatch(r"[0-9a-f]{64}", record["sha256"]) is None:
                raise ValueError("Invalid runtime generation digest.")
            if type(record["size"]) is not int or not 1 <= record["size"] <= MAX_CHECKPOINT:
                raise ValueError("Invalid runtime generation size.")
            for name in ("captured_wall", "clock"):
                number = record[name]
                if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or number < 0:
                    raise ValueError("Invalid runtime generation time.")
        if value["current"] is None or (value["previous"] and value["current"]["file"] == value["previous"]["file"]):
            raise ValueError("Runtime requires distinct committed generations.")
        return value

    def candidates(self):
        if self.manifest is None:
            return []
        valid, errors = [], []
        for record in (self.manifest["current"], self.manifest["previous"]):
            if record is None:
                continue
            try:
                path = self.path(record["file"])
                if path.stat().st_size != record["size"] or digest(path) != record["sha256"]:
                    raise ValueError("Runtime generation checksum/size mismatch.")
                valid.append((path, record))
            except (OSError, ValueError) as error:
                errors.append({"file": record["file"], "error": str(error)[:512]})
        self.recovery_errors = errors
        if not valid:
            raise ValueError("No intact runtime generation remains.")
        return valid

    def use_recovered(self, record):
        if self.future is not None or self.manifest is None or record not in (self.manifest["current"], self.manifest["previous"]):
            raise ValueError("Invalid runtime recovery selection.")
        if record != self.manifest["current"]:
            # Preserve the intact fallback as the next commit's backup.
            self.manifest = {"format": 1, "current": dict(record), "previous": None}

    def submit(self, payload, clock, captured_wall=None):
        if self.closed or self.future is not None:
            return False
        captured_wall = time.time() if captured_wall is None else captured_wall
        for number in (clock, captured_wall):
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or number < 0:
                raise ValueError("Invalid runtime capture time.")
        self.future = self.executor.submit(self.commit, payload, clock, captured_wall)
        return True

    def capture(self, agent):
        if self.closed or self.future is not None:
            raise ValueError('Cannot capture while the runtime writer is busy/closed.')
        from .conceptual_mind import ConceptualMind
        from .runtime_snapshot import capture, freeze
        if not isinstance(agent, ConceptualMind):
            return capture(agent)
        from .native_page_store import capture_pages, index_pages, PendingNativeCheckpoint
        if self.native_page_index is None:
            self.native_page_index = index_pages(self.root)
        moments, writes = capture_pages(agent.native.moments, self.root, self.native_page_index)
        return PendingNativeCheckpoint(freeze(agent.snapshot(moments)), writes, str(self.root))

    def collect_native_pages(self, additional=()):
        if self.closed or self.future is not None:
            raise ValueError('Cannot collect native pages while the writer is busy/closed.')
        return self._collect_native_pages(additional)

    def _collect_native_pages(self, additional=()):
        from .native_page_gc import collect
        try:
            pointer = self.read_manifest() if (self.root / 'current.json').exists() else None
            retained = [] if pointer is None else [(self.path(item['file']), item) for item in (pointer['current'], pointer['previous']) if item is not None]
            result = collect(self.root, retained, additional)
        except Exception as error:
            result = {'status': 'skipped', 'removed_pages': 0, 'removed_bytes': 0, 'missing_entries': 0,
                      'errors': [type(error).__name__ + ': ' + str(error)[:512]]}
        if result['removed_pages'] or result['missing_entries']:
            self.native_page_index = None
        return result

    def commit(self, payload, clock, captured_wall):
        path = self.path("alice-" + uuid4().hex + ".pt")
        native_storage = None
        collection = None
        try:
            from .native_page_store import PendingNativeCheckpoint, persist
            if isinstance(payload, PendingNativeCheckpoint):
                records = payload.payload['native']['moments']['pages']
                collection = self._collect_native_pages(records)
                native_storage = {'references': len(records), 'unique_pages': len({item['sha256'] for item in records}),
                                  'new_pages': len(payload.writes), 'new_page_bytes': sum(len(raw) for _, raw in payload.writes),
                                  'referenced_bytes': sum(item['size'] for item in records)}
                payload = persist(payload, self.root)
                self.native_page_index = {item['sha256']: item['size'] for item in payload['native']['moments']['pages']}
            atomic_write(path, payload)
            size = path.stat().st_size
            if not 1 <= size <= MAX_CHECKPOINT:
                raise ValueError("Runtime checkpoint exceeds its archive limit.")
            current = {"file": path.name, "sha256": digest(path), "clock": clock,
                       "captured_wall": captured_wall, "size": size}
            previous = None if self.manifest is None else self.manifest["current"]
            value = {"format": 1, "current": current, "previous": previous}
            atomic_json(self.root / "current.json", value)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        old = None if self.manifest is None else self.manifest["previous"]
        self.manifest = value
        cleanup_error = None
        if old is not None:
            try:
                obsolete = self.path(old["file"])
                if obsolete.exists() and digest(obsolete) == old["sha256"]:
                    obsolete.unlink()
            except (OSError, ValueError) as error:
                cleanup_error = str(error)[:512]
        result = {"record": current, "cleanup_error": cleanup_error}
        if native_storage is None:
            return result
        after = self._collect_native_pages(records)
        return {**result, 'native_storage': native_storage, 'native_page_gc': {'before': collection, 'after': after}}

    def poll(self):
        if self.future is None or not self.future.done():
            return None
        future, self.future = self.future, None
        try:
            result = future.result()
            self.committed += 1
            self.last_error = None
            return {"status": "committed", **result}
        except Exception as error:
            self.native_page_index = None
            self.last_error = type(error).__name__ + ": " + str(error)[:512]
            return {"status": "failed", "error": self.last_error}

    def finish(self):
        if self.future is not None:
            # Only disk work remains. Called after ticks stop, before releasing ownership.
            try:
                self.future.result()
            except Exception:
                pass
            return self.poll()
        return None

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.finish()
            self.executor.shutdown(wait=True)
        finally:
            self.lease.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
