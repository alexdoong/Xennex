"""Grow paged episode routes and their neural provenance in one owner operation."""
from __future__ import annotations

import torch

from .neural_semantic_memory import NeuralSemanticMemory
from .paged_memory import PagedMemory
from .diagonal_importance import DiagonalImportance


LEDGER_FIELDS = ("versions", "stamps", "observations", "origins", "digests")


def expanded(tensor, capacity, fill=0, axis=0):
    tensor = tensor.movedim(axis, 0)
    value = torch.full((capacity, *tensor.shape[1:]), fill, dtype=tensor.dtype, device=tensor.device)
    value[:len(tensor)].copy_(tensor)
    return value.movedim(0, axis).contiguous()


def expand_capacity(memory, semantic, capacity, importance=None):
    """Prepare every allocation before publishing; neural weights and routes stay intact.

    Called between ticks by the owner, never concurrently with perception or a
    checkpoint. This increases a finite limit; it does not compress experiences.
    """
    if not isinstance(memory, PagedMemory) or not isinstance(semantic, NeuralSemanticMemory):
        raise ValueError("Capacity expansion requires paged episodes and their neural semantic owner.")
    semantic._owner(memory)
    if memory._observation_batch or memory.connection.in_transaction:
        raise ValueError("Capacity expansion cannot interrupt a memory transaction.")
    if semantic.index.source_capacity != memory.capacity:
        raise ValueError("Capacity expansion requires a matching provenance index.")
    if importance is not None and (not isinstance(importance, DiagonalImportance) or importance.capacity != memory.capacity):
        raise ValueError("Capacity expansion requires matching diagonal importance.")
    if type(capacity) is not int or not memory.capacity <= capacity <= 4096:
        raise ValueError("Capacity must grow monotonically within the 4096-episode archive limit.")
    previous = memory.capacity
    if capacity == previous:
        return {"expanded": False, "previous_capacity": previous, "capacity": capacity, "added_tensor_bytes": 0}
    pool = {name: expanded(value, capacity) for name, value in memory.pool.items()}
    ledger = {name: expanded(getattr(semantic, name), capacity, -1 if name == "versions" else 0)
              for name in LEDGER_FIELDS}
    salience = {}
    value_weights = value_precision = None
    if importance is not None:
        salience = {name: expanded(getattr(importance, name), capacity, -1 if name == "last_access" else 0)
                    for name in ("updates", "last_access", "accesses", "surprise")}
        value_weights = expanded(importance.values.weights, capacity * 4, axis=1)
        value_precision = expanded(importance.values.precision, capacity * 4, 1000.)
    added = sum((capacity - previous) * value[0].numel() * value.element_size()
                for value in (*pool.values(), *ledger.values()))
    added += sum((capacity - previous) * value[0].numel() * value.element_size() for value in salience.values())
    if importance is not None:
        added += (capacity - previous) * 4 * (3 * value_weights.element_size() + value_precision.element_size())
    # No disk writes, bank replacement, randomness or external callbacks in the commit.
    memory.pool = pool
    for name, value in ledger.items():
        setattr(semantic, name, value)
    if importance is not None:
        for name, value in salience.items():
            setattr(importance, name, value)
        importance.values.weights = value_weights
        importance.values.precision = value_precision
        importance.capacity = capacity
    memory.capacity = semantic.capacity = semantic.index.source_capacity = capacity
    return {"expanded": True, "previous_capacity": previous, "capacity": capacity, "added_tensor_bytes": added}
