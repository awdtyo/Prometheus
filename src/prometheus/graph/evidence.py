"""Residual preparation and pairwise edge evidence.

Every statistical quantity in the graph is computed here, from telemetry only.
The approach is deliberately small:

1. Detrend a channel with a rolling median and keep the residual.
2. Resample the residual onto a uniform 60 s grid.
3. For an ordered pair, cut an event-centred window around each observation
   onset and cross-correlate the two windows over a bounded relative shift.
4. Use a permutation test on the target window to attach a p-value to the
   largest absolute correlation.

The permutation uses a seeded RNG supplied by the caller, so building the same
graph twice produces the same numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from prometheus.ingest.telemetry import ChannelSeries
from prometheus.observations.baseline import rolling_median

__all__ = [
    "EdgeEvidence",
    "ResidualSeries",
    "channel_residual",
    "measure_edge",
]


@dataclass(frozen=True)
class ResidualSeries:
    """A detrended channel on a uniform time grid (epoch seconds)."""

    timestamps: np.ndarray
    values: np.ndarray
    grid_s: float


@dataclass(frozen=True)
class EdgeEvidence:
    """Timing and significance evidence for one ordered observation pair."""

    onset_lag_s: float
    xcorr_lag_s: float | None
    lag_estimate_s: float
    lag_min_s: float
    lag_max_s: float
    correlation: float
    p_value: float
    statistical_support: float
    lag_agreement: float


def _epoch_seconds(timestamps: object) -> np.ndarray:
    """Return integer-since-epoch as float seconds, honouring pandas' unit."""
    asi8 = np.asarray(timestamps.asi8, dtype=np.int64)
    unit = getattr(timestamps, "unit", "ns")
    divisor = {"s": 1.0, "ms": 1_000.0, "us": 1_000_000.0, "ns": 1_000_000_000.0}[
        str(unit)
    ]
    return asi8.astype(float) / divisor


def channel_residual(
    series: ChannelSeries,
    *,
    baseline_s: float = 1800.0,
    grid_s: float = 60.0,
) -> ResidualSeries:
    """Detrend one channel and resample it onto a uniform grid.

    ``values - rolling_median`` removes slow operating-point changes while
    keeping injected steps and their immediate response. Linear interpolation
    fills the gaps between the different native sampling rates; the simulator
    uses a common mission clock, so this invents no calendar time.
    """
    values = np.asarray(series.values, dtype=float)
    mask = np.isfinite(values)
    values = values[mask]
    timestamps = series.timestamp[mask]
    if values.size < 3:
        return ResidualSeries(
            timestamps=np.empty(0, dtype=float),
            values=np.empty(0, dtype=float),
            grid_s=grid_s,
        )

    window = max(int(round(baseline_s / series.sample_interval_s)), 5)
    residual = values - rolling_median(values, window)
    epoch = _epoch_seconds(timestamps)
    start = float(epoch[0])
    stop = float(epoch[-1])
    if stop <= start:
        return ResidualSeries(
            timestamps=np.empty(0, dtype=float),
            values=np.empty(0, dtype=float),
            grid_s=grid_s,
        )
    grid = np.arange(start, stop + 0.5 * grid_s, grid_s, dtype=float)
    interpolated = np.interp(grid, epoch, residual, left=0.0, right=0.0)
    return ResidualSeries(timestamps=grid, values=interpolated, grid_s=grid_s)


def _pearson(first: np.ndarray, second: np.ndarray) -> float:
    """Pearson correlation, returning zero for degenerate windows."""
    if first.size < 3 or second.size < 3:
        return 0.0
    first = first - float(np.mean(first))
    second = second - float(np.mean(second))
    denominator = float(np.sqrt(np.sum(first * first) * np.sum(second * second)))
    if denominator <= 0.0:
        return 0.0
    return float(np.clip(np.sum(first * second) / denominator, -1.0, 1.0))


