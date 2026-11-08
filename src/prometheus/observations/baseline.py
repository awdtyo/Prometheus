"""Robust baselines and residual statistics for observation extraction.

The baseline is deliberately simple and documented:

* ``robust_sigma`` estimates the white-noise level from successive differences
  (median absolute deviation, scaled for Gaussian noise). It is insensitive to
  a few large excursions.
* ``rolling_median`` is the centered robust baseline used for spike residuals.
* ``sliding_quantile_shift`` compares the 10th/50th/90th percentiles of a
  window before and after each candidate time. Taking the median of the three
  differences tracks a level change while ignoring a few outliers and most
  periodic shape changes. This is the residual used by level detection.
* ``persistent_shift`` compares the first and last hour of a channel. A real
  fault is sustained to mission end, whereas a normal oscillation returns to
  its old level.

Every function works on a finite one-dimensional array. NaN filtering and gap
handling belong to the caller (:mod:`prometheus.observations.detect`).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "persistent_shift",
    "quantile_shift",
    "rolling_median",
    "rolling_mad",
    "robust_sigma",
    "sliding_quantile_shift",
]

_QUANTILES: tuple[float, float, float] = (0.1, 0.5, 0.9)


def robust_sigma(values: np.ndarray) -> float:
    """Estimate white-noise sigma from successive differences.

    For independent noise with standard deviation ``sigma`` the difference has
    standard deviation ``sigma * sqrt(2)``; dividing the MAD of the difference
    by ``sqrt(2)`` recovers ``sigma``. Returns ``0.0`` for fewer than two
    samples.
    """
    if values.size < 2:
        return 0.0
    differences = np.diff(values)
    return float(np.median(np.abs(differences)) / 0.6745 / np.sqrt(2.0))


def rolling_median(values: np.ndarray, window: int) -> np.ndarray:
    """Centered rolling median; edges use the available samples."""
    if window < 1:
        raise ValueError("window must be positive")
    if values.size == 0:
        return values.copy()
    series = pd.Series(values)
    return (
        series.rolling(window, center=True, min_periods=max(1, min(window, 3)))
        .median()
        .to_numpy()
    )


def rolling_mad(values: np.ndarray, window: int) -> np.ndarray:
    """Centered rolling median absolute deviation, scaled to sigma."""
    if window < 1:
        raise ValueError("window must be positive")
    if values.size == 0:
        return values.copy()
    series = pd.Series(values)
    median = series.rolling(window, center=True, min_periods=max(1, min(window, 3))).median()
    deviation = (series - median).abs()
    mad = deviation.rolling(
        window, center=True, min_periods=max(1, min(window, 3))
    ).median()
    return (1.4826 * mad).to_numpy()


def quantile_shift(before: np.ndarray, after: np.ndarray) -> float:
    """Robust level difference between two samples.

    Returns the median of the 10th/50th/90th percentile differences. The
    median across quantiles keeps the estimate stable when only the tails move
    (for example, a brief spike) and when the distribution is skewed.
    """
    if before.size == 0 or after.size == 0:
        return 0.0
    differences = np.quantile(after, _QUANTILES) - np.quantile(before, _QUANTILES)
    return float(np.median(differences))


def sliding_quantile_shift(
    values: np.ndarray,
    interval_s: float,
    *,
    window_s: float = 1800.0,
    stride_s: float = 60.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute a pre/post quantile shift at each sampled candidate time.

    Args:
        values: Finite sample values in time order.
        interval_s: Native sample interval in seconds.
        window_s: Length of the before and after windows.
        stride_s: Spacing between candidate times (at least one sample).

    Returns:
        ``(positions, shifts)`` where ``positions`` are sample indices into
        ``values`` and ``shifts`` are in the channel's units. Positions whose
        windows would be shorter than half the requested length are omitted.
    """
    if interval_s <= 0:
        raise ValueError("interval_s must be positive")
    if values.size == 0:
        return np.empty(0, dtype=int), np.empty(0)

    window = max(int(round(window_s / interval_s)), 8)
    stride = max(1, int(round(stride_s / interval_s)))
    minimum = max(5, window // 2)

    positions: list[int] = []
    shifts: list[float] = []
    for position in range(0, values.size, stride):
        before = values[max(0, position - window) : position]
        after = values[position : position + window]
        if before.size < minimum or after.size < minimum:
            continue
        positions.append(position)
        shifts.append(quantile_shift(before, after))
    return np.asarray(positions, dtype=int), np.asarray(shifts, dtype=float)


def persistent_shift(
    values: np.ndarray,
    interval_s: float,
    *,
    window_s: float = 3600.0,
) -> float:
    """Difference between the end and the start of the run.

    Faults in this project are sustained to mission end, so a genuine level
    change leaves the last hour different from the first hour. A periodic
    signal with a full cycle inside each window averages out.
    """
    window = max(int(round(window_s / interval_s)), 3)
    window = min(window, values.size // 2)
    if window < 1:
        return 0.0
    return quantile_shift(values[:window], values[-window:])


def nominal_span_frac(
    channel_nominal_min: float,
    channel_nominal_max: float,
    magnitude: float,
) -> float:
    """Return ``|magnitude|`` as a fraction of the channel's nominal span."""
    span = channel_nominal_max - channel_nominal_min
    if span <= 0:
        return 0.0
    return float(abs(magnitude) / span)
