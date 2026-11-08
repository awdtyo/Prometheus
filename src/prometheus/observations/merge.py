"""Merge and de-duplicate detections from overlapping detectors.

A single physical change is often found by more than one detector: the
quantile-shift level detector and the slope transition detector both fire on a
step, and a sharp step can also look like a spike. This module applies one
deterministic policy:

* step and drift are the same *level* family; level detections on one channel
  that are separated by at most ``level_gap_s`` become one observation;
* spike and variance detections are removed when they overlap a level
  detection, because the step explains the excursion;
* remaining same-kind detections within ``gap_s`` are merged.

Merging keeps the earliest start, the latest end, the highest confidence and
the highest severity. Magnitude comes from the largest detection, except that
a direct level estimate is preferred over a single slope-window estimate, which
is more sensitive to periodic phase. The kind of a merged level comes from the
slope detector when present, because it measures the transition width directly.
"""

from __future__ import annotations

from prometheus.contracts import ObservationKind, Severity
from prometheus.observations.detect import Detection

__all__ = [
    "filter_transition_fallbacks",
    "merge_detections",
    "suppress_overlaps",
]

_LEVEL_KINDS = frozenset({ObservationKind.STEP, ObservationKind.DRIFT})
_SEVERITY_ORDER = {Severity.INFO: 0, Severity.WARNING: 1, Severity.CRITICAL: 2}


def _family(kind: ObservationKind) -> str:
    return "level" if kind in _LEVEL_KINDS else kind.value


def _overlaps(
    first: Detection,
    second: Detection,
    *,
    margin_s: float,
) -> bool:
    margin = margin_s
    return not (
        first.t_end.timestamp() + margin < second.t_start.timestamp()
        or second.t_end.timestamp() + margin < first.t_start.timestamp()
    )


def _merged(first: Detection, second: Detection) -> Detection:
    """Combine two detections of the same family on the same channel."""
    first_slope = "slope" in first.method
    second_slope = "slope" in second.method
    if first_slope != second_slope:
        # The quantile-shift/persistent estimate is a direct end-vs-start
        # difference; a single slope window is more sensitive to periodic
        # phase, so keep the level estimate for magnitude.
        larger = second if first_slope else first
    else:
        larger = first if abs(first.magnitude) >= abs(second.magnitude) else second

    kind = first.kind
    if _family(first.kind) == "level":
        if second_slope and not first_slope:
            kind = second.kind
        elif first_slope and second_slope:
            kind = larger.kind
    methods = sorted({*first.method.split("+"), *second.method.split("+")})
    return Detection(
        channel=first.channel,
        subsystem=first.subsystem,
        kind=kind,
        t_start=min(first.t_start, second.t_start),
        t_end=max(first.t_end, second.t_end),
        magnitude=larger.magnitude,
        severity=max((first.severity, second.severity), key=_SEVERITY_ORDER.__getitem__),
        confidence=max(first.confidence, second.confidence),
        method="+".join(methods),
    )


def filter_transition_fallbacks(
    detections: list[Detection],
    *,
    level_gap_s: float = 900.0,
) -> list[Detection]:
    """Keep slope detections only where they help.

    The slope detector exists to catch steps masked by a periodic baseline. If
    the primary level detector already found a change on a channel, slope
    detections are useful only when they are close enough to refine its onset;
    distant slope peaks on that channel are normal cycle transitions.
    """
    by_channel: dict[str, list[Detection]] = {}
    for detection in detections:
        by_channel.setdefault(detection.channel, []).append(detection)

    kept: list[Detection] = []
    for channel_detections in by_channel.values():
        levels = [
            detection
            for detection in channel_detections
            if _family(detection.kind) == "level" and "slope" not in detection.method
        ]
        for detection in channel_detections:
            if "slope" not in detection.method or not levels:
                kept.append(detection)
                continue
            if any(
                abs(
                    detection.t_start.timestamp()
                    - level.t_start.timestamp()
                )
                <= level_gap_s
                for level in levels
            ):
                kept.append(detection)
    return kept


def merge_detections(
    detections: list[Detection],
    *,
    gap_s: float = 300.0,
    level_gap_s: float = 900.0,
) -> list[Detection]:
    """Merge overlapping or near-simultaneous detections on the same channel."""
    if not detections:
        return []

    ordered = sorted(
        detections,
        key=lambda detection: (
            detection.channel,
            _family(detection.kind),
            detection.t_start,
            detection.t_end,
            -abs(detection.magnitude),
        ),
    )
    merged: list[Detection] = []
    last_starts: list[float] = []
    for detection in ordered:
        if not merged:
            merged.append(detection)
            last_starts.append(detection.t_start.timestamp())
            continue
        previous = merged[-1]
        same_target = (
            previous.channel == detection.channel
            and _family(previous.kind) == _family(detection.kind)
        )
        if _family(detection.kind) == "level":
            # Level observations run to mission end, so interval overlap would
            # merge unrelated changes. Compare candidate starts instead.
            close = (
                detection.t_start.timestamp() - last_starts[-1] <= level_gap_s
            )
        else:
            close = (
                detection.t_start.timestamp()
                <= previous.t_end.timestamp() + gap_s
            )
        if same_target and close:
            merged[-1] = _merged(previous, detection)
            last_starts[-1] = detection.t_start.timestamp()
        else:
            merged.append(detection)
            last_starts.append(detection.t_start.timestamp())
    return merged


def suppress_overlaps(
    detections: list[Detection],
    *,
    margin_s: float = 300.0,
) -> list[Detection]:
    """Drop spikes/variance changes explained by a level detection.

    A step produces a short derivative transient, which can be mistaken for a
    spike. Level detections are therefore computed first and take precedence.
    """
    levels = [
        detection for detection in detections if _family(detection.kind) == "level"
    ]
    spikes = [
        detection
        for detection in detections
        if detection.kind is ObservationKind.SPIKE
    ]
    variances = [
        detection
        for detection in detections
        if detection.kind is ObservationKind.VARIANCE
    ]

    kept_variances = [
        variance
        for variance in variances
        if not any(_overlaps(variance, level, margin_s=margin_s) for level in levels)
    ]
    kept_spikes = [
        spike
        for spike in spikes
        if not any(_overlaps(spike, level, margin_s=margin_s) for level in levels)
        and not any(
            _overlaps(spike, variance, margin_s=margin_s)
            for variance in kept_variances
        )
    ]
    return [*levels, *kept_spikes, *kept_variances]
