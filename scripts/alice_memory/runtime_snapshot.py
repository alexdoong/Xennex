"""Detached snapshots: persistence threads never access the living agent."""
from __future__ import annotations

import torch


def freeze(value):
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().clone()
    if isinstance(value, dict):
        return {key: freeze(item) for key, item in value.items()}
    if isinstance(value, list):
        return [freeze(item) for item in value]
    if isinstance(value, tuple):
        return tuple(freeze(item) for item in value)
    if value is None or type(value) in (str, bool, int, float, bytes):
        return value
    raise ValueError("Runtime checkpoint contains a nonserializable live object.")


def capture(agent):
    from .conceptual_mind import ConceptualMind
    if isinstance(agent, ConceptualMind):
        return freeze(agent.snapshot())
    from .neural_language import NeuralLanguageCoordinator, checkpoint_payload as neural_payload
    from .language_coordinator import LanguageCoordinator, checkpoint_payload as language_payload
    from .grounded_mind import GroundedMind, checkpoint_payload as grounded_payload
    from .consolidating_mind import ConsolidatingMind, checkpoint_payload as consolidating_payload
    from .temporal_mind import TemporalMind, checkpoint_payload as temporal_payload
    from .continuous_mind import ContinuousMind, checkpoint_payload as continuous_payload
    serializers = ((NeuralLanguageCoordinator, neural_payload), (LanguageCoordinator, language_payload),
                   (GroundedMind, grounded_payload), (ConsolidatingMind, consolidating_payload),
                   (TemporalMind, temporal_payload), (ContinuousMind, continuous_payload))
    for kind, serializer in serializers:
        if isinstance(agent, kind):
            return freeze(serializer(agent))
    raise ValueError("Unsupported persistent Alice runtime.")
