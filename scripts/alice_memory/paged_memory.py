"""Lossless neural episode pages, bounded resident cache and an exact route index."""
from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import uuid
import zlib
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

import torch

from .episodic_memory import EpisodeBlock, EpisodeTrace, EpisodicMemory, cue_valid

ROUTE_FIELDS = ("addresses", "known", "learned_at", "revisions")
MAX_ARCHIVE = 64 * 1024 * 1024


def pack(value: dict) -> bytes:
    stream = io.BytesIO()
    torch.save(value, stream)
    return zlib.compress(stream.getvalue())


def unpack(value: bytes, limit: int = 65536) -> dict:
    decoder = zlib.decompressobj()
    raw = decoder.decompress(value, limit + 1)
    if len(raw) > limit or not decoder.eof or decoder.unused_data:
        raise ValueError("Neural page exceeds its decoded size limit.")
    result = torch.load(io.BytesIO(raw), map_location="cpu", weights_only=True)
    if not isinstance(result, dict):
        raise ValueError("Neural page must contain tensor fields.")
    return result


class PageView:
    def __init__(self, owner, index):
        self.owner, self.index = owner, index

    def __getattr__(self, name):
        if name in ROUTE_FIELDS:
            return self.owner.pool[name][self.index]
        if name == "banks":
            return self.owner.block(self.index).banks
        raise AttributeError(name)

    def observe(self, cue, now):
        block = self.owner.block(self.index)
        block.observe(cue, now)
        self.owner.copy_route(self.index, block)


class PageSequence:
    def __init__(self, owner):
        self.owner = owner

    def __len__(self):
        return self.owner.count

    def __getitem__(self, index):
        if type(index) is not int:
            raise IndexError("Neural page index must be an integer.")
        index = index if index >= 0 else self.owner.count + index
        if not 0 <= index < self.owner.count:
            raise IndexError(index)
        return PageView(self.owner, index)

    def __iter__(self):
        return (PageView(self.owner, index) for index in range(self.owner.count))

    def append(self, block):
        self.owner.room()
        index = self.owner.count
        self.owner.count += 1
        self.owner.cache[index] = block
        self.owner.copy_route(index, block)


