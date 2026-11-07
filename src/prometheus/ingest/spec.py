"""Parse ``specs.yaml`` into the validated :class:`prometheus.contracts.Spec`.

Nominal ranges are converted alongside the values, so range checks later operate
entirely in canonical units.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from prometheus.contracts import (
    SUBSYSTEMS,
    Channel,
    Dependency,
    Spec,
    Subsystem,
    SubsystemSpec,
)
from prometheus.ingest.errors import IngestError
from prometheus.ingest.units import conversion_for

SPEC_FILE = "specs.yaml"


def _mapping(value: Any, what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise IngestError(f"{what} must be a mapping")
    return value


def _text(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IngestError(f"{what} must be a non-empty string")
    return value


def load_spec(run_dir: Path) -> Spec:
    """Load and normalize the specification for a mission directory.

    Args:
        run_dir: Directory containing ``specs.yaml`` and the telemetry files.

    Raises:
        IngestError: The spec is missing, malformed or inconsistent.
    """
    path = run_dir / SPEC_FILE
    if not path.is_file():
        raise IngestError(f"missing {SPEC_FILE} in {run_dir}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise IngestError(f"cannot read {path}: {exc}") from exc
    document = _mapping(raw, SPEC_FILE)

    run_meta = _mapping(document.get("run"), "run")
    mission = _text(document.get("mission"), "mission")
    scenario = _text(run_meta.get("scenario"), "run.scenario")
    seed = run_meta.get("seed")
    duration_s = float(run_meta.get("duration_s", 0))
    if duration_s <= 0:
        raise IngestError("run.duration_s must be positive")
    origin_raw = _text(run_meta.get("time_origin_utc"), "run.time_origin_utc")
    try:
        time_origin = datetime.fromisoformat(origin_raw)
    except ValueError as exc:
        raise IngestError(f"run.time_origin_utc is not ISO-8601: {origin_raw!r}") from exc

    raw_subsystems = _mapping(document.get("subsystems"), "subsystems")
    layouts: dict[Subsystem, SubsystemSpec] = {}
    for name, payload in raw_subsystems.items():
        try:
            subsystem = Subsystem(name)
        except ValueError as exc:
            raise IngestError(f"unknown subsystem {name!r} in specs") from exc
        entry = _mapping(payload, f"subsystems.{name}")
        raw_channels = _mapping(entry.get("channels"), f"subsystems.{name}.channels")
        channels: list[Channel] = []
        for source_name, channel_payload in raw_channels.items():
            meta = _mapping(channel_payload, f"subsystems.{name}.channels.{source_name}")
            original_unit = _text(meta.get("unit"), f"{name}.{source_name}.unit")
            conversion = conversion_for(original_unit)
            channels.append(
                Channel(
                    name=f"{subsystem.value}.{source_name}",
                    subsystem=subsystem,
                    source_name=source_name,
                    column=_text(meta.get("column"), f"{name}.{source_name}.column"),
                    unit=conversion.canonical,
                    original_unit=original_unit,
                    nominal_min=conversion.apply_scalar(float(meta["nominal_min"])),
                    nominal_max=conversion.apply_scalar(float(meta["nominal_max"])),
                    description=str(meta.get("description", "")),
                )
            )
        layouts[subsystem] = SubsystemSpec(
            subsystem=subsystem,
            file=_text(entry.get("file"), f"subsystems.{name}.file"),
            sample_interval_s=float(entry["sample_interval_s"]),
            timestamp_column=_text(
                entry.get("timestamp_column"), f"subsystems.{name}.timestamp_column"
            ),
            timestamp_format=_text(
                entry.get("timestamp_format"), f"subsystems.{name}.timestamp_format"
            ),
            channels=channels,
        )

    raw_dependencies = document.get("dependencies") or []
    if not isinstance(raw_dependencies, list):
        raise IngestError("dependencies must be a list")
    dependencies: list[Dependency] = []
    for index, payload in enumerate(raw_dependencies):
        entry = _mapping(payload, f"dependencies[{index}]")
        lag = entry.get("lag_seconds")
        if not isinstance(lag, list) or len(lag) != 2:
            raise IngestError(f"dependencies[{index}].lag_seconds must be [min, max]")
        dependencies.append(
            Dependency(
                source=_subsystem(entry.get("source"), f"dependencies[{index}].source"),
                target=_subsystem(entry.get("target"), f"dependencies[{index}].target"),
                mechanism=_text(entry.get("mechanism"), f"dependencies[{index}].mechanism"),
                lag_min_s=float(lag[0]),
                lag_max_s=float(lag[1]),
            )
        )

    try:
        return Spec(
            mission=mission,
            scenario=scenario,
            seed=seed,
            duration_s=duration_s,
            time_origin_utc=time_origin,
            subsystems=layouts,
            dependencies=dependencies,
        )
    except ValidationError as exc:
        raise IngestError(f"invalid specs: {exc}") from exc


def _subsystem(value: Any, what: str) -> Subsystem:
    try:
        return Subsystem(value)
    except ValueError as exc:
        raise IngestError(f"{what} is not a valid subsystem: {value!r}") from exc


def iter_layouts(spec: Spec) -> list[SubsystemSpec]:
    """Return subsystem layouts in canonical order."""
    return [spec.subsystems[subsystem] for subsystem in SUBSYSTEMS]
