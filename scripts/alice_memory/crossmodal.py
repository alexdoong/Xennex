"""Paired contrastive perception and action-conditioned latent anticipation."""
from __future__ import annotations

import json
import random
import time
from pathlib import Path

import torch
from torch import nn
from torch.nn import functional as F

from .contracts import Action
from .network import LATENT_SIZE, Perception
from .process_metrics import Budget, memory_usage
from .signals import audio_features, bank
from .world import SyntheticWorld


def load(path: Path) -> tuple[Perception, ConsequencePredictor]:
    if path.stat().st_size > 2_000_000:
        raise ValueError("Predictive checkpoint exceeds the size limit.")
    payload = torch.load(path, map_location="cpu", weights_only=True)
    if not isinstance(payload, dict) or set(payload) != {"format", "perception", "predictor"} or payload["format"] != 8:
        raise ValueError("Invalid predictive checkpoint format.")
    with torch.random.fork_rng(devices=[]):
        perception, predictor = Perception(), ConsequencePredictor()
        perception.load_state_dict(payload["perception"], strict=True)
        predictor.load_state_dict(payload["predictor"], strict=True)
    if any(not torch.isfinite(value).all() for model in (perception, predictor) for value in model.state_dict().values()):
        raise ValueError("Predictive checkpoint contains nonfinite weights.")
    perception.freeze()
    predictor.eval()
    return perception, predictor


def contrastive_train(model: Perception, images: torch.Tensor, audio: torch.Tensor,
                      variants: int, seed: int, budget: Budget, steps: int = 400) -> None:
    """One scene per paired cause per minibatch; no anchor or identity loss.

    The curriculum supplies eight distinct single-object scenes and synchronized
    image/audio pairs. Distinct scene groups are a data-construction assumption,
    not a discovered segmentation/identity mechanism.
    """
    generator = torch.Generator().manual_seed(seed)
    optimizer = torch.optim.Adam(model.parameters(), lr=.003)
    for step in range(steps):
        budget.check(step)
        indices = torch.arange(8) * variants + torch.randint(variants, (8,), generator=generator)
        visual = model.encode(images[indices], "image")
        acoustic = model.encode(audio[indices], "audio")
        similarity = visual @ acoustic.T / .1
        target = torch.arange(8)
        loss = (F.cross_entropy(similarity, target) + F.cross_entropy(similarity.T, target)) * .5
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
    model.freeze()


@torch.no_grad()
def paired_scores(model: Perception, seed: int) -> dict:
    images, audio, labels = bank(seed, 12)
    visual, acoustic = model.encode(images, "image"), model.encode(audio, "audio")
    # Labels are evaluated only after encoding; they never enter either encoder.
    prediction = labels[(visual @ acoustic.T).argmax(-1)]
    reversed_prediction = labels[(acoustic @ visual.T).argmax(-1)]
    shuffled = labels[(visual @ acoustic.roll(12, 0).T).argmax(-1)]
    return {"image_to_audio": (prediction == labels).float().mean().item(),
            "audio_to_image": (reversed_prediction == labels).float().mean().item(),
            "shuffled_correspondence": (shuffled == labels).float().mean().item(),
            "latent_variance": torch.cat((visual, acoustic)).var(0).mean().item(),
            "latents": (visual, acoustic)}


