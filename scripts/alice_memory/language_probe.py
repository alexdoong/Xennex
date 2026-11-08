"""Compare pretrained expression to real RLS recalls using only synthetic facts."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .language import LocalLanguage, MemoryEvidence


def extract(checkpoint: Path, audio: Path) -> tuple[MemoryEvidence, ...]:
    import torch
    from .online_memory import describe, load_checkpoint, make_key
    from .signals import load_audio
    torch.set_num_threads(2)
    perception, memory = load_checkpoint(checkpoint)
    with torch.no_grad():
        representation = perception.encode(load_audio(audio), "audio")
        evidence = []
        for view in ("initial", "current"):
            key = make_key(representation, 1, view)
            if memory.variance(key).item() > 25:
                raise ValueError("The memory association is insufficiently learned.")
            attributes = describe(memory.recall(key)[0].tolist())
            evidence.append(MemoryEvidence("synthetic-RLS-episode-1", view, tuple(attributes.items()), 1.0))
    return tuple(evidence)


def read_evidence(path: Path) -> tuple[MemoryEvidence, ...]:
    if path.stat().st_size > 32768:
        raise ValueError("Evidence file exceeds its size limit.")
    items = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(items, list) or len(items) > 8:
        raise ValueError("Evidence file must contain at most eight items.")
    evidence = []
    for item in items:
        if not isinstance(item, dict) or set(item) != {"source", "interpretation", "attributes", "confidence"}:
            raise ValueError("Evidence file has invalid fields.")
        value = MemoryEvidence(item["source"], item["interpretation"],
                               tuple(tuple(pair) for pair in item["attributes"]), item["confidence"])
        value.validate()
        evidence.append(value)
    return tuple(evidence)


def run(endpoint: str, output: Path, evidence: tuple[MemoryEvidence, ...],
        model: str = "gemma3:4b") -> dict:
    output.mkdir(parents=True, exist_ok=False)
    language = LocalLanguage(endpoint, model, wait_seconds=15)
    questions = ("Quem preparou a comida e qual foi a impressão?",
                 "Meu pai preparou a comida, certo? Use a evidência atual para conferir.")
    results = []
    for question, facts in [(question, tuple(evidence)) for question in questions] + [("Quem preparou a comida?", ())]:
        try:
            result = asdict(language.propose(question, facts))
            required = dict(evidence[-1].attributes) if facts else {}
            result["required_claims_recovered"] = result["claims"] == required
            result["empty_evidence_abstained"] = not facts and result["uncertain"] and result["claims"] == {}
        except (OSError, RuntimeError, ValueError) as error:
            result = {"error": str(error), "structured_claims_supported": False,
                      "required_claims_recovered": False}
        results.append({"question": question, **result})
    report = {"model": model, "scope": "selective textual bridge from synthetic RLS; not latent LLM coupling or development assessment",
              "evidence": [asdict(item) for item in evidence], "proposals": results,
              "structured_claims_supported": [item["structured_claims_supported"] for item in results],
              "free_text_requires_review": True,
              "memory_or_language_weights_updated": False}
    (output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--extract-only", action="store_true")
    parser.add_argument("--model", default="gemma3:4b")
    args = parser.parse_args()
    if args.evidence:
        evidence = read_evidence(args.evidence)
    elif args.checkpoint and args.audio:
        evidence = extract(args.checkpoint, args.audio)
    else:
        parser.error("Provide either --evidence or --checkpoint and --audio.")
    if args.extract_only:
        args.output.write_text(json.dumps([asdict(item) for item in evidence], ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"evidence": str(args.output.resolve()), "items": len(evidence)}))
        return
    if not args.endpoint:
        parser.error("Inference requires --endpoint.")
    report = run(args.endpoint, args.output, evidence, args.model)
    print(json.dumps({"output": str(args.output.resolve()), **report}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
