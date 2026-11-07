"""Load telemetry and event CSVs into normalized per-channel series.

Loading never averages, resamples or invents samples: each channel keeps its
native timestamps. Rows with unparseable timestamps are dropped and counted;
non-numeric values become NaN and are counted, never guessed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel

from prometheus.contracts import Channel, Subsystem, SubsystemSpec
from prometheus.ingest.errors import IngestError
from prometheus.ingest.units import conversion_for

_EVENT_FILE = "events.csv"
_EPOCH_UNITS: dict[str, str] = {
    "epoch_seconds": "s",
    "epoch_milliseconds": "ms",
}
_ISO_FORMATS = frozenset({"iso8601_utc", "iso8601_offset"})


@dataclass(frozen=True)
class ChannelSeries:
    """One normalized channel at its native sampling times."""

    channel: Channel
    sample_interval_s: float
    timestamp: pd.DatetimeIndex
    values: np.ndarray


@dataclass(frozen=True)
class LoadedSubsystem:
    """A parsed subsystem file, before quality assessment."""

    layout: SubsystemSpec
    timestamps: pd.DatetimeIndex
    values: dict[str, np.ndarray]
    rows_in_file: int
    duplicate_timestamps: int
    unparsed_timestamps: int
    non_numeric: dict[str, int]


class NormalizedEvent(BaseModel):
    """A command or alarm on the common UTC timeline, subsystem tagged."""

    event_id: str
    timestamp: datetime
    kind: Literal["command", "alarm"]
    subsystem: Subsystem
    severity: Literal["info", "warning", "critical"]
    code: str
    message: str


def parse_timestamps(values: pd.Series, timestamp_format: str) -> pd.Series:
    """Parse a timestamp column to UTC, returning NaT for unparseable values."""
    if timestamp_format in _ISO_FORMATS:
        return pd.to_datetime(values, utc=True, errors="coerce")
    if timestamp_format in _EPOCH_UNITS:
        numeric = pd.to_numeric(values, errors="coerce")
        return pd.to_datetime(
            numeric, unit=_EPOCH_UNITS[timestamp_format], utc=True, errors="coerce"
        )
    raise IngestError(f"unsupported timestamp_format {timestamp_format!r}")


def load_subsystem(layout: SubsystemSpec, run_dir: Path) -> LoadedSubsystem:
    """Load one subsystem CSV according to its layout."""
    path = run_dir / layout.file
    if not path.is_file():
        raise IngestError(f"missing telemetry file {path}")

    try:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    except (OSError, pd.errors.ParserError) as exc:
        raise IngestError(f"cannot read {path}: {exc}") from exc

    required = [layout.timestamp_column, *[channel.column for channel in layout.channels]]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise IngestError(f"{path.name}: missing columns {missing}")

    rows_in_file = len(frame)
    timestamps = parse_timestamps(frame[layout.timestamp_column], layout.timestamp_format)
    unparsed = int(timestamps.isna().sum())

    frame = frame.assign(__timestamp=timestamps)
    frame = frame[frame["__timestamp"].notna()]
    if frame.empty:
        raise IngestError(f"{path.name}: no parseable timestamps")

    duplicate_timestamps = int(frame["__timestamp"].duplicated().sum())
    frame = frame.drop_duplicates("__timestamp", keep="first").sort_values("__timestamp")
    index = pd.DatetimeIndex(frame["__timestamp"])

    values: dict[str, np.ndarray] = {}
    non_numeric: dict[str, int] = {}
    for channel in layout.channels:
        numeric = pd.to_numeric(frame[channel.column], errors="coerce")
        non_numeric[channel.name] = int(numeric.isna().sum())
        converted = conversion_for(channel.original_unit).apply(
            numeric.to_numpy(dtype=float, copy=True)
        )
        values[channel.name] = converted

    return LoadedSubsystem(
        layout=layout,
        timestamps=index,
        values=values,
        rows_in_file=rows_in_file,
        duplicate_timestamps=duplicate_timestamps,
        unparsed_timestamps=unparsed,
        non_numeric=non_numeric,
    )


def load_events(run_dir: Path) -> list[NormalizedEvent]:
    """Load ``events.csv``, tagging each event with its subsystem."""
    path = run_dir / _EVENT_FILE
    if not path.is_file():
        raise IngestError(f"missing {path.name} in {run_dir}")
    try:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    except (OSError, pd.errors.ParserError) as exc:
        raise IngestError(f"cannot read {path}: {exc}") from exc

    required = [
        "timestamp",
        "event_id",
        "kind",
        "subsystem",
        "severity",
        "code",
        "message",
    ]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise IngestError(f"events.csv: missing columns {missing}")

    stamps = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    bad_rows = [int(index) + 2 for index, value in stamps.items() if pd.isna(value)]
    if bad_rows:
        raise IngestError(f"events.csv: unparseable timestamps on rows {bad_rows}")

    events: list[NormalizedEvent] = []
    for row_index, (stamp, row) in enumerate(zip(stamps, frame.to_dict("records"), strict=True)):
        try:
            events.append(
                NormalizedEvent(
                    event_id=str(row["event_id"]),
                    timestamp=stamp.to_pydatetime(),
                    kind=str(row["kind"]),
                    subsystem=Subsystem(row["subsystem"]),
                    severity=str(row["severity"]),
                    code=str(row["code"]),
                    message=str(row["message"]),
                )
            )
        except ValueError as exc:
            raise IngestError(f"events.csv row {row_index + 2}: {exc}") from exc

    return sorted(events, key=lambda event: (event.timestamp, event.event_id))
