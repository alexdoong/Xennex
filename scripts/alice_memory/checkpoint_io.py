"""Bounded checkpoint reads; larger archives belong only to paged formats."""
from pathlib import Path

import torch


def read_checkpoint(path: Path, legacy_limit: int = 8_000_000) -> dict:
    size = path.stat().st_size
    if size > 80_000_000:
        raise ValueError("Checkpoint exceeds its archive size limit.")
    payload = torch.load(path, map_location="cpu", weights_only=True)
    paged = isinstance(payload, dict) and payload.get("format") in (24, 25, 26, 27, 28, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58)
    if isinstance(payload, dict) and payload.get("format") in (33, 34):
        nested = payload.get("base")
        paged = isinstance(nested, dict) and nested.get("format") == 24
    nested = payload
    for _ in range(6):
        if not isinstance(nested, dict) or nested.get("format") not in (29, 30, 31, 35, 39, 40, 41, 42, 43, 44, 45):
            break
        nested = nested.get("agent")
    if isinstance(nested, dict) and nested.get("format") == 28:
        paged = True
    if not paged and size > legacy_limit:
        raise ValueError("Legacy checkpoint exceeds its original size limit.")
    if isinstance(payload, dict) and payload.get('format') in (46, 48, 50, 52, 54, 56, 58):
        from .native_page_store import resolve
        payload = resolve(payload, path)
    return payload
