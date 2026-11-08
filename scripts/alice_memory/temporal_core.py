"""Causal recurrent state with elapsed-time decay; observations are latent signals."""
from __future__ import annotations

import math
from pathlib import Path

import torch
from torch import nn
from torch.nn import functional as F

from .network import LATENT_SIZE, Perception

STATE_SIZE = 48


class TemporalCore(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.rate = nn.Parameter(torch.full((STATE_SIZE,), -3.0))
        self.cell = nn.GRUCell(LATENT_SIZE + 1, STATE_SIZE)
        self.forecast = nn.Linear(STATE_SIZE, 8)

    def decay(self, hidden: torch.Tensor, elapsed: torch.Tensor) -> torch.Tensor:
        return hidden * torch.exp(-F.softplus(self.rate) * elapsed)

    def forward(self, observation: torch.Tensor, hidden: torch.Tensor,
                elapsed: torch.Tensor, since_observation: torch.Tensor | None = None) -> torch.Tensor:
        interval = elapsed if since_observation is None else since_observation
        inputs = torch.cat((observation, torch.log1p(interval)), dim=-1)
        return self.cell(inputs, self.decay(hidden, elapsed))


class TemporalSession:
    """Bounded current state. A missing observation only advances dynamics.

    Silence must be an observed audio representation; None means no measurement.
    Pausing the simulator does not invent observations or advance its time.
    """
    def __init__(self, core: TemporalCore) -> None:
        self.core = core
        self.hidden = torch.zeros(1, STATE_SIZE)
        self.since_observation = 0.0
        self.observations = 0

    @torch.no_grad()
    def advance(self, observation: torch.Tensor | None, elapsed: float) -> torch.Tensor:
        if not math.isfinite(elapsed) or not 0 <= elapsed <= 60:
            raise ValueError("Elapsed time must be finite and between 0 and 60 seconds per step.")
        if observation is not None and (observation.shape != (1, LATENT_SIZE)
                                        or not torch.isfinite(observation).all()):
            raise ValueError("Expected one finite perceptual representation.")
        accumulated = self.since_observation + elapsed
        if not math.isfinite(accumulated) or accumulated > 86400:
            raise ValueError("Unobserved interval exceeds the laboratory limit of one day.")
        interval = torch.tensor([[elapsed]], dtype=self.hidden.dtype)
        if observation is None:
            self.hidden = self.core.decay(self.hidden, interval)
            self.since_observation = accumulated
            return self.hidden.clone()
        self.hidden = self.core(observation, self.hidden, interval,
                                torch.tensor([[accumulated]], dtype=self.hidden.dtype))
        self.since_observation = 0.0
        self.observations += 1
        return self.hidden.clone()

    def prediction(self) -> int:
        with torch.no_grad():
            return self.core.forecast(self.hidden).argmax(dim=-1).item()


def save_checkpoint(path: Path, perception: Perception, session: TemporalSession) -> None:
    torch.save({"format": 3, "perception": perception.state_dict(),
                "core": session.core.state_dict(), "hidden": session.hidden,
                "since_observation": session.since_observation,
                "observations": session.observations}, path)


def load_checkpoint(path: Path) -> tuple[Perception, TemporalSession]:
    if path.stat().st_size > 2_000_000:
        raise ValueError("Temporal checkpoint exceeds the size limit.")
    payload = torch.load(path, map_location="cpu", weights_only=True)
    return restore_checkpoint(payload)


def restore_checkpoint(payload: dict) -> tuple[Perception, TemporalSession]:
    """Validate an embedded temporal checkpoint using the same rules as a file."""
    fields = {"format", "perception", "core", "hidden", "since_observation", "observations"}
    if not isinstance(payload, dict) or set(payload) != fields or payload["format"] != 3:
        raise ValueError("Invalid temporal checkpoint format.")
    perception, core = Perception(), TemporalCore()
    perception.load_state_dict(payload["perception"], strict=True)
    core.load_state_dict(payload["core"], strict=True)
    hidden = payload["hidden"]
    if not isinstance(hidden, torch.Tensor) or hidden.shape != (1, STATE_SIZE) or hidden.dtype != torch.float32:
        raise ValueError("Invalid temporal hidden state.")
    if any(not torch.isfinite(value).all() for model in (perception, core)
           for value in model.state_dict().values()) or not torch.isfinite(hidden).all():
        raise ValueError("Temporal checkpoint contains non-finite values.")
    duration, count = payload["since_observation"], payload["observations"]
    if type(duration) not in (int, float) or not math.isfinite(duration) or not 0 <= duration <= 86400:
        raise ValueError("Invalid unobserved interval.")
    if type(count) is not int or count < 0:
        raise ValueError("Invalid temporal observation count.")
    perception.freeze()
    core.eval()
    session = TemporalSession(core)
    session.hidden = hidden.clone()
    session.since_observation, session.observations = float(duration), count
    return perception, session
