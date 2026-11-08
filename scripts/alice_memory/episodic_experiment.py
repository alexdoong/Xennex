"""M3 supervised sensory grounding, event discovery and neural belief revisions."""
from __future__ import annotations

import json
import random
import time
import wave
import struct
from pathlib import Path

import torch

from .contracts import Observation
from .episodic_session import EpisodicSession, save
from .event_boundary import EventBoundary, score, train as train_boundary
from .experience_perception import ExperiencePerception, evaluate, semantic, train as train_perception
from .experience_signals import FIELDS, WORDS, dataset, samples, stories
from .process_metrics import Budget, memory_usage
from .signals import audio_features, save_audio


def packets(image: torch.Tensor, audio: torch.Tensor, clock: float, sequence: int,
            modality: str = "both") -> list[Observation]:
    output = []
    if modality in ("image", "both"):
        output.append(Observation("image", image, clock, sequence, "environment"))
    if modality in ("audio", "both"):
        output.append(Observation("audio", audio, clock, sequence + 1, "person"))
    return output


@torch.no_grad()
def boundary_data(perception: ExperiencePerception, seed: int) -> tuple:
    records = stories(seed, 128)
    images = torch.stack([record["image"] for record in records])
    sound = audio_features(torch.stack([record["audio"] for record in records]))
    visual = perception.probabilities(perception.encode(images, "image"))
    acoustic = perception.probabilities(perception.encode(sound, "audio"))
    current, previous, gaps, seen, target = [], [], [], [], []
    for distributions in (visual, acoustic):
        before = torch.zeros(16)
        for index, record in enumerate(records):
            cue, _ = semantic(distributions[index])
            current.append(cue.float())
            previous.append(before)
            gaps.append([record["elapsed"]])
            seen.append([float(index > 0)])
            target.append(float(record["boundary"]))
            observed = cue.reshape(4, 4).sum(-1) > .5
            next_previous = before.reshape(4, 4).clone()
            next_previous[observed] = cue.float().reshape(4, 4)[observed]
            before = next_previous.flatten()
    # Explicit teaching contrasts: one true field change versus mere occlusion.
    # These annotations are loss targets; no category/change flag enters inference.
    rng = random.Random(seed + 50000)
    pairs = []
    for index in range(1200):
        values = tuple(rng.randrange(4) for _ in range(4))
        changed = index % 3 == 0
        field = rng.randrange(4)
        after = list(values)
        if changed:
            after[field] = (after[field] + rng.choice((1, 2, 3))) % 4
        visible = tuple(axis == field or rng.random() > .3 for axis in range(4)) if changed else tuple(rng.random() > .3 for _ in range(4))
        previous_image, previous_audio = samples(values, rng)
        image, audio = samples(tuple(after), rng, visible)
        pairs.append((previous_image, previous_audio, image, audio, changed))
    for modality in ("image", "audio"):
        if modality == "image":
            before_input = torch.stack([pair[0] for pair in pairs])
            after_input = torch.stack([pair[2] for pair in pairs])
        else:
            before_input = audio_features(torch.stack([pair[1] for pair in pairs]))
            after_input = audio_features(torch.stack([pair[3] for pair in pairs]))
        before_probabilities = perception.probabilities(perception.encode(before_input, modality))
        after_probabilities = perception.probabilities(perception.encode(after_input, modality))
        for index, pair in enumerate(pairs):
            current.append(semantic(after_probabilities[index])[0].float())
            previous.append(semantic(before_probabilities[index])[0].float())
            gaps.append([rng.uniform(.1, .25)])
            seen.append([1.])
            target.append(float(pair[4]))
    return (torch.stack(current), torch.stack(previous), torch.tensor(gaps), torch.tensor(seen), torch.tensor(target))


def create(seed: int, budget: Budget) -> tuple[EpisodicSession, dict]:
    torch.manual_seed(seed)
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    perception = ExperiencePerception()
    started = time.perf_counter()
    train_perception(perception, dataset(seed + 100), seed + 200, budget)
    perception_seconds = time.perf_counter() - started
    scores = evaluate(perception, dataset(seed + 300, 512, evaluation=True))
    boundary = EventBoundary(mask_unobserved=True)
    started = time.perf_counter()
    train_boundary(boundary, boundary_data(perception, seed + 1000), seed + 2000, budget)
    return EpisodicSession(perception, boundary), {"perception": scores, "perception_training_seconds": perception_seconds,
                                                "boundary_training_seconds": time.perf_counter() - started}


def drive(session: EpisodicSession, records: list[dict], modality: str = "both") -> dict:
    actual, expected = [], []
    for index, record in enumerate(records):
        values = packets(record["image"], record["audio"], session.clock + record["elapsed"], session.steps * 2, modality)
        result = session.step(values, record["elapsed"])
        if result["new_episode"]:
            actual.append(index)
        if record["boundary"]:
            expected.append(index)
    return score(actual, expected, 1)


def partial_queries(session: EpisodicSession, records: list[dict], seed: int) -> dict:
    rng = random.Random(seed)
    groups = {}
    for record in records:
        groups.setdefault(record["episode"], []).append(record)
    output = {}
    for modality in ("image", "audio"):
        recovered, total, false = 0, 0, 0
        for group in groups.values():
            truth = group[0]["truth"]
            # A temporal clue is supplied by the question, not an oracle episode ID.
            window = (group[0]["clock"], group[-1]["clock"])
            image, audio = samples(truth, rng, (True, False, False, True))
            recall = session.query(packets(image, audio, session.clock, 0, modality), window=window)
            expected = {field: words[value] for field, words, value in zip(FIELDS, WORDS, truth)}
            recovered += int(recall["recall"] == expected)
            total += 1
            contradict = ((truth[0] + 1) % 4, truth[1], truth[2], truth[3])
            image, audio = samples(contradict, rng, (True, False, False, True))
            unsupported = session.query(packets(image, audio, session.clock, 0, modality), window=window)
            false += int(unsupported["recall"] is not None)
        output[modality] = {"episodes": total, "complete_recall": recovered / max(total, 1),
                            "false_recall": false / max(total, 1)}
    return output


