"""Orchestration: ingest a mission directory into one normalized run.

The raw series are kept at their native timestamps. :meth:`IngestedRun.aligned`
offers a convenience view on the union timeline, forward-filled only within one
native sample interval and paired with an ``observed`` mask, so no value is
invented or silently extrapolated.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from prometheus.contracts import Spec, Subsystem
from prometheus.ingest.errors import IngestError
from prometheus.ingest.quality import DataQualityReport, assess_quality
from prometheus.ingest.spec import iter_layouts, load_spec
from prometheus.ingest.telemetry import (
    ChannelSeries,
    LoadedSubsystem,
    NormalizedEvent,
    load_events,
    load_subsystem,
)

__all__ = [
    "AlignedView",
    "IngestError",
    "IngestedRun",
    "ingest_run",
]


@dataclass(frozen=True)
class AlignedView:
    """Channels on the union timeline, with an observed-vs-carried mask."""

    frame: pd.DataFrame
    observed: pd.DataFrame
    timestamps: pd.DatetimeIndex


@dataclass(frozen=True)
class IngestedRun:
    """Everything ingest produces for one mission, ready for later stages."""

    run_dir: Path
    spec: Spec
    series: dict[str, ChannelSeries]
    events: list[NormalizedEvent]
    quality: DataQualityReport
    timeline: pd.DatetimeIndex
    rows_by_subsystem: dict[Subsystem, int]

    def aligned(self, *, max_gap_factor: float = 1.0) -> AlignedView:
        """Build an aligned view without extrapolating.

        The index is the union of every channel's native timestamps, so no new
        times are created. Each channel is forward-filled for at most
        ``max_gap_factor`` times its own sample interval; everything else stays
        NaN. ``observed`` is True only where the value was actually sampled.

        Args:
            max_gap_factor: Multiplier on each channel's native interval. ``1.0``
                carries a value only to the next expected sample.
        """
        if max_gap_factor < 0:
            raise ValueError("max_gap_factor must be non-negative")
        frame = pd.DataFrame(index=self.timeline)
        observed = pd.DataFrame(index=self.timeline)
        for name, series in self.series.items():
            values = pd.Series(series.values, index=series.timestamp)
            tolerance = pd.Timedelta(seconds=series.sample_interval_s * max_gap_factor)
            frame[name] = values.reindex(
                self.timeline, method="ffill", tolerance=tolerance
            )
            mask = pd.Series(False, index=self.timeline)
            native = pd.Series(series.values, index=series.timestamp)
            mask.loc[native.index[native.notna()]] = True
            observed[name] = mask
        return AlignedView(frame=frame, observed=observed, timestamps=self.timeline)


def _union_timeline(loaded: dict[Subsystem, LoadedSubsystem]) -> pd.DatetimeIndex:
    """Union of every native timestamp, timezone-aware and sorted.

    Using :meth:`pandas.DatetimeIndex.union` (instead of a NumPy concatenation)
    keeps the UTC timezone, which reindexing requires.
    """
    indexes = [dataset.timestamps for dataset in loaded.values()]
    if not indexes:
        raise IngestError("mission has no telemetry")
    timeline = indexes[0]
    for index in indexes[1:]:
        timeline = timeline.union(index)
    if timeline.tz is None:
        timeline = timeline.tz_localize("UTC")
    return timeline


def ingest_run(run_dir: str | Path) -> IngestedRun:
    """Load, normalize and quality-check one mission directory.

    Only the mission directory is read: ``specs.yaml``, the telemetry CSVs and
    ``events.csv``. Ground truth lives elsewhere and is never opened.

    Raises:
        IngestError: The directory, spec, telemetry or events cannot be parsed.
    """
    path = Path(run_dir).expanduser()
    if not path.is_dir():
        raise IngestError(f"not a directory: {path}")

    spec = load_spec(path)
    loaded: dict[Subsystem, LoadedSubsystem] = {
        layout.subsystem: load_subsystem(layout, path) for layout in iter_layouts(spec)
    }

    series: dict[str, ChannelSeries] = {}
    rows_by_subsystem: dict[Subsystem, int] = {}
    for layout in iter_layouts(spec):
        dataset = loaded[layout.subsystem]
        rows_by_subsystem[layout.subsystem] = len(dataset.timestamps)
        for channel in layout.channels:
            series[channel.name] = ChannelSeries(
                channel=channel,
                sample_interval_s=layout.sample_interval_s,
                timestamp=dataset.timestamps,
                values=dataset.values[channel.name],
            )

    events = load_events(path)
    quality = assess_quality(loaded)

    return IngestedRun(
        run_dir=path,
        spec=spec,
        series=series,
        events=events,
        quality=quality,
        timeline=_union_timeline(loaded),
        rows_by_subsystem=rows_by_subsystem,
    )