def _window(
    residual: ResidualSeries,
    onset_epoch_s: float,
    *,
    pre_s: float,
    post_s: float,
) -> np.ndarray:
    """Cut an event-centred window, padding out-of-mission time with zero."""
    relative = np.arange(-pre_s, post_s + 0.5 * residual.grid_s, residual.grid_s)
    times = onset_epoch_s + relative
    if residual.timestamps.size == 0:
        return np.zeros(relative.size, dtype=float)
    return np.interp(
        times,
        residual.timestamps,
        residual.values,
        left=0.0,
        right=0.0,
    )


def _shifted_correlations(
    source: np.ndarray,
    target: np.ndarray,
    shifts: list[int],
) -> np.ndarray:
    """Correlation for each relative shift (positive means target is later)."""
    correlations = np.empty(len(shifts), dtype=float)
    for index, shift in enumerate(shifts):
        if shift > 0:
            first = source[: source.size - shift]
            second = target[shift:]
        elif shift < 0:
            first = source[-shift:]
            second = target[: target.size + shift]
        else:
            first = source
            second = target
        correlations[index] = _pearson(first, second)
    return correlations


def measure_edge(
    source: ResidualSeries,
    target: ResidualSeries,
    *,
    source_onset_epoch_s: float,
    target_onset_epoch_s: float,
    rng: np.random.Generator,
    pre_s: float = 600.0,
    post_s: float = 1800.0,
    max_shift_s: float = 600.0,
    permutations: int = 100,
    lag_tolerance_s: float = 600.0,
) -> EdgeEvidence:
    """Measure timing and significance for one ordered channel pair.

    The two windows are aligned on their own observation onsets. A relative
    cross-correlation shift therefore measures shape disagreement, while
    ``onset_lag_s + shift`` is the physical lag estimate. The permutation
    maximum statistic controls for the fact that the best shift is selected
    from several candidates.
    """
    onset_lag = float(target_onset_epoch_s - source_onset_epoch_s)
    source_window = _window(source, source_onset_epoch_s, pre_s=pre_s, post_s=post_s)
    target_window = _window(target, target_onset_epoch_s, pre_s=pre_s, post_s=post_s)
    grid = source.grid_s if source.grid_s > 0 else target.grid_s
    if grid <= 0 or source_window.size < 3 or target_window.size < 3:
        return EdgeEvidence(
            onset_lag_s=onset_lag,
            xcorr_lag_s=None,
            lag_estimate_s=onset_lag,
            lag_min_s=max(0.0, onset_lag),
            lag_max_s=max(0.0, onset_lag),
            correlation=0.0,
            p_value=1.0,
            statistical_support=0.0,
            lag_agreement=0.5,
        )

    max_shift = max(int(round(max_shift_s / grid)), 1)
    shifts = list(range(-max_shift, max_shift + 1))
    correlations = _shifted_correlations(source_window, target_window, shifts)
    peak_index = int(np.argmax(np.abs(correlations)))
    peak = float(correlations[peak_index])
    peak_abs = abs(peak)
    shift_s = float(shifts[peak_index] * grid)

    exceedances = 0
    for _ in range(permutations):
        permuted = rng.permutation(target_window)
        permuted_correlations = _shifted_correlations(
            source_window, permuted, shifts
        )
        if float(np.max(np.abs(permuted_correlations))) >= peak_abs:
            exceedances += 1
    p_value = (1.0 + exceedances) / (permutations + 1.0)

    support = float(np.clip(peak_abs * (1.0 - p_value), 0.0, 1.0))
    lag_agreement = float(
        1.0 / (1.0 + abs(shift_s) / max(lag_tolerance_s, grid))
    )
    lag_estimate = onset_lag + shift_s
    lag_min = max(0.0, min(onset_lag, lag_estimate) - grid)
    lag_max = max(lag_min, max(onset_lag, lag_estimate) + grid)
    return EdgeEvidence(
        onset_lag_s=onset_lag,
        xcorr_lag_s=shift_s,
        lag_estimate_s=lag_estimate,
        lag_min_s=lag_min,
        lag_max_s=lag_max,
        correlation=peak,
        p_value=float(p_value),
        statistical_support=support,
        lag_agreement=lag_agreement,
    )
