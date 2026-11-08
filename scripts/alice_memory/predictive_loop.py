"""Learned anticipation in the causal loop, with bounded multimodal state.

The predictor was trained on focused images and focus commands. Audio shares the
perceptual space but is retained separately by origin; co-delivery is not treated
as proof of a common object. Action selection is still the declared M1 policy.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import replace
from pathlib import Path

import torch
from torch.nn import functional as F

from .agent_loop import AgentLoop
from .contracts import Observation, StepResult
from .crossmodal import ConsequencePredictor, load as load_models
from .loop_checkpoint import atomic_write
from .loop_experiment import drive
from .network import Perception
from .process_metrics import Budget, memory_usage
from .signals import bank
from .world import SyntheticWorld


class PredictiveState:
    """Fixed-size online state, with no raw observation history or oracle IDs."""

    def __init__(self, core: ConsequencePredictor) -> None:
        self.core = core
        self.hidden = torch.zeros(1, 64)
        self.joint = torch.zeros(1, 16)
        self.visual = torch.zeros(1, 16)
        self.present = torch.zeros(1, 1)
        self.audio = torch.zeros(3, 16)  # environment, person, self
        self.audio_acquired = torch.full((3,), -1., dtype=torch.float64)
        self.mean = torch.zeros(1, 16)
        self.log_variance = torch.zeros(1, 16)
        self.previous_visual = torch.zeros(1, 16)
        self.previous_present = False
        self.forecast_at = -1.
        self.forecast_focus = 0
        self.observed_focus = 0
        self.since_observation = 0.
        self.observations = 0
        self.forecasts = 0
        self.scored = 0
        self.error_sum = 0.
        self.baseline_sum = 0.
        self.last_error = 0.

    def advance(self, signal: torch.Tensor | None, elapsed: float) -> None:
        self.joint = torch.zeros_like(self.joint) if signal is None else signal.detach().clone()
        self.since_observation = self.since_observation + elapsed if signal is None else 0.
        self.observations += int(signal is not None)

    @torch.no_grad()
    def anticipate(self, focus: int, elapsed: float, clock: float, visual_at: float) -> None:
        # Score only matched acquisition/focus/horizon; no score for absent pixels.
        matched = bool(self.present.item()) and abs(visual_at - self.forecast_at) < 1e-8
        if self.forecasts and matched and self.forecast_focus == self.observed_focus:
            self.last_error = (self.mean - self.visual).square().mean().item()
            if self.previous_present:
                self.error_sum += self.last_error
                self.baseline_sum += (self.previous_visual - self.visual).square().mean().item()
                self.scored += 1
        self.mean, self.log_variance, self.hidden = self.core(
            self.visual, torch.tensor([focus]), torch.tensor([[elapsed]]), self.hidden,
            self.present, torch.tensor([self.observed_focus]))
        self.previous_visual = self.visual.clone()
        self.previous_present = bool(self.present.item())
        # Next interval is an explicit persistence estimate, not future knowledge.
        self.forecast_at = clock + elapsed
        self.forecast_focus = focus
        self.forecasts += 1

    def snapshot(self) -> dict:
        return {key: value.clone() if isinstance(value, torch.Tensor) else value
                for key, value in vars(self).items() if key != "core"}

    def restore(self, payload: dict, clock: float, steps: int) -> None:
        reference = self.snapshot()
        if not isinstance(payload, dict) or set(payload) != set(reference):
            raise ValueError("Invalid predictive state fields.")
        for key, example in reference.items():
            value = payload[key]
            if isinstance(example, torch.Tensor):
                if not isinstance(value, torch.Tensor) or value.shape != example.shape or value.dtype != example.dtype or not torch.isfinite(value).all():
                    raise ValueError("Invalid predictive tensor: " + key)
            elif type(example) is bool:
                if type(value) is not bool:
                    raise ValueError("Invalid predictive mask.")
            elif type(example) is int:
                if type(value) is not int or value < 0:
                    raise ValueError("Invalid predictive counter.")
            elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("Invalid predictive scalar.")
        if payload["forecasts"] != steps or payload["scored"] > steps or payload["observations"] > steps:
            raise ValueError("Predictive counters do not match the agent.")
        if any(not 0 <= payload[key] < 3 for key in ("observed_focus", "forecast_focus")):
            raise ValueError("Invalid predictive focus.")
        if not torch.all((payload["present"] == 0) | (payload["present"] == 1)):
            raise ValueError("Invalid visual presence mask.")
        if payload["audio_acquired"].min() < -1 or payload["audio_acquired"].max() > clock:
            raise ValueError("Invalid audio acquisition register.")
        if not -1 <= payload["forecast_at"] <= clock + 60 + 1e-8:
            raise ValueError("Invalid prediction horizon.")
        if any(payload[key] < 0 for key in ("since_observation", "error_sum", "baseline_sum", "last_error")):
            raise ValueError("Invalid prediction error or interval.")
        for key, value in payload.items():
            setattr(self, key, value.clone() if isinstance(value, torch.Tensor) else value)


class PredictiveAgent(AgentLoop):
    def __init__(self, perception: Perception, predictor: ConsequencePredictor,
                 tone_prototypes: torch.Tensor) -> None:
        super().__init__(perception, PredictiveState(predictor))
        self.tone_prototypes = tone_prototypes
        self.visual_at = -1.

    def _start_step(self) -> None:
        self.temporal.observed_focus = self.attention
        self.temporal.visual.zero_()
        self.temporal.present.zero_()
        self.visual_at = -1.

    def _observe_feature(self, packet: Observation, feature: torch.Tensor) -> None:
        if packet.modality == "image" and packet.view == "focused":
            self.temporal.visual = feature.unsqueeze(0)
            self.temporal.present.fill_(1)
            self.visual_at = packet.acquired_at
        if packet.modality == "audio":
            row = ("environment", "person", "self").index(packet.origin)
            self.temporal.audio[row] = feature
            self.temporal.audio_acquired[row] = packet.acquired_at
            # Person's sound may guide the next emission without declaring which
            # visible object caused it. Self sound cannot set another emission.
            if packet.origin == "person":
                self.last_identity = self._decode_identity(feature)

    def _decode_identity(self, feature: torch.Tensor) -> int:
        return (feature @ self.tone_prototypes.T).argmax().item()

    @torch.no_grad()
    def step(self, observations: list[Observation], elapsed: float) -> StepResult:
        result = super().step(observations, elapsed)
        self.temporal.anticipate(self.attention, elapsed, self.clock, self.visual_at)
        return replace(result, hidden_norm=self.temporal.hidden.norm().item())


@torch.no_grad()
def create(models: Path, seed: int) -> tuple[PredictiveAgent, SyntheticWorld]:
    perception, predictor = load_models(models)
    # Calibrate actuator tones in the learned space. These are known motor codes,
    # not simulator identity labels supplied to the recurrent predictor.
    _, audio, _ = bank(seed + 5000, 16)
    encoded = perception.encode(audio, "audio").reshape(8, 16, 16)
    prototypes = F.normalize(encoded.mean(1), dim=-1)
    return PredictiveAgent(perception, predictor, prototypes), SyntheticWorld(seed)


def save(path: Path, agent: PredictiveAgent, world: SyntheticWorld) -> None:
    if abs(agent.clock - world.clock) > 1e-8 or agent.steps != world.steps:
        raise ValueError("Cannot checkpoint an unsynchronized predictive loop.")
    atomic_write(path, {"format": 9, "perception": agent.perception.state_dict(),
                        "predictor": agent.temporal.core.state_dict(),
                        "tone_prototypes": agent.tone_prototypes, "state": agent.temporal.snapshot(),
                        "agent": agent.snapshot(), "world": world.snapshot(),
                        "torch_rng": torch.get_rng_state()})


def load(path: Path) -> tuple[PredictiveAgent, SyntheticWorld]:
    if path.stat().st_size > 2_000_000:
        raise ValueError("Predictive loop checkpoint exceeds the size limit.")
    payload = torch.load(path, map_location="cpu", weights_only=True)
    fields = {"format", "perception", "predictor", "tone_prototypes", "state", "agent", "world", "torch_rng"}
    if not isinstance(payload, dict) or set(payload) != fields or payload["format"] != 9:
        raise ValueError("Invalid predictive loop format.")
    rng = payload["torch_rng"]
    if not isinstance(rng, torch.Tensor) or rng.dtype != torch.uint8 or rng.shape != torch.get_rng_state().shape:
        raise ValueError("Invalid predictive RNG snapshot.")
    with torch.random.fork_rng(devices=[]):
        perception, predictor = Perception(), ConsequencePredictor()
        perception.load_state_dict(payload["perception"], strict=True)
        predictor.load_state_dict(payload["predictor"], strict=True)
        prototypes = payload["tone_prototypes"]
        if not isinstance(prototypes, torch.Tensor) or prototypes.shape != (8, 16) or prototypes.dtype != torch.float32:
            raise ValueError("Invalid tone prototype shape.")
        if any(not torch.isfinite(value).all() for model in (perception, predictor) for value in model.state_dict().values()) or not torch.isfinite(prototypes).all():
            raise ValueError("Nonfinite predictive loop weights.")
        if not torch.allclose(prototypes.norm(dim=-1), torch.ones(8), atol=1e-5):
            raise ValueError("Invalid tone prototype norms.")
        perception.freeze()
        predictor.eval()
        agent = PredictiveAgent(perception, predictor, prototypes.clone())
        agent.restore_state(payload["agent"])
        world = SyntheticWorld.restore(payload["world"])
        if abs(agent.clock - world.clock) > 1e-8 or agent.steps != world.steps:
            raise ValueError("Predictive world and agent are out of sync.")
        agent.temporal.restore(payload["state"], agent.clock, agent.steps)
    torch.set_rng_state(rng)
    return agent, world


def run(output: Path, models: Path | None = None, seed: int = 17, steps: int = 10_000,
        max_seconds: float = 300, checkpoint: Path | None = None, realtime: bool = False) -> dict:
    if type(seed) is not int or not 0 <= seed <= 100_000 or (models is None) == (checkpoint is None):
        raise ValueError("Provide valid seed and exactly one models/checkpoint input.")
    budget = Budget(steps, max_seconds)
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    agent, world = load(checkpoint) if checkpoint else create(models, seed)
    preparation = time.perf_counter() - started
    memory_before = memory_usage()
    report = drive(agent, world, steps, budget, realtime)
    export = time.perf_counter()
    save(output / "loop.pt", agent, world)
    export_seconds = time.perf_counter() - export
    world.render().save(output / "scene.png")
    state = agent.temporal
    mse = state.error_sum / max(state.scored, 1)
    baseline = state.baseline_sum / max(state.scored, 1)
    tensors = [*agent.perception.state_dict().values(), *state.core.state_dict().values(),
               agent.tone_prototypes, *(value for value in state.snapshot().values() if isinstance(value, torch.Tensor))]
    report.update(format=9, seed=world.seed, device="cpu", resumed=checkpoint is not None,
                  source_sha256=hashlib.sha256((checkpoint or models).read_bytes()).hexdigest(),
                  torch=str(torch.__version__), threads=torch.get_num_threads(),
                  scope="learned focused-visual anticipation; separate auditory origins; scripted policy",
                  prediction={"scored": state.scored, "mse": mse, "repeat_last_mse": baseline,
                              "relative_improvement": None if not state.scored else 1 - mse / max(baseline, 1e-12),
                              "horizon": "previous interval estimate; unmatched acquisitions excluded"},
                  memory_at_loop_start=memory_before, memory_at_loop_end=memory_usage(),
                  tensor_state_bytes=sum(value.numel() * value.element_size() for value in tensors),
                  preparation_seconds=preparation, checkpoint_seconds=export_seconds,
                  self_feedback=agent.self_feedback, external_feedback=agent.external_feedback,
                  virtual_seconds=world.clock, stored_observation_history=False,
                  stability_accepted=report["peak_pending"] <= 32 and torch.isfinite(state.hidden).all().item(),
                  prediction_accepted=state.scored > 0 and 1 - mse / max(baseline, 1e-12) >= .2)
    report["accepted"] = report["stability_accepted"] and report["prediction_accepted"]
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
