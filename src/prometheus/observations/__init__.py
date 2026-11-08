"""Observation extraction: turn telemetry and events into citable facts.

Public entry point: :func:`observe_run` for the CLI and :func:`extract_observations`
for in-process callers. Observations are discrete, deterministic and carry
stable ``OBS-0001`` identifiers, so later stages can cite them without reading
the raw telemetry again.
"""

from prometheus.observations.detect import (
    Detection,
    DetectorConfig,
    detect_channel,
    detect_drifts,
    detect_levels,
    detect_spikes,
    detect_transitions,
    detect_variance_changes,
)
from prometheus.observations.merge import (
    filter_transition_fallbacks,
    merge_detections,
    suppress_overlaps,
)
from prometheus.observations.run import (
    ObservationResult,
    extract_observations,
    observe_run,
    write_observations,
)

__all__ = [
    "Detection",
    "DetectorConfig",
    "ObservationResult",
    "detect_channel",
    "detect_drifts",
    "detect_levels",
    "detect_spikes",
    "detect_transitions",
    "detect_variance_changes",
    "extract_observations",
    "filter_transition_fallbacks",
    "merge_detections",
    "observe_run",
    "suppress_overlaps",
    "write_observations",
]