class ConsequencePredictor(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.cell = nn.GRUCell(LATENT_SIZE + 8, 64)
        self.mean = nn.Linear(64, LATENT_SIZE)
        self.log_variance = nn.Linear(64, LATENT_SIZE)

    def forward(self, current: torch.Tensor, focus: torch.Tensor, elapsed: torch.Tensor,
                hidden: torch.Tensor, present: torch.Tensor,
                observed_focus: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        inputs = torch.cat((current, F.one_hot(focus, 3).float(), torch.log1p(elapsed), present,
                            F.one_hot(observed_focus, 3).float()), -1)
        state = self.cell(inputs, hidden)
        return F.normalize(self.mean(state), dim=-1), self.log_variance(state).clamp(-6, 2), state


@torch.no_grad()
def curriculum(model: Perception, seed: int, count: int = 64, length: int = 16) -> tuple:
    """The model sees only encoded current pixels, issued focus and elapsed time."""
    rng = random.Random(seed)
    observations, actions, intervals, presence = [], [], [], []
    for episode in range(count):
        world = SyntheticWorld(seed + episode)
        first = world.advance(.1)[0]
        values = [first.payload]
        visible = [first.present]
        targets, gaps = [], []
        for step in range(length):
            # First expose all spatial slots; later test prediction on revisits.
            target = (step + 1) % 3 if step < 3 else rng.randrange(3)
            gap = rng.uniform(.1, .8)
            packets = world.advance(gap, Action("focus", step, world.clock, target=target))
            image = packets[0]
            values.append(image.payload)
            visible.append(image.present)
            targets.append(target)
            gaps.append(gap)
        encoded = model.encode(torch.stack(values), "image")
        observations.append(encoded * torch.tensor(visible).float().unsqueeze(-1))
        actions.append(targets)
        intervals.append(gaps)
        presence.append(visible)
    return (torch.stack(observations), torch.tensor(actions), torch.tensor(intervals).unsqueeze(-1),
            torch.tensor(presence).float().unsqueeze(-1))


def train_predictor(model: ConsequencePredictor, data: tuple, seed: int,
                    budget: Budget, steps: int = 1200) -> None:
    features, actions, elapsed, present = data
    generator = torch.Generator().manual_seed(seed)
    optimizer = torch.optim.Adam(model.parameters(), lr=.003)
    for step in range(steps):
        budget.check(step)
        indices = torch.randint(len(features), (32,), generator=generator)
        state = torch.zeros(len(indices), 64)
        losses = []
        for moment in range(actions.shape[1]):
            observed_focus = actions[indices, moment - 1] if moment else torch.zeros(len(indices), dtype=torch.long)
            mean, log_variance, state = model(features[indices, moment], actions[indices, moment],
                                               elapsed[indices, moment], state, present[indices, moment], observed_focus)
            if moment >= 2:
                error = (mean - features[indices, moment + 1]).square()
                valid = present[indices, moment + 1]
                losses.append(((error + .05 * (error * torch.exp(-log_variance) + log_variance)) * valid).sum()
                              / (valid.sum() * LATENT_SIZE).clamp_min(1))
        optimizer.zero_grad(set_to_none=True)
        torch.stack(losses).mean().backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1)
        optimizer.step()
    model.eval()


@torch.no_grad()
def prediction_scores(model: ConsequencePredictor, data: tuple,
                      reset: bool = False, shuffle_actions: bool = False) -> dict:
    features, actions, elapsed, present = data
    state = torch.zeros(len(features), 64)
    error, baseline, uncertainty = [], [], []
    for moment in range(actions.shape[1]):
        action = actions[:, moment].roll(1) if shuffle_actions else actions[:, moment]
        observed_focus = actions[:, moment - 1] if moment else torch.zeros(len(features), dtype=torch.long)
        mean, log_variance, state = model(features[:, moment], action, elapsed[:, moment],
                                          torch.zeros_like(state) if reset else state, present[:, moment], observed_focus)
        if moment >= 2:
            valid = present[:, moment + 1]
            denominator = (valid.sum() * LATENT_SIZE).clamp_min(1)
            error.append(((mean - features[:, moment + 1]).square() * valid).sum() / denominator)
            baseline.append(((features[:, moment] - features[:, moment + 1]).square() * valid).sum() / denominator)
            uncertainty.append(log_variance.exp().mean())
    mse, last = torch.stack(error).mean().item(), torch.stack(baseline).mean().item()
    return {"mse": mse, "repeat_last_mse": last, "relative_improvement": 1 - mse / max(last, 1e-12),
            "predicted_variance": torch.stack(uncertainty).mean().item()}


def run(output: Path, seed: int = 17, max_seconds: float = 300) -> dict:
    budget = Budget(100000, max_seconds)
    if type(seed) is not int or not 0 <= seed <= 100000:
        raise ValueError("Seed must be between 0 and 100000.")
    output.mkdir(parents=True, exist_ok=False)
    torch.manual_seed(seed)
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    started = time.perf_counter()
    perception = Perception()
    images, audio, _ = bank(seed + 100, 24)
    contrastive_train(perception, images, audio, 24, seed + 200, budget)
    scores = paired_scores(perception, seed + 300)
    scores.pop("latents")
    paired_seconds = time.perf_counter() - started
    train_data = curriculum(perception, seed + 1000)
    # +2000 diagnosed the first architecture; reserve a fresh split for this variant.
    heldout = curriculum(perception, seed + 3000, 32)
    predictor = ConsequencePredictor()
    training = time.perf_counter()
    train_predictor(predictor, train_data, seed + 4000, budget)
    prediction = prediction_scores(predictor, heldout)
    report = {"format": 8, "seed": seed, "architecture": "GRU with efferent spatial context; v2",
              "evaluation_world_seed": seed + 3000,
              "perception": scores, "prediction": prediction,
              "reset_state": prediction_scores(predictor, heldout, reset=True),
              "shuffled_actions": prediction_scores(predictor, heldout, shuffle_actions=True),
              "paired_training_seconds": paired_seconds,
              "prediction_training_seconds": time.perf_counter() - training,
              "memory": memory_usage(), "stored_runtime_history": False,
              "scope": "paired single-object curriculum and focus-action prediction; not general identity or episodic learning",
              "missing_target_policy": "loss and MSE masked when the future sensor measurement is absent",
              "accepted": scores["image_to_audio"] >= .9 and scores["audio_to_image"] >= .9
                          and scores["latent_variance"] > .005 and prediction["relative_improvement"] >= .2}
    torch.save({"format": 8, "perception": perception.state_dict(), "predictor": predictor.state_dict()}, output / "models.pt")
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