def meals(session: EpisodicSession, seed: int) -> dict:
    rng = random.Random(seed)
    truth = (1, 0, 0, 1)  # taught meal / pleasant / father / kitchen convention
    windows = []
    for encounter in range(2):
        start = session.clock + 3.  # Observable separation, even for identical scenes.
        for step in range(8):
            elapsed = start - session.clock if step == 0 else .2
            image, audio = samples(truth, rng)
            session.step(packets(image, audio, session.clock + elapsed, session.steps * 2), elapsed)
        windows.append((start, session.clock))
    cue_image, cue_audio = samples(truth, rng, (True, False, False, True))
    revised_image, revised_audio = samples((1, 0, 1, 1), rng, (False, False, True, False))
    cues = packets(cue_image, cue_audio, session.clock, session.steps * 2)
    evidence = packets(revised_image, revised_audio, session.clock + 1, session.steps * 2 + 2, "audio")
    correction = session.revise(cues, evidence, 2, 1., windows[0])
    initial = session.query(cues, "initial", windows[0])
    current = session.query(cues, "current", windows[0])
    second = session.query(cues, "current", windows[1])
    return {"correction": correction, "initial": initial, "current": current, "similar_other_meal": second,
            "cue_image": cue_image, "cue_audio": cue_audio, "window": windows[0],
            "accepted": bool(correction["revised"]) and initial["recall"] == {"atividade": "comer", "impressao": "agradavel", "autor": "pai", "contexto": "cozinha"}
                        and current["recall"] == {"atividade": "comer", "impressao": "agradavel", "autor": "mae", "contexto": "cozinha"}
                        and second["recall"] == initial["recall"]}


def load_pcm(path: Path) -> torch.Tensor:
    with wave.open(str(path), "rb") as stream:
        if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getnframes()) != (1, 2, 8000, 1024):
            raise ValueError("Use mono PCM16 8000 Hz with 1024 samples.")
        return torch.tensor(struct.unpack("<1024h", stream.readframes(1024)), dtype=torch.float32) / 32767


def revision_benchmark(template: EpisodicSession, seed: int, trials: int = 32) -> dict:
    correct, ambiguous_refused = 0, 0
    for trial in range(trials):
        session = EpisodicSession(template.perception, template.boundary)
        result = meals(session, seed + trial)
        correct += int(result["accepted"])
        cue = packets(result["cue_image"], result["cue_audio"], session.clock, 0)
        recall = session.query(cue)
        ambiguous_refused += int(recall["ambiguous"] and recall["recall"] is None)
    return {"trials": trials, "directed_corrections_preserved": correct / max(trials, 1),
            "ambiguous_identical_meals_abstained": ambiguous_refused / max(trials, 1)}


def run(output: Path, seed: int = 17, max_seconds: float = 300) -> dict:
    if type(seed) is not int or not 0 <= seed <= 100000:
        raise ValueError("Invalid episodic seed.")
    budget = Budget(100000, max_seconds)
    output.mkdir(parents=True, exist_ok=False)
    session, report = create(seed, budget)
    records = stories(seed + 14000, 24)
    report["boundaries"] = drive(session, records)
    report["partial_cue_recall"] = partial_queries(session, records, seed + 5000)
    report["meals"] = meals(session, seed + 6000)
    report["revision_benchmark"] = revision_benchmark(session, seed + 7000)
    cue_image = report["meals"].pop("cue_image")
    cue_audio = report["meals"].pop("cue_audio")
    # Export raw permitted query cues, not the training history or labels.
    from PIL import Image
    image = (cue_image.permute(1, 2, 0) * 255).round().to(torch.uint8)
    Image.frombytes("RGB", (32, 32), bytes(image.flatten().tolist())).save(output / "meal-cue.png")
    save_audio(output / "meal-cue.wav", cue_audio)
    budget.check(len(records) + 16)
    save(output / "session.pt", session)
    report.update(format=13, seed=seed, representation="synthetic-experience-v2", torch=str(torch.__version__),
                  tolerance_steps=1, boundary_threshold=.5, field_confidence_threshold=.8,
                  evaluation_world_seed=seed + 14000, boundary_training_seed=seed + 1000,
                  stored_raw_history=False, episodes=len(session.memory.blocks), revisions=len(session.memory.revision_log),
                  tensor_state_bytes=sum(value.numel() * value.element_size() for value in session.memory.state_dict().values()),
                  memory=memory_usage(), scope="single annotated teaching stream; learned semantic recognition and boundaries; explicit index/time windows",
                  accepted=report["boundaries"]["f1"] >= .85 and report["meals"]["accepted"]
                           and report["revision_benchmark"]["directed_corrections_preserved"] >= .95
                           and all(values["complete_recall"] >= .9 and values["false_recall"] <= .05 for values in report["partial_cue_recall"].values())
                           and all(values["known_field_recall"] >= .9 and values["false_known_on_missing"] <= .05 for values in report["perception"].values()))
    (output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report
