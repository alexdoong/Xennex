"""Atomic bounded learning cycles from original episodic neural sources."""
from __future__ import annotations

from .adaptive_memory import recalled_pair


def consolidation_cycle(model, index, memory, episode, replay_limit=3, policy="representatives"):
    """Current source plus bounded reactivation; no cached or caller-supplied labels.

    A cycle may deliberately rehearse a previously consolidated current episode.
    This primitive is not an exactly-once scheduler or a full semantic backend.
    """
    if type(replay_limit) is not int or not 0 <= replay_limit <= 16 or policy not in ("representatives", "history") or (index is None and replay_limit != 0):
        raise ValueError("Invalid bounded neural consolidation cycle.")
    if model.config["key_size"] != 12 or model.config["value_size"] != 4:
        raise ValueError("Consolidation requires the structured four-field source.")
    before = {name: value.clone() for name, value in model.state_dict().items()}
    index_state = index.snapshot() if index is not None else None
    try:
        target = index.target if index is not None else 2
        pair = recalled_pair(memory, episode, memory.clock, target)
        if pair is None:
            raise ValueError("Current neural source cannot support consolidation.")
        selected = {"pairs": [], "attempted": 0, "skipped": []}
        if index is not None:
            index.observe(memory, episode, memory.clock)
            selected = index.select(memory, replay_limit, exclude=episode, policy=policy)
        if int(model.writes) + 1 + len(selected["pairs"]) > 100000:
            raise ValueError("Consolidation cycle exceeds the write budget; prior state preserved.")
        for source in (pair, *selected["pairs"]):
            model.write(source["key"], source["value"], memory.clock)
        return {"source_episode": episode, "source_revision": pair["source_revision"],
                "reactivated": [source["source_episode"] for source in selected["pairs"]],
                "attempted": selected["attempted"], "skipped": selected["skipped"],
                "source_reads": 1 + int(index is not None) + selected["attempted"]}
    except BaseException:
        model.load_state_dict(before, strict=True)
        if index is not None:
            index.load_state_dict(index_state["state"], strict=True)
            index.generator.set_state(index_state["generator"])
        raise
