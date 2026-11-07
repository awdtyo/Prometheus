"""Write a simulated run to disk in deliberately heterogeneous formats.

Each subsystem gets its own CSV with a different timestamp convention, sample
rate and column naming, plus a shared event log and a ``specs.yaml`` that
describes all of it. Formatting is fixed-point and timezone-stable so identical
seeds produce byte-identical files.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from prometheus.contracts import Subsystem
from prometheus.sim import channels as schema
from prometheus.sim.model import BASE_DT_S, Run


@dataclass(frozen=True)
class WrittenRun:
    """Paths produced for one run."""

    files: list[Path]
    ground_truth_path: Path


def _origin(run: Run) -> datetime:
    origin = datetime.fromisoformat(run.scenario.time_origin_utc)
    if origin.tzinfo is None:
        origin = origin.replace(tzinfo=UTC)
    return origin


def _format_timestamp(kind: str, origin: datetime, offset_s: float) -> str:
    moment = origin + timedelta(seconds=float(offset_s))
    if kind == "iso8601_utc":
        return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if kind == "epoch_seconds":
        return str(int(round(moment.timestamp())))
    if kind == "epoch_milliseconds":
        return str(int(round(moment.timestamp() * 1000.0)))
    if kind == "iso8601_offset":
        return moment.isoformat(timespec="milliseconds")
    raise ValueError(f"unknown timestamp format {kind!r}")


def _sample_indices(run: Run, interval_s: int) -> tuple[np.ndarray, np.ndarray]:
    count = int(round(run.scenario.duration_s / interval_s)) + 1
    grid = np.arange(count, dtype=float) * float(interval_s)
    base = np.rint(grid / BASE_DT_S).astype(int)
    if base.size and base[-1] >= run.time_s.size:
        base = base[base < run.time_s.size]
        grid = grid[: base.size]
    return grid, base


def _write_telemetry(run: Run, out_dir: Path, subsystem: Subsystem) -> Path:
    layout = schema.LAYOUTS[subsystem]
    grid, base = _sample_indices(run, layout.sample_interval_s)
    origin = _origin(run)
    path = out_dir / layout.file_name

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [layout.timestamp_column] + [channel.column for channel in layout.channels]
        )
        for offset_s, index in zip(grid, base, strict=True):
            row = [_format_timestamp(layout.timestamp_format, origin, offset_s)]
            row.extend(
                f"{float(run.channels[subsystem][channel.key][index]):.4f}"
                for channel in layout.channels
            )
            writer.writerow(row)
    return path


def _write_events(run: Run, out_dir: Path) -> Path:
    path = out_dir / "events.csv"
    origin = _origin(run)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            ["timestamp", "event_id", "kind", "subsystem", "severity", "code", "message"]
        )
        for index, event in enumerate(run.events, start=1):
            writer.writerow(
                [
                    _format_timestamp("iso8601_utc", origin, event.at_s),
                    f"EVT-{index:04d}",
                    event.kind,
                    event.subsystem.value,
                    event.severity,
                    event.code,
                    event.message,
                ]
            )
    return path


def build_specs(run: Run) -> dict[str, Any]:
    """Describe channels, units, nominal ranges and the dependency map."""
    subsystems: dict[str, Any] = {}
    for subsystem, layout in schema.LAYOUTS.items():
        subsystems[subsystem.value] = {
            "file": layout.file_name,
            "sample_interval_s": layout.sample_interval_s,
            "timestamp_column": layout.timestamp_column,
            "timestamp_format": layout.timestamp_format,
            "channels": {
                channel.key: {
                    "column": channel.column,
                    "unit": channel.unit,
                    "nominal_min": channel.nominal_min,
                    "nominal_max": channel.nominal_max,
                    "description": channel.description,
                }
                for channel in layout.channels
            },
        }

    return {
        "mission": "Prometheus synthetic mission",
        "run": {
            "scenario": run.scenario.name,
            "seed": run.seed,
            "duration_s": run.scenario.duration_s,
            "time_origin_utc": run.scenario.time_origin_utc,
        },
        "subsystems": subsystems,
        "dependencies": [
            {
                "source": dependency.source.value,
                "target": dependency.target.value,
                "mechanism": dependency.mechanism,
                "lag_seconds": [dependency.lag_min_s, dependency.lag_max_s],
            }
            for dependency in schema.DEPENDENCIES
        ],
    }


def _write_specs(run: Run, out_dir: Path) -> Path:
    path = out_dir / "specs.yaml"
    path.write_text(
        yaml.safe_dump(build_specs(run), sort_keys=True, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    return path


def _write_ground_truth(run: Run, ground_truth_dir: Path) -> Path:
    ground_truth_dir.mkdir(parents=True, exist_ok=True)
    path = ground_truth_dir / "ground_truth.json"
    path.write_text(
        json.dumps(run.ground_truth, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def write_run(run: Run, out_dir: Path, ground_truth_dir: Path) -> WrittenRun:
    """Write telemetry, events and specs to ``out_dir`` and truth separately.

    Ground truth is intentionally written to a different tree so pipeline code
    has no legitimate reason to open it.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    files = [
        _write_telemetry(run, out_dir, subsystem) for subsystem in schema.LAYOUTS
    ]
    files.append(_write_events(run, out_dir))
    files.append(_write_specs(run, out_dir))
    truth = _write_ground_truth(run, ground_truth_dir)
    return WrittenRun(files=files, ground_truth_path=truth)
