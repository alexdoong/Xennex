#!/usr/bin/env python3
"""Local Semantic Code Search Tool for Antigravity AI Agent.

Uses Ollama with 'nomic-embed-text' (768 dimensions) to provide semantic code search
across Xennex codebase. Enables natural language conceptual queries without needing exact keywords.
Zero external dependencies (uses standard library urllib, json, math, pathlib).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple

# UTF-8 stdout
sys.stdout.reconfigure(encoding="utf-8")

OLLAMA_API_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "nomic-embed-text"
INDEX_CACHE_PATH = Path(r"E:\Projetos e apps\Xennex\.cache\semantic_index.json")
SEARCH_ROOTS = [
    Path(r"E:\Projetos e apps\Xennex\src"),
    Path(r"E:\Projetos e apps\Xennex\docs"),
    Path(r"E:\Projetos e apps\Xennex\scripts"),
]
ALLOWED_EXTENSIONS = {".cs", ".xaml", ".ts", ".tsx", ".py", ".md", ".json"}


def get_embedding(text: str, model: str = DEFAULT_MODEL) -> Optional[List[float]]:
    url = f"{OLLAMA_API_URL}/api/embeddings"
    payload = json.dumps({"model": model, "prompt": text[:2000]}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("embedding")
    except Exception as e:
        print(f"[Error fetching embedding]: {e}", file=sys.stderr)
        return None


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def chunk_file(path: Path, max_lines: int = 40) -> List[Dict[str, Any]]:
    chunks = []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if not lines:
            return chunks

        for i in range(0, len(lines), max_lines):
            chunk_lines = lines[i:i + max_lines]
            chunk_text = "\n".join(chunk_lines).strip()
            if chunk_text:
                chunks.append({
                    "start_line": i + 1,
                    "end_line": min(i + max_lines, len(lines)),
                    "text": chunk_text
                })
    except Exception:
        pass
    return chunks


def load_or_update_index() -> Dict[str, Any]:
    index: Dict[str, Any] = {"files": {}}
    if INDEX_CACHE_PATH.exists():
        try:
            with open(INDEX_CACHE_PATH, "r", encoding="utf-8") as f:
                index = json.load(f)
        except Exception:
            index = {"files": {}}

    changed = False
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in ALLOWED_EXTENSIONS:
                continue
            # Skip build output directories
            rel_str = str(p)
            if any(ign in rel_str for ign in ["bin", "obj", "node_modules", ".git", ".cache"]):
                continue

            mtime = p.stat().st_mtime
            str_path = str(p)

            # Check if cache is still fresh
            cached = index["files"].get(str_path)
            if cached and cached.get("mtime") == mtime:
                continue

            # Need to re-embed chunks
            chunks = chunk_file(p)
            chunk_data = []
            for c in chunks:
                emb = get_embedding(c["text"])
                if emb:
                    chunk_data.append({
                        "start_line": c["start_line"],
                        "end_line": c["end_line"],
                        "snippet": c["text"][:300],
                        "embedding": emb
                    })

            index["files"][str_path] = {
                "mtime": mtime,
                "chunks": chunk_data
            }
            changed = True

    if changed:
        INDEX_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(INDEX_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(index, f)

    return index


def search(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    query_emb = get_embedding(query)
    if not query_emb:
        print("Failed to compute embedding for query.", file=sys.stderr)
        return []

    index = load_or_update_index()
    results: List[Tuple[float, Dict[str, Any]]] = []

    for file_path, f_data in index["files"].items():
        for ch in f_data.get("chunks", []):
            sim = cosine_similarity(query_emb, ch["embedding"])
            results.append((sim, {
                "file": file_path,
                "start_line": ch["start_line"],
                "end_line": ch["end_line"],
                "score": round(sim, 4),
                "snippet": ch["snippet"]
            }))

    results.sort(key=lambda x: x[0], reverse=True)
    return [r[1] for r in results[:top_k]]


def main() -> int:
    parser = argparse.ArgumentParser(description="Local Semantic Code Search")
    parser.add_argument("query", help="Natural language query")
    parser.add_argument("--top", type=int, default=5, help="Number of results")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    matches = search(args.query, top_k=args.top)

    if args.json:
        print(json.dumps(matches, indent=2))
        return 0

    print("=" * 70)
    print(f"🔍 BUSCA SEMÂNTICA: \"{args.query}\"")
    print("=" * 70)
    if not matches:
        print("Nenhum resultado encontrado.")
        return 0

    for i, m in enumerate(matches, 1):
        rel = m["file"].replace("E:\\Projetos e apps\\Xennex\\", "")
        print(f"\n[{i}] {rel} (Linhas {m['start_line']}-{m['end_line']}) | Score: {m['score']}")
        print("-" * 50)
        lines = m["snippet"].splitlines()[:5]
        for l in lines:
            print(f"    {l}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