class PagedMemory(EpisodicMemory):
    def __init__(self, capacity: int = 4096, hot_limit: int = 4):
        if type(capacity) is not int or not 1 <= capacity <= 4096 or type(hot_limit) is not int or not 1 <= hot_limit <= min(32, capacity):
            raise ValueError("Invalid archive capacity/resident budget.")
        super().__init__(min(capacity, 128))
        del self._modules["blocks"]
        self.capacity, self.hot_limit, self.revision_capacity = capacity, hot_limit, 32768
        self.count, self.loads, self.hits, self.evictions = 0, 0, 0, 0
        self.cache = OrderedDict()
        self._observation_batch = False
        self.blocks = PageSequence(self)
        template = EpisodeBlock()
        self.pool = {name: torch.zeros((capacity, *getattr(template, name).shape), dtype=getattr(template, name).dtype)
                     for name in ROUTE_FIELDS}
        folder = Path.cwd() / "bin" / "AlicePages"
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / (uuid.uuid4().hex + ".sqlite")
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("CREATE TABLE episodes (id INTEGER PRIMARY KEY, route BLOB NOT NULL, page BLOB NOT NULL, digest TEXT NOT NULL, trace TEXT NOT NULL)")
        self.connection.commit()

    def copy_route(self, index, block):
        for name in ROUTE_FIELDS:
            self.pool[name][index].copy_(getattr(block, name))

    def room(self):
        if len(self.cache) < self.hot_limit:
            return
        index = next(iter(self.cache))
        self.persist(index)
        self.cache.pop(index)
        self.evictions += 1

    def persist(self, index):
        block = self.cache[index]
        for name in ROUTE_FIELDS:
            getattr(block, name).copy_(self.pool[name][index])
        route = pack({name: self.pool[name][index].clone() for name in ROUTE_FIELDS})
        page = pack(block.state_dict())
        digest = hashlib.sha256(route + page).hexdigest()
        trace = json.dumps(asdict(self.traces[index]), separators=(",", ":"))
        # Compare actual serialized contents, including direct in-place weight
        # edits. Reading a clean page need not issue another SQLite transaction.
        if getattr(block, "_persisted", None) == (digest, trace):
            return
        if self._observation_batch:
            self._persist_row(index, route, page, digest, trace)
        else:
            with self.connection:
                self._persist_row(index, route, page, digest, trace)
        block._persisted = (digest, trace)

    def _persist_row(self, index, route, page, digest, trace):
        self.connection.execute("INSERT OR REPLACE INTO episodes VALUES (?,?,?,?,?)", (index, route, page, digest, trace))
        size = self.connection.execute("PRAGMA page_count").fetchone()[0] * self.connection.execute("PRAGMA page_size").fetchone()[0]
        if size > MAX_ARCHIVE:
            raise ValueError("Neural archive storage budget reached; prior pages preserved.")

    def block(self, index):
        if index in self.cache:
            self.hits += 1
            self.cache.move_to_end(index)
            return self.cache[index]
        row = self.connection.execute("SELECT route,page,digest FROM episodes WHERE id=?", (index,)).fetchone()
        if row is None or hashlib.sha256(row[0] + row[1]).hexdigest() != row[2]:
            raise ValueError("Missing or corrupt neural episode page.")
        state = unpack(row[1])
        block = EpisodeBlock()
        expected = block.state_dict()
        if set(state) != set(expected):
            raise ValueError("Invalid neural page tensor fields.")
        for name, value in state.items():
            if not isinstance(value, torch.Tensor) or value.dtype != expected[name].dtype or value.shape != expected[name].shape or not torch.isfinite(value).all():
                raise ValueError("Invalid neural page tensor type/shape/value.")
        block.load_state_dict(state, strict=True)
        if any(not torch.equal(getattr(block, name), self.pool[name][index]) for name in ROUTE_FIELDS):
            raise ValueError("Neural page disagrees with its route index.")
        for bank in block.banks:
            if bank.writes.item() < 0 or not torch.allclose(bank.precision, bank.precision.T, atol=1e-8) or torch.linalg.cholesky_ex(bank.precision).info.item() != 0:
                raise ValueError("Invalid neural page precision/counter.")
        self.room()
        block._persisted = (row[2], json.dumps(asdict(self.traces[index]), separators=(",", ":")))
        self.cache[index] = block
        self.loads += 1
        return block

    def observe(self, cue, now, boundary):
        if type(boundary) is not bool:
            raise ValueError("Boundary decision must be boolean.")
        return self.observe_at(cue, now, None if boundary or not self.count else self.count - 1)

    def observe_at(self, cue, now, episode=None):
        known = cue_valid(cue)
        self.time_valid(now)
        if episode is not None and (type(episode) is not int or not 0 <= episode < self.count):
            raise ValueError("Invalid ongoing episode address.")
        if not known.any():
            # Clock-only ticks need neither a new episode nor a rollback copy
            # of neural weights, including when the archive is at capacity.
            return super().observe_at(cue, now, episode)
        if episode is None and self.count == self.capacity:
            raise ValueError("Episode capacity reached; archive preserved.")
        if self._observation_batch:
            index = super().observe_at(cue, now, episode)
            self.persist(index)
            return index
        with self.atomic_observations([] if episode is None else [episode]):
            return self.observe_at(cue, now, episode)

    @contextmanager
    def atomic_observations(self, episodes):
        episodes = tuple(episodes)
        if self._observation_batch or any(type(index) is not int or not 0 <= index < self.count for index in episodes):
            raise ValueError("Invalid or nested observation transaction.")
        selected = set(episodes)
        old_count, old_clock = self.count, self.clock
        old_cache = self.cache.copy()
        cached = {index: ({name: value.clone() for name, value in block.state_dict().items()},
                          getattr(block, "_persisted", None)) for index, block in old_cache.items()}
        old_routes = {index: {name: tensor[index].clone() for name, tensor in self.pool.items()} for index in selected}
        old_traces = {index: asdict(self.traces[index]) for index in selected}
        self.connection.execute("SAVEPOINT observation_frame")
        self._observation_batch = True
        self._observation_targets = selected
        try:
            yield
            self.connection.execute("RELEASE observation_frame")
        except Exception:
            self.connection.execute("ROLLBACK TO observation_frame")
            self.connection.execute("RELEASE observation_frame")
            self.clock = old_clock
            self.count = old_count
            del self.traces[old_count:]
            for tensor in self.pool.values():
                tensor[old_count:].zero_()
            for index in selected:
                self.traces[index] = EpisodeTrace(**old_traces[index])
                for name, value in old_routes[index].items():
                    self.pool[name][index].copy_(value)
            self.cache = old_cache
            for index, (state, persisted) in cached.items():
                self.cache[index].load_state_dict(state)
                self.cache[index]._persisted = persisted
            raise
        finally:
            self._observation_batch = False
            del self._observation_targets

    def revise(self, cue, field, probabilities, learned_at, window=None, source="person"):
        selected = self.read(cue, learned_at, window=window)["episode"]
        if selected is None:
            return super().revise(cue, field, probabilities, learned_at, window, source)
        before = {name: value.clone() for name, value in self.block(selected).state_dict().items()}
        old_clock, old_revisions = self.clock, len(self.revision_log)
        try:
            result = super().revise(cue, field, probabilities, learned_at, window, source)
            if result["revised"]:
                self.persist(selected)
            return result
        except Exception:
            self.clock = old_clock
            del self.revision_log[old_revisions:]
            block = self.block(selected)
            block.load_state_dict(before)
            self.copy_route(selected, block)
            raise

    def candidates(self, cue, side, window=None):
        known = cue_valid(cue)
        if not known.any() or not self.count:
            return []
        query = cue.reshape(4, 4)[known]
        query = query / query.sum(-1, keepdim=True).clamp_min(1e-10)
        valid = self.pool["known"][:self.count, side, known].all(-1)
        scores = (self.pool["addresses"][:self.count, side, known] * query).sum(-1).mean(-1)
        if window is not None:
            valid &= torch.tensor([trace.ended >= window[0] and trace.started <= window[1] for trace in self.traces])
        indices = torch.where(valid & (scores >= .85))[0].tolist()
        return sorted(((scores[index].item(), index) for index in indices), reverse=True)

    def metadata(self):
        return {**super().metadata(), "hot_limit": self.hot_limit}

    def state_dict(self, *args, **kwargs):
        for index in list(self.cache):
            self.persist(index)
        raw = self.connection.serialize()
        if len(raw) > MAX_ARCHIVE:
            raise ValueError("Neural archive checkpoint exceeds its limit.")
        return {"archive": torch.frombuffer(bytearray(raw), dtype=torch.uint8).clone()}

    def close(self):
        self.connection.close()
        self.path.unlink(missing_ok=True)

    def __del__(self):
        if "connection" not in self.__dict__:
            return
        try:
            self.close()
        except (OSError, sqlite3.Error):
            pass


