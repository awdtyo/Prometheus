"""Load YAML configuration and synthetic fixtures into typed domain models.

The loaders are deliberately strict: they validate the on-disk shape, reject
duplicate or out-of-order records, and cross-check telemetry and events against
the subsystem specifications. Every failure is reported as an
:class:`~autopsy.ingest.errors.IngestError` with the file and, where possible,
the line number.

Ground truth is loaded only by :func:`load_ground_truth`. It is never part of
:class:`~autopsy.schemas.inputs.InvestigationInputs`, which is the object handed
to analysis and hypothesis stages.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from autopsy.ingest.errors import IngestError
from autopsy.schemas.evaluation import GroundTruth
from autopsy.schemas.events import MissionEvent
from autopsy.schemas.inputs import InvestigationInputs
from autopsy.schemas.scenarios import ScenarioSpec
from autopsy.schemas.subsystems import ParameterSpec, SubsystemSpec
from autopsy.schemas.telemetry import TelemetryRecord

PathLike = str | Path

TELEMETRY_COLUMNS = [
    "timestamp",
    "subsystem",
    "parameter",
    "value",
    "unit",
    "source_id",
]
EVENT_COLUMNS = [
    "event_id",
    "timestamp",
    "subsystem",
    "event_type",
    "description",
    "severity",
    "metadata",
]


def _read_yaml(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise IngestError(f"cannot read YAML file {path}: {exc}") from exc
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise IngestError(f"invalid YAML in {path}: {exc}") from exc


def _read_json(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise IngestError(f"cannot read JSON file {path}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise IngestError(f"invalid JSON in {path}: {exc}") from exc


def load_subsystem_spec(path: PathLike) -> SubsystemSpec:
    """Load and validate one subsystem YAML file."""
    spec_path = Path(path)
    payload = _read_yaml(spec_path)
    try:
        return SubsystemSpec.model_validate(payload)
    except ValidationError as exc:
        raise IngestError(f"invalid subsystem specification {spec_path}: {exc}") from exc


def _validate_dependencies(specs: dict[str, SubsystemSpec]) -> None:
    for subsystem_id, spec in specs.items():
        unknown = sorted(set(spec.dependencies) - set(specs))
        if unknown:
            raise IngestError(
                f"subsystem {subsystem_id!r} depends on unknown subsystem(s): {', '.join(unknown)}"
            )

    unresolved = {subsystem_id: set(spec.dependencies) for subsystem_id, spec in specs.items()}
    resolved: set[str] = set()
    while unresolved:
        ready = sorted(
            subsystem_id
            for subsystem_id, dependencies in unresolved.items()
            if dependencies <= resolved
        )
        if not ready:
            cycle = ", ".join(sorted(unresolved))
            raise IngestError(f"subsystem dependency cycle detected among: {cycle}")
        for subsystem_id in ready:
            resolved.add(subsystem_id)
            del unresolved[subsystem_id]


def load_subsystem_specs(directory: PathLike) -> dict[str, SubsystemSpec]:
    """Load every ``*.yaml`` subsystem specification in a directory.

    Returns a mapping keyed by subsystem ID. The directory must contain at
    least one specification, IDs must be unique, dependencies must reference
    known subsystems, and the dependency graph must be acyclic.
    """
    spec_dir = Path(directory)
    paths = sorted(spec_dir.glob("*.yaml"))
    if not paths:
        raise IngestError(f"no subsystem YAML files found in {spec_dir}")

    specs: dict[str, SubsystemSpec] = {}
    for path in paths:
        spec = load_subsystem_spec(path)
        if spec.id in specs:
            raise IngestError(f"duplicate subsystem id {spec.id!r} in {path}")
        specs[spec.id] = spec

    _validate_dependencies(specs)
    return dict(sorted(specs.items()))


def load_scenario_spec(path: PathLike) -> ScenarioSpec:
    """Load and validate one scenario YAML file."""
    scenario_path = Path(path)
    payload = _read_yaml(scenario_path)
    try:
        return ScenarioSpec.model_validate(payload)
    except ValidationError as exc:
        raise IngestError(f"invalid scenario specification {scenario_path}: {exc}") from exc


def _require_columns(reader: csv.DictReader[str], expected: list[str], path: Path) -> None:
    if reader.fieldnames != expected:
        raise IngestError(f"{path}: expected CSV columns {expected}, got {reader.fieldnames}")


def load_telemetry_csv(path: PathLike) -> list[TelemetryRecord]:
    """Load a telemetry CSV fixture.

    The file must use the header
    ``timestamp,subsystem,parameter,value,unit,source_id``. Rows must be
    ordered by timestamp and unique per ``(timestamp, subsystem, parameter)``.
    """
    telemetry_path = Path(path)
    records: list[TelemetryRecord] = []
    seen: set[tuple[datetime, str, str]] = set()
    try:
        with telemetry_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            _require_columns(reader, TELEMETRY_COLUMNS, telemetry_path)
            for line_number, row in enumerate(reader, start=2):
                try:
                    value = float(row["value"])
                except (TypeError, ValueError) as exc:
                    raise IngestError(
                        f"{telemetry_path}:{line_number}: value must be numeric"
                    ) from exc
                payload = {
                    "timestamp": row["timestamp"],
                    "subsystem": row["subsystem"],
                    "parameter": row["parameter"],
                    "value": value,
                    "unit": row["unit"],
                    "source_id": row["source_id"] or None,
                }
                try:
                    record = TelemetryRecord.model_validate(payload)
                except ValidationError as exc:
                    raise IngestError(
                        f"{telemetry_path}:{line_number}: invalid telemetry row: {exc}"
                    ) from exc

                key = (record.timestamp, record.subsystem, record.parameter)
                if key in seen:
                    raise IngestError(
                        f"{telemetry_path}:{line_number}: duplicate sample for "
                        f"{record.subsystem}.{record.parameter} at {record.timestamp.isoformat()}"
                    )
                seen.add(key)

                if records and record.timestamp < records[-1].timestamp:
                    raise IngestError(
                        f"{telemetry_path}:{line_number}: "
                        "telemetry rows must be ordered by timestamp"
                    )
                records.append(record)
    except OSError as exc:
        raise IngestError(f"cannot read telemetry CSV {telemetry_path}: {exc}") from exc

    if not records:
        raise IngestError(f"telemetry fixture {telemetry_path} contains no rows")
    return records


def _validate_events(events: list[MissionEvent], path: Path) -> None:
    seen: set[str] = set()
    for index, event in enumerate(events):
        if event.event_id in seen:
            raise IngestError(f"{path}: duplicate event_id {event.event_id!r}")
        seen.add(event.event_id)
        if index > 0 and event.timestamp < events[index - 1].timestamp:
            raise IngestError(f"{path}: events must be ordered by timestamp")


def _validate_event_payloads(payloads: list[Any], path: Path) -> list[MissionEvent]:
    events: list[MissionEvent] = []
    for index, payload in enumerate(payloads, start=1):
        if not isinstance(payload, dict):
            raise IngestError(f"{path}: event {index} must be a JSON object")
        try:
            events.append(MissionEvent.model_validate(payload))
        except ValidationError as exc:
            raise IngestError(f"{path}: invalid event {index}: {exc}") from exc
    _validate_events(events, path)
    if not events:
        raise IngestError(f"event fixture {path} contains no events")
    return events


def load_events_json(path: PathLike) -> list[MissionEvent]:
    """Load an event log from a JSON array of event objects."""
    event_path = Path(path)
    payload = _read_json(event_path)
    if not isinstance(payload, list):
        raise IngestError(f"{event_path}: event log must be a JSON array")
    return _validate_event_payloads(payload, event_path)


def load_events_csv(path: PathLike) -> list[MissionEvent]:
    """Load an event log from a CSV file.

    The ``metadata`` column contains a compact JSON object or is empty for an
    event without metadata.
    """
    event_path = Path(path)
    payloads: list[dict[str, Any]] = []
    try:
        with event_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            _require_columns(reader, EVENT_COLUMNS, event_path)
            for line_number, row in enumerate(reader, start=2):
                raw_metadata = row["metadata"] or ""
                if raw_metadata:
                    try:
                        metadata = json.loads(raw_metadata)
                    except json.JSONDecodeError as exc:
                        raise IngestError(
                            f"{event_path}:{line_number}: metadata is not valid JSON"
                        ) from exc
                else:
                    metadata = {}
                if not isinstance(metadata, dict):
                    raise IngestError(f"{event_path}:{line_number}: metadata must be a JSON object")
                payloads.append(
                    {
                        "event_id": row["event_id"],
                        "timestamp": row["timestamp"],
                        "subsystem": row["subsystem"],
                        "event_type": row["event_type"],
                        "description": row["description"],
                        "severity": row["severity"],
                        "metadata": metadata,
                    }
                )
    except OSError as exc:
        raise IngestError(f"cannot read event CSV {event_path}: {exc}") from exc

    return _validate_event_payloads(payloads, event_path)


def load_ground_truth(path: PathLike) -> GroundTruth:
    """Load evaluation-only ground truth.

    The returned object must stay on the evaluation side of the boundary and
    must never be included in the inputs passed to hypothesis agents.
    """
    ground_truth_path = Path(path)
    payload = _read_json(ground_truth_path)
    try:
        return GroundTruth.model_validate(payload)
    except ValidationError as exc:
        raise IngestError(f"invalid ground truth {ground_truth_path}: {exc}") from exc


def _validate_parameter_references(
    subsystems: list[SubsystemSpec],
    telemetry: list[TelemetryRecord],
) -> None:
    parameters: dict[tuple[str, str], ParameterSpec] = {
        (subsystem.id, parameter.name): parameter
        for subsystem in subsystems
        for parameter in subsystem.monitored_parameters
    }
    for record in telemetry:
        parameter = parameters.get((record.subsystem, record.parameter))
        if parameter is None:
            raise IngestError(
                f"telemetry references undeclared parameter {record.subsystem}.{record.parameter}"
            )
        if record.unit != parameter.unit:
            raise IngestError(
                f"telemetry unit {record.unit!r} for {record.subsystem}.{record.parameter} "
                f"does not match configured unit {parameter.unit!r}"
            )


def _validate_event_references(
    subsystems: list[SubsystemSpec],
    events: list[MissionEvent],
) -> None:
    event_types = {
        (subsystem.id, event.event_type)
        for subsystem in subsystems
        for event in subsystem.relevant_events
    }
    for event in events:
        if (event.subsystem, event.event_type) not in event_types:
            raise IngestError(
                f"event {event.event_id!r} uses undeclared event type "
                f"{event.subsystem}.{event.event_type}"
            )


def load_investigation_inputs(
    scenario_path: PathLike,
    *,
    repository_root: PathLike | None = None,
    subsystems_dir: PathLike | None = None,
) -> InvestigationInputs:
    """Build the sanitized inputs for one scenario.

    ``repository_root`` is the base for the relative fixture paths in the
    scenario YAML and defaults to the current working directory.
    ``subsystems_dir`` defaults to ``<repository_root>/configs/subsystems``.

    This loader reads the scenario, subsystem specifications, telemetry, and
    event JSON. It never reads ``fixtures/expected/`` and the returned
    :class:`InvestigationInputs` has no fault or ground-truth fields.
    """
    scenario_file = Path(scenario_path)
    scenario = load_scenario_spec(scenario_file)

    root = Path(repository_root) if repository_root is not None else Path.cwd()
    spec_dir = (
        Path(subsystems_dir) if subsystems_dir is not None else root / "configs" / "subsystems"
    )
    specs = load_subsystem_specs(spec_dir)

    missing = [subsystem_id for subsystem_id in scenario.subsystems if subsystem_id not in specs]
    if missing:
        raise IngestError(
            f"scenario {scenario.id!r} references unknown subsystem(s): {', '.join(missing)}"
        )
    selected = [specs[subsystem_id] for subsystem_id in scenario.subsystems]
    selected_ids = set(scenario.subsystems)
    for subsystem in selected:
        missing_dependencies = sorted(set(subsystem.dependencies) - selected_ids)
        if missing_dependencies:
            raise IngestError(
                f"scenario {scenario.id!r} omits dependenc(ies) of {subsystem.id!r}: "
                f"{', '.join(missing_dependencies)}"
            )

    telemetry = load_telemetry_csv(root / scenario.telemetry_file)
    events = load_events_json(root / scenario.event_log_json)
    _validate_parameter_references(selected, telemetry)
    _validate_event_references(selected, events)

    try:
        return InvestigationInputs(
            scenario_id=scenario.id,
            scenario_name=scenario.name,
            mission_start_utc=scenario.mission_start_utc,
            duration_seconds=scenario.duration_seconds,
            sampling_interval_seconds=scenario.sampling_interval_seconds,
            subsystems=selected,
            telemetry=telemetry,
            events=events,
        )
    except ValidationError as exc:
        raise IngestError(f"scenario inputs for {scenario.id!r} are inconsistent: {exc}") from exc
