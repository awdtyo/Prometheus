"""Load, validate, and cross-check the synthetic battery-failure demo data."""

from __future__ import annotations

import copy
import csv
import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from autopsy.ingest import (
    EVENT_COLUMNS,
    TELEMETRY_COLUMNS,
    IngestError,
    load_events_csv,
    load_events_json,
    load_ground_truth,
    load_investigation_inputs,
    load_scenario_spec,
    load_subsystem_spec,
    load_subsystem_specs,
    load_telemetry_csv,
)
from autopsy.schemas import (
    GroundTruth,
    InvestigationInputs,
    ParameterSpec,
    ScenarioSpec,
    SubsystemSpec,
    TelemetryRecord,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "configs"
FIXTURE_DIR = ROOT / "fixtures"
SCENARIO_PATH = CONFIG_DIR / "scenarios" / "battery_failure.yaml"
SUBSYSTEM_DIR = CONFIG_DIR / "subsystems"
TELEMETRY_PATH = FIXTURE_DIR / "telemetry" / "battery_failure_telemetry.csv"
EVENTS_JSON_PATH = FIXTURE_DIR / "events" / "battery_failure_events.json"
EVENTS_CSV_PATH = FIXTURE_DIR / "events" / "battery_failure_events.csv"
GROUND_TRUTH_PATH = FIXTURE_DIR / "expected" / "battery_failure_ground_truth.json"

MISSION_START = datetime(2026, 3, 14, 8, 0, tzinfo=UTC)
EXPECTED_SUBSYSTEMS = {"adcs", "comms", "eps", "obc", "tcs"}


def _scenario_payload() -> dict[str, Any]:
    payload = yaml.safe_load(SCENARIO_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _records_at(
    records: list[TelemetryRecord],
    seconds: int,
) -> list[TelemetryRecord]:
    timestamp = MISSION_START + timedelta(seconds=seconds)
    return [record for record in records if record.timestamp == timestamp]


def _value_at(
    records: list[TelemetryRecord],
    subsystem: str,
    parameter: str,
    seconds: int,
) -> float:
    matches = [
        record
        for record in records
        if record.subsystem == subsystem
        and record.parameter == parameter
        and record.timestamp == MISSION_START + timedelta(seconds=seconds)
    ]
    assert len(matches) == 1
    return matches[0].value


def _parameter_spec(subsystem: SubsystemSpec, name: str) -> ParameterSpec:
    matches = [parameter for parameter in subsystem.monitored_parameters if parameter.name == name]
    assert len(matches) == 1
    return matches[0]


def _all_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(key)
            keys.update(_all_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_all_keys(child))
    return keys


# ---------------------------------------------------------------------------
# Subsystem configuration
# ---------------------------------------------------------------------------


def test_all_subsystem_specs_load() -> None:
    specs = load_subsystem_specs(SUBSYSTEM_DIR)

    assert set(specs) == EXPECTED_SUBSYSTEMS
    for spec in specs.values():
        assert spec.monitored_parameters
        assert spec.relevant_events
        assert spec.expected_downstream_effects


def test_subsystem_dependency_graph_matches_scenario() -> None:
    specs = load_subsystem_specs(SUBSYSTEM_DIR)

    assert specs["eps"].dependencies == []
    assert set(specs["tcs"].dependencies) == {"eps"}
    assert set(specs["obc"].dependencies) == {"eps"}
    assert set(specs["adcs"].dependencies) == {"eps", "obc"}
    assert set(specs["comms"].dependencies) == {"eps", "obc", "adcs"}


def test_every_parameter_has_a_nominal_range_and_unit() -> None:
    specs = load_subsystem_specs(SUBSYSTEM_DIR)

    for spec in specs.values():
        for parameter in spec.monitored_parameters:
            assert parameter.unit
            assert parameter.nominal_min <= parameter.nominal_max
            assert (
                parameter.warning_low is not None
                or parameter.warning_high is not None
                or parameter.nominal_min == parameter.nominal_max
            )


def test_subsystem_loader_wraps_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text("id: [unterminated\n", encoding="utf-8")

    with pytest.raises(IngestError, match="invalid YAML"):
        load_subsystem_spec(path)


def test_subsystem_loader_wraps_schema_errors(tmp_path: Path) -> None:
    path = tmp_path / "incomplete.yaml"
    path.write_text("id: eps\nname: Electrical Power System\n", encoding="utf-8")

    with pytest.raises(IngestError, match="invalid subsystem specification"):
        load_subsystem_spec(path)


# ---------------------------------------------------------------------------
# Scenario configuration
# ---------------------------------------------------------------------------


def test_scenario_loads_and_fault_converts_met_to_utc() -> None:
    scenario = load_scenario_spec(SCENARIO_PATH)

    assert scenario.id == "battery-failure"
    assert scenario.mission_start_utc == MISSION_START
    assert scenario.duration_seconds == 3600.0
    assert scenario.sampling_interval_seconds == 60.0
    assert scenario.seed == 20260314
    assert scenario.subsystems == ["eps", "tcs", "adcs", "comms", "obc"]

    fault = scenario.fault.to_fault_config(scenario.mission_start_utc)
    assert fault.fault_type.value == "power_degradation"
    assert fault.target_subsystem == "eps"
    assert fault.start_time == datetime(2026, 3, 14, 8, 15, tzinfo=UTC)
    assert fault.duration_seconds == 2100.0
    assert fault.magnitude == 0.22


def test_scenario_fixture_paths_are_relative_and_not_ground_truth() -> None:
    scenario = load_scenario_spec(SCENARIO_PATH)

    for value in (scenario.telemetry_file, scenario.event_log_json, scenario.event_log_csv):
        path = Path(value)
        assert not path.is_absolute()
        assert ".." not in path.parts
        assert "expected" not in path.parts


@pytest.mark.parametrize(
    "bad_path",
    [
        "/tmp/telemetry.csv",
        "../telemetry.csv",
        "fixtures/expected/battery_failure_ground_truth.json",
        "~/telemetry.csv",
        "",
    ],
)
def test_scenario_rejects_unsafe_input_paths(bad_path: str) -> None:
    payload = _scenario_payload()
    payload["telemetry_file"] = bad_path

    with pytest.raises(ValidationError):
        ScenarioSpec.model_validate(payload)


def test_scenario_rejects_fault_target_outside_subsystems() -> None:
    payload = _scenario_payload()
    payload["fault"]["target_subsystem"] = "unknown"

    with pytest.raises(ValidationError, match="fault.target_subsystem"):
        ScenarioSpec.model_validate(payload)


def test_scenario_rejects_fault_that_ends_after_the_scenario() -> None:
    payload = _scenario_payload()
    payload["fault"]["start_met_seconds"] = 3000.0

    with pytest.raises(ValidationError, match="fault must end within"):
        ScenarioSpec.model_validate(payload)


def test_scenario_rejects_non_integer_sampling_intervals() -> None:
    payload = _scenario_payload()
    payload["sampling_interval_seconds"] = 70.0

    with pytest.raises(ValidationError, match="integer multiple"):
        ScenarioSpec.model_validate(payload)


# ---------------------------------------------------------------------------
# Telemetry fixture
# ---------------------------------------------------------------------------


def test_telemetry_fixture_loads_with_expected_shape() -> None:
    records = load_telemetry_csv(TELEMETRY_PATH)

    assert len(records) == 1403
    assert len({record.timestamp for record in records}) == 61
    assert records[0].timestamp == MISSION_START
    assert records[-1].timestamp == MISSION_START + timedelta(seconds=3600)
    assert {record.subsystem for record in records} == EXPECTED_SUBSYSTEMS


def test_telemetry_matches_configured_parameters_and_units() -> None:
    specs = load_subsystem_specs(SUBSYSTEM_DIR)
    records = load_telemetry_csv(TELEMETRY_PATH)

    for record in records:
        parameter = _parameter_spec(specs[record.subsystem], record.parameter)
        assert record.unit == parameter.unit
        assert record.source_id == f"{record.subsystem}:{record.parameter}"


def test_telemetry_has_one_sample_per_parameter_per_timestamp() -> None:
    specs = load_subsystem_specs(SUBSYSTEM_DIR)
    records = load_telemetry_csv(TELEMETRY_PATH)
    expected_count = sum(len(spec.monitored_parameters) for spec in specs.values())

    by_timestamp: dict[datetime, list[TelemetryRecord]] = {}
    for record in records:
        by_timestamp.setdefault(record.timestamp, []).append(record)

    assert len(by_timestamp) == 61
    for timestamp_records in by_timestamp.values():
        assert len(timestamp_records) == expected_count
        keys = {(record.subsystem, record.parameter) for record in timestamp_records}
        assert len(keys) == expected_count


def test_initial_telemetry_is_within_nominal_ranges() -> None:
    specs = load_subsystem_specs(SUBSYSTEM_DIR)
    records = _records_at(load_telemetry_csv(TELEMETRY_PATH), 0)

    for record in records:
        parameter = _parameter_spec(specs[record.subsystem], record.parameter)
        assert parameter.nominal_min <= record.value <= parameter.nominal_max, (
            record.subsystem,
            record.parameter,
            record.value,
        )


def test_battery_voltage_follows_the_injected_degradation() -> None:
    records = load_telemetry_csv(TELEMETRY_PATH)

    assert 28.5 < _value_at(records, "eps", "battery_voltage_v", 0) < 28.7
    assert 28.5 < _value_at(records, "eps", "battery_voltage_v", 900) < 28.7
    assert _value_at(records, "eps", "battery_voltage_v", 1440) < 26.2
    assert _value_at(records, "eps", "battery_voltage_v", 2400) < 24.8
    assert _value_at(records, "eps", "battery_voltage_v", 3600) < 24.0


def test_power_shortfall_propagates_to_downstream_telemetry() -> None:
    records = load_telemetry_csv(TELEMETRY_PATH)

    assert _value_at(records, "tcs", "heater_power_w", 1500) > 17.0
    assert _value_at(records, "tcs", "heater_power_w", 1560) < 9.0
    assert _value_at(records, "tcs", "heater_power_w", 1800) < 18.0
    assert _value_at(records, "tcs", "thermal_loop_temperature_c", 3000) > 30.0
    assert _value_at(records, "adcs", "attitude_error_deg", 1800) > 0.5
    assert _value_at(records, "comms", "transmitter_power_w", 1800) < 8.2
    assert _value_at(records, "comms", "transmitter_power_w", 2160) < 7.0
    assert _value_at(records, "comms", "downlink_rate_kbps", 2160) <= 96.0
    assert _value_at(records, "obc", "cpu_load_pct", 1920) > 75.0
    assert _value_at(records, "obc", "watchdog_reset_count", 2040) == 1.0


def test_state_of_charge_never_reaches_the_critical_threshold() -> None:
    records = load_telemetry_csv(TELEMETRY_PATH)
    soc = [record.value for record in records if record.parameter == "state_of_charge_pct"]

    assert min(soc) > 20.0
    assert min(soc) == pytest.approx(69.0, abs=0.2)


def test_telemetry_loader_rejects_out_of_order_rows(tmp_path: Path) -> None:
    path = tmp_path / "telemetry.csv"
    rows = [
        [
            "2026-03-14T08:01:00Z",
            "eps",
            "battery_voltage_v",
            "28.5",
            "V",
            "eps:battery_voltage_v",
        ],
        [
            "2026-03-14T08:00:00Z",
            "eps",
            "battery_voltage_v",
            "28.6",
            "V",
            "eps:battery_voltage_v",
        ],
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(TELEMETRY_COLUMNS)
        writer.writerows(rows)

    with pytest.raises(IngestError, match="ordered by timestamp"):
        load_telemetry_csv(path)


def test_telemetry_loader_rejects_duplicate_samples(tmp_path: Path) -> None:
    path = tmp_path / "telemetry.csv"
    row = [
        "2026-03-14T08:00:00Z",
        "eps",
        "battery_voltage_v",
        "28.6",
        "V",
        "eps:battery_voltage_v",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(TELEMETRY_COLUMNS)
        writer.writerows([row, row])

    with pytest.raises(IngestError, match="duplicate sample"):
        load_telemetry_csv(path)


# ---------------------------------------------------------------------------
# Event fixtures
# ---------------------------------------------------------------------------


def test_event_json_and_csv_fixtures_are_equivalent() -> None:
    json_events = load_events_json(EVENTS_JSON_PATH)
    csv_events = load_events_csv(EVENTS_CSV_PATH)

    assert json_events == csv_events
    assert len(json_events) == 19
    assert [event.event_id for event in json_events] == [
        f"evt_{index:03d}" for index in range(1, 20)
    ]
    assert [event.timestamp for event in json_events] == sorted(
        event.timestamp for event in json_events
    )


def test_every_event_type_is_declared_by_its_subsystem() -> None:
    specs = load_subsystem_specs(SUBSYSTEM_DIR)
    events = load_events_json(EVENTS_JSON_PATH)

    for event in events:
        declared = {spec.event_type for spec in specs[event.subsystem].relevant_events}
        assert event.event_type in declared, (event.event_id, event.event_type)


def test_event_log_follows_the_required_failure_sequence() -> None:
    events = load_events_json(EVENTS_JSON_PATH)
    event_types = [event.event_type for event in events]

    assert event_types[0] == "mission_start"
    assert event_types[-1] == "safe_mode_stable"
    assert event_types.index("battery_degradation_onset") < event_types.index("battery_voltage_sag")
    assert event_types.index("battery_voltage_sag") < event_types.index("load_shedding_started")
    assert event_types.index("load_shedding_started") < event_types.index("power_available_reduced")
    assert event_types.index("power_available_reduced") < event_types.index(
        "thermal_control_degraded"
    )
    assert event_types.index("thermal_control_degraded") < event_types.index(
        "attitude_control_degraded"
    )
    assert event_types.index("attitude_control_degraded") < event_types.index(
        "transmitter_power_reduced"
    )
    assert event_types.index("transmitter_power_reduced") < event_types.index("safe_mode_entered")
    assert event_types.index("safe_mode_entered") < event_types.index("mission_level_failure")


def test_events_fall_inside_the_scenario_window() -> None:
    scenario = load_scenario_spec(SCENARIO_PATH)
    events = load_events_json(EVENTS_JSON_PATH)
    end = scenario.mission_start_utc + timedelta(seconds=scenario.duration_seconds)

    assert all(scenario.mission_start_utc <= event.timestamp <= end for event in events)


def test_event_metadata_timestamps_match_met() -> None:
    scenario = load_scenario_spec(SCENARIO_PATH)
    events = load_events_json(EVENTS_JSON_PATH)

    for event in events:
        expected_met = (event.timestamp - scenario.mission_start_utc).total_seconds()
        assert event.metadata["met_seconds"] == int(expected_met)


def test_event_metadata_matches_sampled_telemetry() -> None:
    records = load_telemetry_csv(TELEMETRY_PATH)
    events = load_events_json(EVENTS_JSON_PATH)
    values_by_timestamp: dict[datetime, dict[str, list[float]]] = {}
    for record in records:
        values_by_timestamp.setdefault(record.timestamp, {}).setdefault(
            record.parameter, []
        ).append(record.value)

    checked = 0
    for event in events:
        parameters = values_by_timestamp.get(event.timestamp, {})
        for key, value in event.metadata.items():
            candidates = parameters.get(key, [])
            if len(candidates) != 1:
                continue
            assert value == pytest.approx(candidates[0], rel=0.05), (
                event.event_id,
                key,
                value,
                candidates[0],
            )
            checked += 1

    assert checked >= 12


def test_event_loader_rejects_bad_metadata(tmp_path: Path) -> None:
    path = tmp_path / "events.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(EVENT_COLUMNS)
        writer.writerow(
            [
                "evt_001",
                "2026-03-14T08:00:00Z",
                "obc",
                "mission_start",
                "Mission start.",
                "info",
                "{not-json}",
            ]
        )

    with pytest.raises(IngestError, match="metadata is not valid JSON"):
        load_events_csv(path)


# ---------------------------------------------------------------------------
# Ground truth and agent-input boundary
# ---------------------------------------------------------------------------


def test_ground_truth_matches_the_scenario_fault() -> None:
    scenario = load_scenario_spec(SCENARIO_PATH)
    ground_truth = load_ground_truth(GROUND_TRUTH_PATH)

    assert isinstance(ground_truth, GroundTruth)
    assert ground_truth.scenario_id == scenario.id
    assert ground_truth.synthetic is True
    assert ground_truth.injected_fault == scenario.fault.to_fault_config(scenario.mission_start_utc)
    assert ground_truth.expected_terminal_state == "safe_mode"
    assert len(ground_truth.expected_causal_sequence) == 17


def test_ground_truth_steps_match_the_event_log() -> None:
    specs = load_subsystem_specs(SUBSYSTEM_DIR)
    events = load_events_json(EVENTS_JSON_PATH)
    events_by_id = {event.event_id: event for event in events}
    ground_truth = load_ground_truth(GROUND_TRUTH_PATH)

    assert [step.step for step in ground_truth.expected_causal_sequence] == list(range(1, 18))
    for step in ground_truth.expected_causal_sequence:
        assert step.evidence_ids
        declared = {spec.event_type for spec in specs[step.subsystem].relevant_events}
        assert step.event_type in declared
        for evidence_id in step.evidence_ids:
            event = events_by_id[evidence_id]
            assert event.timestamp == step.timestamp
            assert event.subsystem == step.subsystem
            assert event.event_type == step.event_type


def test_investigation_inputs_are_sanitized() -> None:
    inputs = load_investigation_inputs(SCENARIO_PATH, repository_root=ROOT)

    assert isinstance(inputs, InvestigationInputs)
    assert inputs.scenario_id == "battery-failure"
    assert len(inputs.subsystems) == 5
    assert len(inputs.telemetry) == 1403
    assert len(inputs.events) == 19

    assert "fault" not in InvestigationInputs.model_fields
    assert "ground_truth" not in InvestigationInputs.model_fields
    assert "expected_causal_sequence" not in InvestigationInputs.model_fields

    keys = _all_keys(inputs.model_dump(mode="json"))
    assert "fault" not in keys
    assert "injected_fault" not in keys
    assert "ground_truth" not in keys
    assert "expected_causal_sequence" not in keys


def test_investigation_inputs_do_not_need_ground_truth(tmp_path: Path) -> None:
    shutil.copytree(CONFIG_DIR, tmp_path / "configs")
    shutil.copytree(FIXTURE_DIR / "telemetry", tmp_path / "fixtures" / "telemetry")
    shutil.copytree(FIXTURE_DIR / "events", tmp_path / "fixtures" / "events")
    assert not (tmp_path / "fixtures" / "expected").exists()

    inputs = load_investigation_inputs(
        tmp_path / "configs" / "scenarios" / "battery_failure.yaml",
        repository_root=tmp_path,
    )

    assert len(inputs.events) == 19
    assert len(inputs.telemetry) == 1403


def test_investigation_inputs_reject_unknown_parameter(tmp_path: Path) -> None:
    shutil.copytree(CONFIG_DIR, tmp_path / "configs")
    shutil.copytree(FIXTURE_DIR / "telemetry", tmp_path / "fixtures" / "telemetry")
    shutil.copytree(FIXTURE_DIR / "events", tmp_path / "fixtures" / "events")

    telemetry_path = tmp_path / "fixtures" / "telemetry" / "battery_failure_telemetry.csv"
    rows = telemetry_path.read_text(encoding="utf-8").splitlines()
    rows[1] = rows[1].replace("attitude_error_deg", "unknown_parameter")
    telemetry_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    with pytest.raises(IngestError, match="undeclared parameter"):
        load_investigation_inputs(
            tmp_path / "configs" / "scenarios" / "battery_failure.yaml",
            repository_root=tmp_path,
        )


def test_ground_truth_loader_rejects_unsorted_steps(tmp_path: Path) -> None:
    payload = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    payload = copy.deepcopy(payload)
    payload["expected_causal_sequence"][0]["timestamp"] = "2026-03-14T09:00:00Z"
    path = tmp_path / "ground_truth.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(IngestError, match="non-decreasing"):
        load_ground_truth(path)