def restore_archive(state, metadata):
    if not isinstance(state, dict) or set(state) != {"archive"}:
        raise ValueError("Invalid neural archive checkpoint fields.")
    value = state["archive"]
    if not isinstance(value, torch.Tensor) or value.dtype != torch.uint8 or value.ndim != 1 or not 1 <= value.numel() <= MAX_ARCHIVE:
        raise ValueError("Invalid neural archive checkpoint bytes.")
    memory = PagedMemory(metadata["capacity"], metadata["hot_limit"])
    try:
        memory.connection.close()
        with memory.path.open("wb") as output:
            for chunk in value.split(65536):
                output.write(bytes(chunk.tolist()))
        memory.connection = sqlite3.connect(memory.path)
        tables = memory.connection.execute("SELECT name,type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
        if tables != [("episodes", "table")] or memory.connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("Invalid neural archive schema/integrity.")
        rows = memory.connection.execute("SELECT id,route,page,digest,trace FROM episodes ORDER BY id")
        for index, row in enumerate(rows):
            if index >= memory.capacity or row[0] != index or hashlib.sha256(row[1] + row[2]).hexdigest() != row[3] or json.loads(row[4]) != metadata["traces"][index]:
                raise ValueError("Invalid archived episode identity/checksum/trace.")
            route = unpack(row[1], 8192)
            if set(route) != set(ROUTE_FIELDS):
                raise ValueError("Invalid archived route fields.")
            for name, tensor in route.items():
                expected = memory.pool[name][index]
                if not isinstance(tensor, torch.Tensor) or tensor.dtype != expected.dtype or tensor.shape != expected.shape or not torch.isfinite(tensor).all():
                    raise ValueError("Invalid archived route tensor.")
                expected.copy_(tensor)
            memory.count += 1
        if memory.count != len(metadata["traces"]):
            raise ValueError("Archive episode count disagrees with metadata.")
        memory.clock = metadata["clock"]
        return memory
    except Exception:
        memory.close()
        raise
