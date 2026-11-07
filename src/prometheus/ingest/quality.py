"""Data-quality assessment for a loaded mission.

The report is purely descriptive: it counts what ingest had to repair (duplicate
timestamps), what it could not parse, sampling gaps, values outside the spec's
nominal range, and every unit conversion applied. It never alters the data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from prometheus.contracts import SUBSYSTEMS, Subsystem
from prometheus.ingest.telemetry import LoadedSubsystem
from prometheus.ingest.units import conversion_for

#: A spacing above this multiple of the declared interval counts as a gap.
GAP_FACTOR: float = 1.5


class ChannelQuality(BaseModel):
    """Quality counters for one channel."""

    channel: str
    sample_interval_s: float
    samples: int
    gap_count: int
    out_of_range: int
    nominal_min: float
    nominal_max: float
    non_numeric: int
    unit_conversion: str | None = None


class DataQualityReport(BaseModel):
    """Counters and detail for everything ingest noticed."""

    rows_read: int
    rows_kept: int
    duplicate_timestamps: int
    unparsed_timestamps: int
    non_numeric: int
    gap_count: int
    max_spacing_s: float
    out_of_range: int
    unit_conversions: list[str] = Field(default_factory=list)
    unknown_units: list[str] = Field(default_factory=list)
    channels: list[ChannelQuality] = Field(default_factory=list)

    @property
    def out_of_range_channels(self) -> list[ChannelQuality]:
        """Channels with at least one out-of-range sample."""
        return [channel for channel in self.channels if channel.out_of_range]

    def render(self) -> str:
        """Render a compact multi-line report for the CLI."""
        lines = [
            "data quality",
            f"  rows: read={self.rows_read} kept={self.rows_kept}",
            f"  duplicates={self.duplicate_timestamps} "
            f"unparsed_timestamps={self.unparsed_timestamps} "
            f"non_numeric={self.non_numeric}",
            f"  gaps={self.gap_count} (max spacing {self.max_spacing_s:.1f}s)",
            f"  out_of_range={self.out_of_range} samples in "
            f"{len(self.out_of_range_channels)}/{len(self.channels)} channels",
            f"  unit conversions={len(self.unit_conversions)}",
        ]
        lines.extend(f"    {item}" for item in self.unit_conversions)
        if self.unknown_units:
            lines.append(f"  unknown units kept unchanged={len(self.unknown_units)}")
            lines.extend(f"    {item}" for item in self.unknown_units)
        if self.out_of_range_channels:
            lines.append("  channels with out-of-range samples:")
            for channel in self.out_of_range_channels:
                lines.append(
                    f"    {channel.channel}: {channel.out_of_range} outside "
                    f"[{channel.nominal_min:.2f}, {channel.nominal_max:.2f}]"
                )
        return "\n".join(lines)


def _spacings(index: pd.DatetimeIndex) -> np.ndarray:
    """Return inter-sample spacings in seconds."""
    if len(index) < 2:
        return np.empty(0)
    return index.to_series().diff().dropna().dt.total_seconds().to_numpy()


def assess_quality(loaded: dict[Subsystem, LoadedSubsystem]) -> DataQualityReport:
    """Build the quality report for a fully loaded mission."""
    channels: list[ChannelQuality] = []
    rows_read = 0
    rows_kept = 0
    duplicates = 0
    unparsed = 0
    non_numeric = 0
    gaps = 0
    max_spacing = 0.0
    out_of_range = 0
    conversions: list[str] = []
    unknown_units: list[str] = []

    for subsystem in SUBSYSTEMS:
        dataset = loaded[subsystem]
        layout = dataset.layout
        rows_read += dataset.rows_in_file
        rows_kept += len(dataset.timestamps)
        duplicates += dataset.duplicate_timestamps
        unparsed += dataset.unparsed_timestamps

        spacings = _spacings(dataset.timestamps)
        gap_count = int((spacings > layout.sample_interval_s * GAP_FACTOR).sum())
        gaps += gap_count
        if spacings.size:
            max_spacing = max(max_spacing, float(spacings.max()))

        for channel in layout.channels:
            values = dataset.values[channel.name]
            bad = int(np.isnan(values).sum())
            outside = int(
                np.sum((values < channel.nominal_min) | (values > channel.nominal_max))
            )
            non_numeric += bad
            out_of_range += outside
            conversion = conversion_for(channel.original_unit)
            unit_conversion = None
            if not conversion.known:
                unknown_units.append(f"{channel.name}: {channel.original_unit}")
            if channel.unit != channel.original_unit:
                unit_conversion = (
                    f"{channel.name}: {channel.original_unit} -> {channel.unit}"
                )
                conversions.append(unit_conversion)
            channels.append(
                ChannelQuality(
                    channel=channel.name,
                    sample_interval_s=layout.sample_interval_s,
                    samples=len(dataset.timestamps),
                    gap_count=gap_count,
                    out_of_range=outside,
                    nominal_min=channel.nominal_min,
                    nominal_max=channel.nominal_max,
                    non_numeric=bad,
                    unit_conversion=unit_conversion,
                )
            )

    return DataQualityReport(
        rows_read=rows_read,
        rows_kept=rows_kept,
        duplicate_timestamps=duplicates,
        unparsed_timestamps=unparsed,
        non_numeric=non_numeric,
        gap_count=gaps,
        max_spacing_s=max_spacing,
        out_of_range=out_of_range,
        unit_conversions=conversions,
        unknown_units=unknown_units,
        channels=channels,
    )
