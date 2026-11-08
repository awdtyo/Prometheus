"""Detect discrete observations on one telemetry channel.

The pipeline has five detectors, all deterministic and CPU-only:

* **Level** (``step``/``drift``): a robust pre/post quantile-shift curve is
  high-passed with a rolling median and thresholded. Candidates must be
  sustained to mission end and must not be part of a recurring oscillation.
  A second, slope-based transition detector catches steps whose shape is
  masked by a strong periodic signal (for example the avionics thermal cycle).
* **Drift**: a two-sided CUSUM on the residual against a causal rolling-median
  baseline. It is deliberately restricted to quiet, non-oscillating channels
  without a primary step detection, because its job is only to catch slow
  ramps that the windowed level detector smooths away.
* **Spike**: residual against a centered rolling-median baseline, with a
  robust z-score and a check that the signal returns to baseline.
* **Variance change**: ratio of successive-difference MAD before and after a
  candidate time, with a sustained-change check.
* **Event**: command/alarm rows are converted by :mod:`prometheus.observations.run`.

The level and transition detectors together provide change-point coverage;
the slope detector is a CUSUM-style cumulative test on the derivative of the
smoothed signal. Ground truth is never read here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from itertools import combinations

import numpy as np
import pandas as pd

from prometheus.contracts import ObservationKind, Severity, Subsystem
from prometheus.ingest.telemetry import ChannelSeries
from prometheus.observations.baseline import (
    nominal_span_frac,
    persistent_shift,
    robust_sigma,
    rolling_median,
    sliding_quantile_shift,
)

__all__ = [
    "Detection",
    "DetectorConfig",
    "detect_channel",
    "detect_drifts",
    "detect_levels",
    "detect_spikes",
    "detect_transitions",
    "detect_variance_changes",
]


@dataclass(frozen=True)
class DetectorConfig:
    """Tunable thresholds for observation detection.

    Defaults were chosen for 5-30 s spacecraft telemetry and are deliberately
    conservative: a real fault must be persistent, not just a large sample.
    """

    level_window_s: float = 1800.0
    level_stride_s: float = 60.0
    level_highpass_s: float = 3600.0
    level_min_duration_s: float = 300.0
    level_sigma_mult: float = 4.0
    level_mad_mult: float = 1.5
    level_min_span_frac: float = 0.01

    transition_smooth_s: float = 300.0
    transition_sigma_mult: float = 4.0
    transition_min_duration_s: float = 60.0
    transition_gap_s: float = 60.0
    transition_context_s: float = 900.0
    transition_persistent_frac: float = 0.25
    transition_max_persistent_ratio: float = 4.0

    drift_baseline_s: float = 1800.0
    drift_cusum_slack: float = 0.5
    drift_cusum_threshold: float = 8.0
    drift_max_sign_changes: int = 4
    drift_max_per_channel: int = 1

    spike_window_s: float = 600.0
    spike_sigma_mult: float = 6.0
    spike_max_duration_s: float = 600.0
    spike_context_s: float = 300.0

    variance_window_s: float = 1800.0
    variance_up_ratio: float = 4.0
    variance_down_ratio: float = 0.25
    variance_min_duration_s: float = 600.0

    step_max_width_s: float = 600.0


@dataclass(frozen=True)
class Detection:
    """One candidate observation before stable IDs are assigned."""

    channel: str
    subsystem: Subsystem
    kind: ObservationKind
    t_start: datetime
    t_end: datetime
    magnitude: float
    severity: Severity
    confidence: float
    method: str


def _finite(series: ChannelSeries) -> tuple[np.ndarray, pd.DatetimeIndex]:
    """Drop NaN samples, preserving native timestamps."""
    values = np.asarray(series.values, dtype=float)
    mask = np.isfinite(values)
    return values[mask], series.timestamp[mask]


def _stamp(timestamps: pd.DatetimeIndex, index: int) -> datetime:
    """Convert a sample index to a timezone-aware Python datetime."""
    return timestamps[int(index)].to_pydatetime()


def _runs(mask: np.ndarray, *, min_gap: int = 0) -> list[tuple[int, int]]:
    """Return inclusive-exclusive runs of True, joining runs closer than gap."""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, flag in enumerate(mask):
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, len(mask)))
    if min_gap <= 0 or len(runs) < 2:
        return runs
    merged = [runs[0]]
    for start, end in runs[1:]:
        previous_start, previous_end = merged[-1]
        if start - previous_end <= min_gap:
            merged[-1] = (previous_start, end)
        else:
            merged.append((start, end))
    return merged


def _severity_for(z_score: float, span_frac: float, kind: ObservationKind) -> Severity:
    """Map an effect size to an operator-facing severity."""
    if kind is ObservationKind.VARIANCE:
        if abs(z_score) >= 20:
            return Severity.CRITICAL
        if abs(z_score) >= 6:
            return Severity.WARNING
        return Severity.INFO
    if z_score >= 20 or span_frac >= 0.25:
        return Severity.CRITICAL
    if z_score >= 6 or span_frac >= 0.05:
        return Severity.WARNING
    return Severity.INFO


def _confidence_for(z_score: float, duration_s: float, floor: float) -> float:
    """Convert robust significance and duration into a bounded confidence."""
    significance = max(z_score, 1.0)
    bonus = 0.10 * np.log2(significance / floor)
    duration = 0.10 * min(duration_s / 1800.0, 1.0)
    return float(np.clip(0.55 + bonus + duration, 0.50, 0.99))


def _transition_width_s(
    values: np.ndarray,
    interval_s: float,
    onset_index: int,
    config: DetectorConfig,
) -> float:
    """Estimate the 10-90% width of the level transition around ``onset_index``.

    A short transition is a step; a long one is a drift. The estimate uses a
    300 s centered median, so a single noisy sample cannot decide the kind.
    """
    smooth_window = max(int(round(config.transition_smooth_s / interval_s)), 3)
    smoothed = rolling_median(values, smooth_window)
    context = max(int(round(config.transition_context_s / interval_s)), 1)

    before = smoothed[max(0, onset_index - context) : onset_index]
    after = smoothed[
        min(len(smoothed), onset_index + context) : min(
            len(smoothed), onset_index + 2 * context
        )
    ]
    if before.size == 0 or after.size == 0:
        return 0.0
    pre_level = float(np.median(before))
    post_level = float(np.median(after))
    change = post_level - pre_level
    if abs(change) <= 0.0:
        return 0.0

    direction = 1.0 if change > 0 else -1.0
    low = max(0, onset_index - context)
    high = min(len(smoothed), onset_index + 2 * context)
    segment = direction * (smoothed[low:high] - pre_level)
    target = abs(change)
    crossed_low = np.nonzero(segment >= 0.10 * target)[0]
    crossed_high = np.nonzero(segment >= 0.90 * target)[0]
    if crossed_low.size == 0 or crossed_high.size == 0:
        return 0.0
    return float((crossed_high[0] - crossed_low[0]) * interval_s)


def _classify_level(
    values: np.ndarray,
    interval_s: float,
    onset_index: int,
    config: DetectorConfig,
) -> ObservationKind:
    """Return ``drift`` for a wide transition, ``step`` otherwise."""
    width = _transition_width_s(values, interval_s, onset_index, config)
    return ObservationKind.DRIFT if width > config.step_max_width_s else ObservationKind.STEP


def _recurring_candidates(
    candidates: list[dict[str, float]],
    interval_s: float,
) -> set[int]:
    """Find candidates that belong to a regular oscillation.

    A normal seasonal signal (solar input, avionics temperature, duty-cycled
    loads) produces repeated quantile-shift or slope detections with similar
    magnitudes and nearly constant spacing. Real fault steps appear once and
    are sustained, so they are not part of such a triplet. Triplets may skip
    intermediate peaks, which is why every combination is examined rather than
    only consecutive candidates. Returns sample indices.
    """
    recurring: set[int] = set()
    ordered = sorted(candidates, key=lambda candidate: candidate["peak"])
    if len(ordered) < 3:
        return recurring

    for first, second, third in combinations(ordered, 3):
        group = (first, second, third)
        magnitudes = np.abs([candidate["magnitude"] for candidate in group])
        if magnitudes.min() / max(magnitudes.max(), 1e-12) < 0.5:
            continue
        gaps = np.diff([candidate["peak"] * interval_s for candidate in group])
        if float(gaps.min()) < 1200.0:
            continue
        mean_gap = float(gaps.mean())
        if mean_gap <= 0:
            continue
        if float(gaps.std() / mean_gap) < 0.35:
            recurring.update(int(candidate["peak"]) for candidate in group)
    return recurring


def detect_levels(
    series: ChannelSeries,
    config: DetectorConfig | None = None,
) -> list[Detection]:
    """Detect sustained level changes (steps and drifts) on one channel."""
    config = config or DetectorConfig()
    values, timestamps = _finite(series)
    if values.size < 20:
        return []

    positions, shifts = sliding_quantile_shift(
        values,
        series.sample_interval_s,
        window_s=config.level_window_s,
        stride_s=config.level_stride_s,
    )
    if shifts.size < 5:
        return []

    deviation = shifts - float(np.median(shifts))
    highpass_window = max(int(round(config.level_highpass_s / series.sample_interval_s)), 5)
    slow = rolling_median(deviation, highpass_window)
    highpassed = deviation - slow

    mad = 1.4826 * float(np.median(np.abs(highpassed - np.median(highpassed))))
    noise = robust_sigma(values)
    span = series.channel.nominal_max - series.channel.nominal_min
    threshold = max(
        config.level_sigma_mult * noise,
        config.level_mad_mult * mad,
        1e-12,
    )
    mask = np.abs(highpassed) > threshold

    candidates: list[dict[str, float]] = []
    for start, stop in _runs(mask):
        duration = (positions[stop - 1] - positions[start]) * series.sample_interval_s
        if duration < config.level_min_duration_s:
            continue
        curve_offset = start + int(np.argmax(np.abs(highpassed[start:stop])))
        peak_position = int(positions[curve_offset])
        candidates.append(
            {
                "peak": float(peak_position),
                "magnitude": float(deviation[curve_offset]),
                "start": float(positions[start]),
                "stop": float(positions[stop - 1]),
                "duration": float(duration),
            }
        )
    if not candidates:
        return []

    recurring = _recurring_candidates(candidates, series.sample_interval_s)
    persistent = persistent_shift(values, series.sample_interval_s)
    minimum = max(
        config.level_sigma_mult * noise,
        config.level_min_span_frac * span,
        1e-12,
    )
    if np.sign(persistent) == 0 or abs(persistent) < minimum:
        return []

    detections: list[Detection] = []
    for candidate in candidates:
        peak = int(candidate["peak"])
        if peak in recurring:
            continue
        if np.sign(candidate["magnitude"]) != np.sign(persistent):
            continue

        onset = int(round((candidate["start"] + candidate["stop"]) / 2.0))
        onset = min(max(onset, 0), values.size - 1)
        kind = _classify_level(values, series.sample_interval_s, onset, config)
        magnitude = float(persistent)
        z_score = abs(magnitude) / max(noise, 1e-12)
        span_frac = nominal_span_frac(
            series.channel.nominal_min, series.channel.nominal_max, magnitude
        )
        duration = (_stamp(timestamps, values.size - 1) - _stamp(timestamps, onset)).total_seconds()
        detections.append(
            Detection(
                channel=series.channel.name,
                subsystem=series.channel.subsystem,
                kind=kind,
                t_start=_stamp(timestamps, onset),
                t_end=_stamp(timestamps, values.size - 1),
                magnitude=magnitude,
                severity=_severity_for(z_score, span_frac, kind),
                confidence=_confidence_for(z_score, duration, config.level_sigma_mult),
                method="quantile_shift+persistent",
            )
        )
    return detections


def detect_transitions(
    series: ChannelSeries,
    config: DetectorConfig | None = None,
) -> list[Detection]:
    """Detect abrupt slope changes that persist as a level shift.

    This complements :func:`detect_levels`: a strong periodic baseline can hide
    a step from a windowed quantile comparison, but the step still adds a
    short, unusually steep slope. The derivative is standardized with a robust
    MAD and thresholded; candidates must also pass the end-vs-start
    persistence check, which rejects normal cycle transitions.
    """
    config = config or DetectorConfig()
    values, timestamps = _finite(series)
    if values.size < 20:
        return []

    interval = series.sample_interval_s
    smooth_window = max(int(round(config.transition_smooth_s / interval)), 3)
    smoothed = rolling_median(values, smooth_window)
    derivative = np.gradient(smoothed) / interval
    center = float(np.median(derivative))
    scale = 1.4826 * float(np.median(np.abs(derivative - center)))
    if scale <= 0:
        return []

    threshold = config.transition_sigma_mult * scale
    mask = np.abs(derivative - center) > threshold
    gap = max(int(round(config.transition_gap_s / interval)), 1)
    context = max(int(round(config.transition_context_s / interval)), 1)

    noise = robust_sigma(values)
    persistent = persistent_shift(values, interval)
    span = series.channel.nominal_max - series.channel.nominal_min
    minimum = max(config.level_sigma_mult * noise, config.level_min_span_frac * span, 1e-12)
    if np.sign(persistent) == 0 or abs(persistent) < minimum:
        return []

    candidates: list[dict[str, float]] = []
    for start, stop in _runs(mask, min_gap=gap):
        duration = (stop - start) * interval
        if duration < config.transition_min_duration_s:
            continue
        peak = start + int(np.argmax(np.abs(derivative[start:stop] - center)))

        before = smoothed[max(0, start - context) : max(0, start)]
        after = smoothed[min(len(smoothed), stop) : min(len(smoothed), stop + context)]
        if before.size == 0 or after.size == 0:
            continue
        delta = float(np.median(after) - np.median(before))
        if np.sign(delta) != np.sign(persistent):
            continue
        if abs(delta) < max(
            minimum, config.transition_persistent_frac * abs(persistent)
        ):
            continue
        if abs(delta) > max(
            minimum, config.transition_max_persistent_ratio * abs(persistent)
        ):
            continue
        candidates.append(
            {
                "peak": float(peak),
                "magnitude": delta,
                "start": float(start),
                "stop": float(stop),
                "duration": float(duration),
            }
        )
    if not candidates:
        return []

    recurring = _recurring_candidates(candidates, interval)
    detections: list[Detection] = []
    for candidate in candidates:
        peak = int(candidate["peak"])
        if peak in recurring:
            continue
        delta = float(candidate["magnitude"])
        duration = float(candidate["duration"])
        z_score = abs(delta) / max(noise, 1e-12)
        span_frac = nominal_span_frac(
            series.channel.nominal_min, series.channel.nominal_max, delta
        )
        kind = (
            ObservationKind.DRIFT
            if duration > config.step_max_width_s
            else ObservationKind.STEP
        )
        detections.append(
            Detection(
                channel=series.channel.name,
                subsystem=series.channel.subsystem,
                kind=kind,
                t_start=_stamp(timestamps, peak),
                t_end=_stamp(timestamps, values.size - 1),
                magnitude=delta,
                severity=_severity_for(z_score, span_frac, kind),
                confidence=_confidence_for(z_score, duration, config.transition_sigma_mult),
                method="slope+persistent",
            )
        )
    return detections


def _cusum_level_events(
    values: np.ndarray,
    interval_s: float,
    config: DetectorConfig,
) -> list[dict[str, float]]:
    """Return sustained CUSUM excursions against a causal median baseline.

    The baseline is the median of the preceding ``drift_baseline_s`` and is
    shifted by one sample, so it never includes the residual it is compared
    with. A two-sided CUSUM accumulates standardized residuals; an excursion
    stays open while the statistic remains above the threshold, which is why a
    persistent ramp produces one long event and a returning oscillation
    produces several short ones.
    """
    window = max(int(round(config.drift_baseline_s / interval_s)), 5)
    frame = pd.Series(np.asarray(values, dtype=float))
    baseline = (
        frame.rolling(window, min_periods=max(3, window // 3))
        .median()
        .shift(1)
        .to_numpy()
    )
    residual = np.asarray(values, dtype=float) - baseline
    sigma = robust_sigma(np.asarray(values, dtype=float))
    if sigma <= 0:
        return []
    z_scores = residual / sigma

    positive = 0.0
    negative = 0.0
    positive_start = 0
    negative_start = 0
    events: list[dict[str, float]] = []
    active: dict[str, float] | None = None

    for index, z_score in enumerate(z_scores):
        if not np.isfinite(z_score):
            continue
        positive = max(0.0, positive + z_score - config.drift_cusum_slack)
        negative = max(0.0, negative - z_score - config.drift_cusum_slack)
        if positive == 0.0:
            positive_start = index
        if negative == 0.0:
            negative_start = index

        sign = (
            1
            if positive > config.drift_cusum_threshold
            else (-1 if negative > config.drift_cusum_threshold else 0)
        )
        if active is None:
            if sign:
                active = {
                    "start": float(positive_start if sign > 0 else negative_start),
                    "end": float(index),
                    "sign": float(sign),
                }
        elif int(sign) == int(active["sign"]):
            active["end"] = float(index)
        else:
            events.append(active)
            active = (
                {
                    "start": float(positive_start if sign > 0 else negative_start),
                    "end": float(index),
                    "sign": float(sign),
                }
                if sign
                else None
            )
    if active is not None:
        events.append(active)
    return events


def _derivative_sign_changes(
    values: np.ndarray,
    interval_s: float,
    noise: float,
    config: DetectorConfig,
) -> int:
    """Count strong slope reversals, a cheap periodicity indicator."""
    window = max(int(round(config.transition_smooth_s / interval_s)), 3)
    smoothed = rolling_median(values, window)
    differences = np.diff(smoothed)
    deadband = max(0.5 * noise, 1e-12)
    strong = differences[np.abs(differences) > deadband]
    if strong.size < 2:
        return 0
    signs = np.sign(strong)
    return int(np.count_nonzero(signs[1:] != signs[:-1]))


def _deduplicate_events(
    events: list[dict[str, float]],
) -> list[dict[str, float]]:
    """Collapse events with the same start and direction, keeping the longest."""
    best: dict[tuple[int, int], dict[str, float]] = {}
    for event in events:
        key = (int(event["start"]), int(event["sign"]))
        previous = best.get(key)
        if previous is None or event["end"] > previous["end"]:
            best[key] = event
    return sorted(best.values(), key=lambda event: event["start"])


def _recurring_events(
    events: list[dict[str, float]],
    interval_s: float,
) -> set[int]:
    """Find CUSUM events that belong to a regular oscillation.

    A normal cycle produces repeated excursions with similar duration and
    nearly constant spacing. A persistent drift happens once, so any event in
    such a repeating triplet is discarded.
    """
    recurring: set[int] = set()
    if len(events) < 3:
        return recurring
    for first, second, third in combinations(range(len(events)), 3):
        group = (events[first], events[second], events[third])
        if len({int(event["sign"]) for event in group}) != 1:
            continue
        durations = np.array(
            [(event["end"] - event["start"]) * interval_s for event in group]
        )
        if durations.min() / max(durations.max(), 1e-12) < 0.5:
            continue
        starts = np.array([event["start"] * interval_s for event in group])
        gaps = np.diff(starts)
        if float(gaps.min()) < 1200.0:
            continue
        mean_gap = float(gaps.mean())
        if mean_gap <= 0:
            continue
        if float(gaps.std() / mean_gap) < 0.4:
            recurring.update((first, second, third))
    return recurring


def detect_drifts(
    series: ChannelSeries,
    config: DetectorConfig | None = None,
    *,
    has_primary_step: bool = False,
) -> list[Detection]:
    """Detect slow, sustained ramps that the level detector smooths away.

    The detector is intentionally narrow. It runs only on quiet channels
    (few strong slope reversals) that have no primary step detection, because
    on those channels the level and transition detectors are more accurate.
    """
    config = config or DetectorConfig()
    values, timestamps = _finite(series)
    if values.size < 20 or has_primary_step:
        return []

    noise = robust_sigma(values)
    if noise <= 0:
        return []
    if (
        _derivative_sign_changes(values, series.sample_interval_s, noise, config)
        > config.drift_max_sign_changes
    ):
        return []

    events = _deduplicate_events(
        _cusum_level_events(values, series.sample_interval_s, config)
    )
    events = [
        event
        for event in events
        if (event["end"] - event["start"]) * series.sample_interval_s
        >= config.level_min_duration_s
    ]
    if not events:
        return []

    recurring = _recurring_events(events, series.sample_interval_s)
    persistent = persistent_shift(values, series.sample_interval_s)
    span = series.channel.nominal_max - series.channel.nominal_min
    minimum = max(
        config.level_sigma_mult * noise,
        config.level_min_span_frac * span,
        1e-12,
    )
    if np.sign(persistent) == 0 or abs(persistent) < minimum:
        return []

    detections: list[Detection] = []
    for index, event in enumerate(events):
        if index in recurring:
            continue
        if int(event["sign"]) != int(np.sign(persistent)):
            continue
        onset = int(event["start"])
        width = _transition_width_s(
            values, series.sample_interval_s, onset, config
        )
        if width <= config.step_max_width_s:
            continue

        duration = (event["end"] - event["start"]) * series.sample_interval_s
        z_score = abs(persistent) / max(noise, 1e-12)
        span_frac = nominal_span_frac(
            series.channel.nominal_min, series.channel.nominal_max, persistent
        )
        detections.append(
            Detection(
                channel=series.channel.name,
                subsystem=series.channel.subsystem,
                kind=ObservationKind.DRIFT,
                t_start=_stamp(timestamps, onset),
                t_end=_stamp(timestamps, values.size - 1),
                magnitude=float(persistent),
                severity=_severity_for(z_score, span_frac, ObservationKind.DRIFT),
                confidence=_confidence_for(
                    z_score, duration, config.drift_cusum_threshold
                ),
                method="cusum+persistent",
            )
        )

    detections.sort(key=lambda detection: detection.t_start)
    return detections[: config.drift_max_per_channel]


def detect_spikes(
    series: ChannelSeries,
    config: DetectorConfig | None = None,
) -> list[Detection]:
    """Detect brief excursions that return to the rolling-median baseline."""
    config = config or DetectorConfig()
    values, timestamps = _finite(series)
    if values.size < 20:
        return []

    interval = series.sample_interval_s
    window = max(int(round(config.spike_window_s / interval)), 5)
    baseline = rolling_median(values, window)
    residual = values - baseline
    noise = robust_sigma(values)
    if noise <= 0:
        return []

    z_scores = residual / noise
    mask = np.abs(z_scores) > config.spike_sigma_mult
    context = max(int(round(config.spike_context_s / interval)), 1)

    detections: list[Detection] = []
    for start, stop in _runs(mask):
        duration = (stop - start) * interval
        if duration <= 0 or duration > config.spike_max_duration_s:
            continue
        peak = start + int(np.argmax(np.abs(z_scores[start:stop])))
        before = values[max(0, start - context) : start]
        after = values[stop : min(len(values), stop + context)]
        if before.size == 0 or after.size == 0:
            continue
        pre_level = float(np.median(before))
        post_level = float(np.median(after))
        excursion = float(values[peak] - pre_level)
        net_change = post_level - pre_level
        if abs(net_change) >= max(
            config.transition_sigma_mult * noise, 0.25 * abs(excursion)
        ):
            continue

        z_score = abs(excursion) / max(noise, 1e-12)
        span_frac = nominal_span_frac(
            series.channel.nominal_min, series.channel.nominal_max, excursion
        )
        detections.append(
            Detection(
                channel=series.channel.name,
                subsystem=series.channel.subsystem,
                kind=ObservationKind.SPIKE,
                t_start=_stamp(timestamps, start),
                t_end=_stamp(timestamps, stop - 1),
                magnitude=excursion,
                severity=_severity_for(z_score, span_frac, ObservationKind.SPIKE),
                confidence=_confidence_for(z_score, duration, config.spike_sigma_mult),
                method="rolling_median+zscore",
            )
        )
    return detections


def detect_variance_changes(
    series: ChannelSeries,
    config: DetectorConfig | None = None,
) -> list[Detection]:
    """Detect sustained changes in channel noise or oscillation amplitude.

    The statistic is the ratio of successive-difference MAD after and before a
    candidate time. A single level step contributes only one or two large
    differences, which the median ignores; a genuine noise change moves the
    whole distribution.
    """
    config = config or DetectorConfig()
    values, timestamps = _finite(series)
    if values.size < 40:
        return []

    interval = series.sample_interval_s
    window = max(int(round(config.variance_window_s / interval)), 8)
    stride = max(1, int(round(config.level_stride_s / interval)))

    ratios: list[float] = []
    positions: list[int] = []
    for position in range(0, values.size, stride):
        before = values[max(0, position - window) : position]
        after = values[position : position + window]
        if before.size < max(8, window // 2) or after.size < max(8, window // 2):
            continue
        pre_mad = float(np.median(np.abs(np.diff(before))))
        post_mad = float(np.median(np.abs(np.diff(after))))
        if pre_mad <= 0:
            continue
        ratios.append((post_mad + 1e-12) / (pre_mad + 1e-12))
        positions.append(position)
    if len(ratios) < 5:
        return []

    ratio_array = np.asarray(ratios)
    position_array = np.asarray(positions, dtype=int)
    mask = (ratio_array >= config.variance_up_ratio) | (
        ratio_array <= config.variance_down_ratio
    )

    early = max(int(round(1800.0 / interval)), 8)
    early = min(early, values.size // 2)
    late = early
    if early < 1:
        return []
    pre_mad = float(np.median(np.abs(np.diff(values[:early]))))
    post_mad = float(np.median(np.abs(np.diff(values[-late:]))))
    if pre_mad <= 0:
        return []
    persistent_ratio = (post_mad + 1e-12) / (pre_mad + 1e-12)

    noise = robust_sigma(values)

    detections: list[Detection] = []
    for start, stop in _runs(mask):
        duration = (position_array[stop - 1] - position_array[start]) * interval
        if duration < config.variance_min_duration_s:
            continue
        segment = ratio_array[start:stop]
        peak_offset = int(np.argmax(np.abs(np.log(segment))))
        peak_ratio = float(segment[peak_offset])
        if peak_ratio >= 1.0 and persistent_ratio < config.variance_up_ratio:
            continue
        if peak_ratio < 1.0 and persistent_ratio > config.variance_down_ratio:
            continue

        magnitude = peak_ratio - 1.0
        z_score = abs(np.log2(max(peak_ratio, 1e-12))) * 8.0
        span_frac = nominal_span_frac(
            series.channel.nominal_min, series.channel.nominal_max, magnitude * noise
        )
        detections.append(
            Detection(
                channel=series.channel.name,
                subsystem=series.channel.subsystem,
                kind=ObservationKind.VARIANCE,
                t_start=_stamp(timestamps, int(position_array[start])),
                t_end=_stamp(timestamps, int(position_array[stop - 1])),
                magnitude=magnitude,
                severity=_severity_for(z_score, span_frac, ObservationKind.VARIANCE),
                confidence=_confidence_for(z_score, duration, 6.0),
                method="diff_mad_ratio",
            )
        )
    return detections


def detect_channel(
    series: ChannelSeries,
    config: DetectorConfig | None = None,
) -> list[Detection]:
    """Run every telemetry detector on one channel."""
    config = config or DetectorConfig()
    levels = detect_levels(series, config)
    has_primary_step = any(
        detection.kind is ObservationKind.STEP for detection in levels
    )
    return [
        *levels,
        *detect_transitions(series, config),
        *detect_drifts(series, config, has_primary_step=has_primary_step),
        *detect_spikes(series, config),
        *detect_variance_changes(series, config),
    ]
