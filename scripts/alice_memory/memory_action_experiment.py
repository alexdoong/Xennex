"""Evaluate learned action selection with identical cues and altered memory."""
from __future__ import annotations

import json
import hashlib
import random
from pathlib import Path

import torch
from torch import nn
from torch.nn import functional as F

from .contracts import Observation
from .episodic_experiment import drive, meals, packets
from .episodic_session import EpisodicSession, load
from .experience_signals import samples, stories
from .experience_perception import semantic
from .memory_actor import MemoryActor, RecallPolicy, save, train
from .process_metrics import Budget, memory_usage


def current_only_reference(seed: int) -> nn.Module:
    """A trained forced-choice comparator; no access to past attributes."""
    generator = torch.Generator().manual_seed(seed)
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(seed)
        model = nn.Sequential(nn.Linear(20, 32), nn.GELU(), nn.Linear(32, 4))
    optimizer = torch.optim.Adam(model.parameters(), lr=.003)
    for _ in range(1200):
        attributes = torch.randint(4, (128, 4), generator=generator)
        current = F.one_hot(attributes, 4).float()
        current[:, (1, 2)] = 0
        field = torch.randint(4, (128,), generator=generator)
        target = attributes[torch.arange(128), field]
        inputs = torch.cat((current.flatten(1), F.one_hot(field, 4).float()), -1)
        loss = F.cross_entropy(model(inputs), target)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
    return model.eval().requires_grad_(False)


def evaluate(actor: MemoryActor, records: list[dict], seed: int) -> dict:
    rng = random.Random(seed)
    groups = {}
    for record in records:
        groups.setdefault(record["episode"], []).append(record)
    questions = []
    reference = current_only_reference(seed + 100)
    reference_correct = 0
    for group in groups.values():
        truth = group[0]["truth"]
        image, audio = samples(truth, rng, (True, False, False, True))
        cue = packets(image, audio, actor.session.clock, 0)
        window = (group[0]["clock"], group[-1]["clock"])
        for field in (1, 2):  # Both targets are absent from the current cue.
            questions.append((cue, field, window, truth[field], actor.session.query(cue, window=window)))
            current, _ = semantic(actor.session.interpret(cue)[0])
            with torch.no_grad():
                inputs = torch.cat((current.float(), F.one_hot(torch.tensor(field), 4).float())).unsqueeze(0)
                reference_correct += int(reference(inputs).argmax(-1).item() == truth[field])
    scores = {}
    feedback = {}
    for mode in ("memory", "none", "shuffled"):
        correct, heard = 0, 0
        for index, (cue, field, window, target, _) in enumerate(questions):
            # Rotate independent past experiences; never rotate the query/target.
            replacement = questions[(index + 9) % len(questions)][4]
            result = actor.respond(cue, field, window, control=mode, replacement=replacement)
            action = actor.last_action
            correct += int(action.kind == "emit" and action.signal == target)
            if action.kind == "emit":
                # Physical return differs with the emitted command. Own feedback
                # is not external evidence for autobiographical memory formation.
                command = [0] * 4
                command[field] = action.signal
                visible = tuple(index == field for index in range(4))
                _, sound = samples(tuple(command), rng, visible)
                returned = Observation("audio", sound, actor.session.clock + .2, actor.actions,
                                       origin="self", action_id=action.sequence)
                returned.validate()
                heard += actor.feedback([returned], .2)["accepted"]
        scores[mode] = correct / max(len(questions), 1)
        feedback[mode] = heard
    return {"questions": len(questions), "success": scores,
            "current_only_forced_choice": reference_correct / max(len(questions), 1),
            "gain_over_no_memory_pp": 100 * (scores["memory"] - scores["none"]),
            "self_feedback_received": feedback,
            "last_self_prediction_error": actor.last_error,
            "feedback_limit": "registered by source/action; does not train the policy or become external autobiographical evidence",
            "accepted": scores["memory"] >= .8 and scores["memory"] - scores["none"] >= .2
                        and scores["memory"] - reference_correct / max(len(questions), 1) >= .2
                        and scores["memory"] > scores["shuffled"]}


def run(output: Path, checkpoint: Path, seed: int = 17, max_seconds: float = 300) -> dict:
    if type(seed) is not int or not 0 <= seed <= 100000:
        raise ValueError("Invalid memory action seed.")
    budget = Budget(100000, max_seconds)
    torch.manual_seed(seed)
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    output.mkdir(parents=True, exist_ok=False)
    template = load(checkpoint)
    torch.manual_seed(seed)  # Loading restores the old RNG; policy gets its own seed.
    # New unseen experience stream, learned by the frozen sensory/event models.
    session = EpisodicSession(template.perception, template.boundary)
    records = stories(seed + 13000, 32)
    boundaries = drive(session, records)
    policy = RecallPolicy()
    train(policy, seed + 10000, budget)
    actor = MemoryActor(session, policy)
    report = evaluate(actor, records, seed + 11000)
    correction = meals(session, seed + 12000)
    cue = packets(correction.pop("cue_image"), correction.pop("cue_audio"), session.clock, 0)
    initial = actor.respond(cue, 2, correction["window"], "initial")
    current = actor.respond(cue, 2, correction["window"], "current")
    report["revised_meal_actions"] = {"initial": initial["action"], "current": current["action"],
                                     "accepted": initial["action"]["signal"] == 0 and current["action"]["signal"] == 1}
    budget.check(len(records))
    save(output / "actor.pt", actor)
    report.update(format=14 if session.boundary.mask_unobserved else 12, seed=seed, boundaries=boundaries, memory=memory_usage(),
                  source_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                  evaluation_world_seed=seed + 13000, policy_seed=seed, policy_data_seed=seed + 10000,
                  torch=str(torch.__version__), threads=torch.get_num_threads(),
                  scope="learned discrete answers to taught field symbols; current cues omit target; supervised policy, no reinforcement learning",
                  policy_parameters=sum(value.numel() for value in policy.parameters()),
                  stored_raw_history=False,
                  accepted=report["accepted"] and report["revised_meal_actions"]["accepted"] and correction["accepted"])
    (output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report
