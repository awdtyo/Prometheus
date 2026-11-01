"""Observation extraction from telemetry, events, and subsystem specifications.

Deterministic, config-driven detectors. No LLM, no network, no ground truth.
"""

from __future__ import annotations

from autopsy.observations.extractor import (
    ObservationConfig,
    extract_observations,
)

__all__ = ["ObservationConfig", "extract_observations"]
