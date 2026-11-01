"""Deterministic scenario generator.

Regenerates every non-demo scenario from a seeded model so the result is
reproducible. For each scenario it writes:

* ``configs/scenarios/<id>.yaml``            scenario declaration
* ``fixtures/telemetry/<id>_telemetry.csv``  telemetry rows
* ``fixtures/events/<id>_events.json``       mission events
* ``fixtures/expected/<id>_ground_truth.json`` evaluation-only ground truth

The existing ``battery_failure`` files are never touched.
"""

from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "configs" / "scenarios"
TELEMETRY_DIR = ROOT / "fixtures" / "telemetry"
EVENTS_DIR = ROOT / "fixtures" / "events"
EXPECTED_DIR = ROOT / "fixtures" / "expected"

BASE = datetime(2026, 3, 14, 8, 0, tzinfo=timezone.utc)
DURATION_SECONDS = 3600.0
SAMPLING_INTERVAL_SECONDS = 60.0
SEED = 20260314

# Monitored parameters per subsystem (matches configs/subsystems/*.yaml).
PARAMS = {
    "eps": [("bus_voltage_v", "V"), ("battery_voltage_v", "V")],
    "tcs": [("thermal_loop_temperature_c", "degC"), ("radiator_outlet_temperature_c", "degC")],
    "adcs": [("attitude_error_deg", "deg"), ("reaction_wheel_speed_rpm", "rpm")],
    "comms": [("transmitter_power_w", "W"), ("signal_to_noise_db", "dB")],
    "obc": [("cpu_load_pct", "%"), ("cpu_temperature_c", "degC")],
}

# Nominal baseline (midpoint of spec nominal range) per parameter.
NOMINAL = {
    "bus_voltage_v": 28.3,
    "battery_voltage_v": 28.3,
    "thermal_loop_temperature_c": 21.0,
    "radiator_outlet_temperature_c": 15.0,
    "attitude_error_deg": 0.25,
    "reaction_wheel_speed_rpm": 2100.0,
    "transmitter_power_w": 10.0,
    "signal_to_noise_db": 24.0,
    "cpu_load_pct": 40.0,
    "cpu_temperature_c": 32.5,
}

SUBSYSTEMS = ["eps", "tcs", "adcs", "comms", "obc"]


def _seeded(seed: int):
    random.seed(seed)


def _iso(seconds: float) -> str:
    return (BASE + timedelta(seconds=seconds)).isoformat()


def _telemetry_rows(profile: dict[str, list[tuple[float, float]]]) -> list[list[str]]:
    """profile: parameter -> list of (time_seconds, value) control points."""
    n = int(DURATION_SECONDS // SAMPLING_INTERVAL_SECONDS) + 1
    rows: list[list[str]] = []
    for i in range(n):
        t = i * SAMPLING_INTERVAL_SECONDS
        ts = _iso(t)
        for subsystem in SUBSYSTEMS:
            for param, unit in PARAMS[subsystem]:
                points = profile.get(param, [])
                value = _interpolate(points, t, NOMINAL[param])
                # small gaussian noise around the control value
                value += random.gauss(0, 0.02 * max(1.0, abs(value)))
                source_id = f"{subsystem}:{param}"
                rows.append([ts, subsystem, param, f"{value:.3f}", unit, source_id])
    return rows


def _interpolate(points: list[tuple[float, float]], t: float, default: float) -> float:
    if not points:
        return default
    # piecewise linear between control points; hold last value afterwards
    if t <= points[0][0]:
        return points[0][1]
    for i in range(len(points) - 1):
        t0, v0 = points[i]
        t1, v1 = points[i + 1]
        if t0 <= t <= t1:
            frac = (t - t0) / (t1 - t0) if t1 != t0 else 1.0
            return v0 + frac * (v1 - v0)
    return points[-1][1]


# ---------------------------------------------------------------------------
# Scenario definitions
# Each entry: id, name, description, fault, points (param -> control points),
# events (list of dicts), ground_truth (dict).
# ---------------------------------------------------------------------------

SCENARIOS: list[dict] = []


def _scenario(
    sid: str,
    name: str,
    description: str,
    fault_type: str,
    target_subsystem: str,
    start_met: float,
    duration: float,
    magnitude: float,
    points: dict[str, list[tuple[float, float]]],
    events: list[dict],
    ground_truth: dict,
) -> dict:
    return {
        "id": sid,
        "name": name,
        "description": description,
        "seed": SEED,
        "mission_start_utc": _iso(0),
        "duration_seconds": DURATION_SECONDS,
        "sampling_interval_seconds": SAMPLING_INTERVAL_SECONDS,
        "subsystems": list(SUBSYSTEMS),
        "fault": {
            "fault_type": fault_type,
            "target_subsystem": target_subsystem,
            "start_met_seconds": start_met,
            "duration_seconds": duration,
            "magnitude": magnitude,
        },
        "telemetry_file": f"fixtures/telemetry/{sid}_telemetry.csv",
        "event_log_json": f"fixtures/events/{sid}_events.json",
        "event_log_csv": f"fixtures/events/{sid}_events.csv",
        "points": points,
        "events": events,
        "ground_truth": ground_truth,
    }


# 1. solar_shadowing: arrays shadowed -> power generation lost -> bus sags.
SCENARIOS.append(
    _scenario(
        "solar_shadowing",
        "Solar Array Shadowing",
        "An attitude excursion shadows the solar arrays, cutting generation and "
        "sagging the main bus until attitude is recovered.",
        "power_loss",
        "eps",
        600.0,
        1800.0,
        0.35,
        {
            "bus_voltage_v": [(0, 28.3), (600, 28.3), (900, 23.5), (2400, 28.3)],
            "battery_voltage_v": [(0, 28.3), (600, 28.3), (900, 24.0), (2400, 28.3)],
        },
        [
            {
                "timestamp": _iso(900),
                "subsystem": "eps",
                "event_type": "battery_voltage_sag",
                "description": "Reported bus voltage sags as arrays are shadowed.",
                "severity": "high",
            },
            {
                "timestamp": _iso(1200),
                "subsystem": "eps",
                "event_type": "power_available_reduced",
                "description": "Available power drops below mission-operations allocation.",
                "severity": "high",
            },
        ],
        {
            "scenario_id": "solar_shadowing",
            "synthetic": True,
            "injected_fault": {
                "fault_type": "power_loss",
                "target_subsystem": "eps",
                "start_time": _iso(600),
                "duration_seconds": 1800.0,
                "magnitude": 0.35,
                "parameters": {
                    "root_cause": "solar_array_shadowing",
                    "affected_parameter": "bus_voltage_v",
                },
            },
            "expected_causal_sequence": [
                {
                    "step": 1,
                    "timestamp": _iso(600),
                    "subsystem": "eps",
                    "event_type": "array_shadowing_started",
                    "description": "Solar array shadowing cuts generation; bus begins to sag.",
                    "evidence_ids": ["evt_001"],
                },
                {
                    "step": 2,
                    "timestamp": _iso(1200),
                    "subsystem": "eps",
                    "event_type": "bus_undervoltage_critical",
                    "description": "Bus voltage crosses critical low; EPS sheds load.",
                    "evidence_ids": ["evt_002"],
                },
            ],
        },
    )
)

# 2. heater_stuck_on: thermal control heater stuck on -> overheat.
SCENARIOS.append(
    _scenario(
        "heater_stuck_on",
        "Battery Heater Stuck On",
        "The battery heater contactor sticks closed, driving the thermal control "
        "loop into overheat and raising bus load.",
        "thermal_overheat",
        "tcs",
        900.0,
        1200.0,
        0.5,
        {
            "thermal_loop_temperature_c": [(0, 21.0), (900, 21.0), (1500, 42.0), (2100, 21.0)],
            "radiator_outlet_temperature_c": [(0, 15.0), (900, 15.0), (1500, 36.0), (2100, 15.0)],
        },
        [
            {
                "timestamp": _iso(1500),
                "subsystem": "tcs",
                "event_type": "thermal_control_degraded",
                "description": "Thermal control cannot hold battery setpoint.",
                "severity": "medium",
            },
            {
                "timestamp": _iso(1650),
                "subsystem": "tcs",
                "event_type": "battery_temperature_high",
                "description": "Battery temperature exceeds warning threshold.",
                "severity": "high",
            },
        ],
        {
            "scenario_id": "heater_stuck_on",
            "synthetic": True,
            "injected_fault": {
                "fault_type": "thermal_overheat",
                "target_subsystem": "tcs",
                "start_time": _iso(900),
                "duration_seconds": 1200.0,
                "magnitude": 0.5,
                "parameters": {
                    "root_cause": "heater_contactor_stuck_closed",
                    "affected_parameter": "thermal_loop_temperature_c",
                },
            },
            "expected_causal_sequence": [
                {
                    "step": 1,
                    "timestamp": _iso(900),
                    "subsystem": "tcs",
                    "event_type": "heater_stuck_on",
                    "description": "Heater stuck on begins adding uncommanded heat.",
                    "evidence_ids": ["evt_001"],
                },
                {
                    "step": 2,
                    "timestamp": _iso(1650),
                    "subsystem": "tcs",
                    "event_type": "thermal_overheat_critical",
                    "description": "Loop temperature exceeds critical limit.",
                    "evidence_ids": ["evt_002"],
                },
            ],
        },
    )
)

# 3. reaction_wheel_degradation: wheel degrades -> attitude error grows.
SCENARIOS.append(
    _scenario(
        "reaction_wheel_degradation",
        "Reaction Wheel Degradation",
        "A reaction wheel bearing degrades, reducing pointing authority and "
        "letting attitude error grow past the critical limit.",
        "actuator_failure",
        "adcs",
        1200.0,
        1500.0,
        0.4,
        {
            "attitude_error_deg": [(0, 0.25), (1200, 0.25), (2100, 2.6), (2700, 0.25)],
            "reaction_wheel_speed_rpm": [(0, 2100.0), (1200, 2100.0), (2100, 1200.0), (2700, 2100.0)],
        },
        [
            {
                "timestamp": _iso(2100),
                "subsystem": "adcs",
                "event_type": "attitude_control_degraded",
                "description": "Attitude error exceeds nominal pointing limit.",
                "severity": "high",
            },
            {
                "timestamp": _iso(2250),
                "subsystem": "adcs",
                "event_type": "reaction_wheel_saturation",
                "description": "Reaction wheel speed approaches saturation.",
                "severity": "high",
            },
        ],
        {
            "scenario_id": "reaction_wheel_degradation",
            "synthetic": True,
            "injected_fault": {
                "fault_type": "actuator_failure",
                "target_subsystem": "adcs",
                "start_time": _iso(1200),
                "duration_seconds": 1500.0,
                "magnitude": 0.4,
                "parameters": {
                    "root_cause": "reaction_wheel_bearing_wear",
                    "affected_parameter": "attitude_error_deg",
                },
            },
            "expected_causal_sequence": [
                {
                    "step": 1,
                    "timestamp": _iso(1200),
                    "subsystem": "adcs",
                    "event_type": "reaction_wheel_degraded",
                    "description": "Wheel degradation begins; control authority drops.",
                    "evidence_ids": ["evt_001"],
                },
                {
                    "step": 2,
                    "timestamp": _iso(2250),
                    "subsystem": "adcs",
                    "event_type": "attitude_error_critical",
                    "description": "Pointing error crosses critical limit.",
                    "evidence_ids": ["evt_002"],
                },
            ],
        },
    )
)

# 4. transmitter_overdraw: transmitter draws excess power -> bus sags -> comms degraded.
SCENARIOS.append(
    _scenario(
        "transmitter_overdraw",
        "Transmitter Power Overdraw",
        "The RF transmitter draws excess current, sagging the bus and degrading "
        "downlink signal quality.",
        "power_degradation",
        "comms",
        300.0,
        900.0,
        0.3,
        {
            "transmitter_power_w": [(0, 10.0), (300, 10.0), (600, 4.8), (1200, 10.0)],
            "signal_to_noise_db": [(0, 24.0), (300, 24.0), (600, 9.0), (1200, 24.0)],
            "bus_voltage_v": [(0, 28.3), (300, 28.3), (600, 25.0), (1200, 28.3)],
        },
        [
            {
                "timestamp": _iso(600),
                "subsystem": "comms",
                "event_type": "transmitter_power_reduced",
                "description": "Transmitter output reduced to preserve power.",
                "severity": "high",
            },
            {
                "timestamp": _iso(900),
                "subsystem": "comms",
                "event_type": "comms_loss_risk",
                "description": "Link margin insufficient for reliable commanding.",
                "severity": "critical",
            },
        ],
        {
            "scenario_id": "transmitter_overdraw",
            "synthetic": True,
            "injected_fault": {
                "fault_type": "power_degradation",
                "target_subsystem": "comms",
                "start_time": _iso(300),
                "duration_seconds": 900.0,
                "magnitude": 0.3,
                "parameters": {
                    "root_cause": "transmitter_overdraw",
                    "affected_parameter": "transmitter_power_w",
                },
            },
            "expected_causal_sequence": [
                {
                    "step": 1,
                    "timestamp": _iso(300),
                    "subsystem": "comms",
                    "event_type": "transmitter_overdraw",
                    "description": "Transmitter overdraw begins; bus and SNR degrade.",
                    "evidence_ids": ["evt_001"],
                },
                {
                    "step": 2,
                    "timestamp": _iso(900),
                    "subsystem": "comms",
                    "event_type": "communication_loss_critical",
                    "description": "SNR crosses critical low; downlink at risk.",
                    "evidence_ids": ["evt_002"],
                },
            ],
        },
    )
)

# 5. decoy_sensor_bias: telemetry shows a bus sag (sensor bias) but hardware fine.
SCENARIOS.append(
    _scenario(
        "decoy_sensor_bias",
        "Bus Voltage Sensor Bias (Decoy)",
        "The bus voltage sensor reports a false low reading while the actual "
        "power hardware is healthy; a decoy for a real power fault.",
        "sensor_drift",
        "eps",
        900.0,
        1200.0,
        0.25,
        {
            # Only the *reported* bus_voltage_v is biased; battery_voltage_v stays
            # nominal so the hardware is demonstrably fine.
            "bus_voltage_v": [(0, 28.3), (900, 28.3), (1200, 23.0), (2100, 28.3)],
            "battery_voltage_v": [(0, 28.3), (2100, 28.3)],
        },
        [
            {
                "timestamp": _iso(1200),
                "subsystem": "eps",
                "event_type": "battery_voltage_sag",
                "description": "Sensor reports bus voltage drop; hardware nominal.",
                "severity": "medium",
            },
            {
                "timestamp": _iso(1500),
                "subsystem": "eps",
                "event_type": "power_available_reduced",
                "description": "Available power appears reduced (sensor artifact).",
                "severity": "high",
            },
        ],
        {
            "scenario_id": "decoy_sensor_bias",
            "synthetic": True,
            "injected_fault": {
                "fault_type": "sensor_drift",
                "target_subsystem": "eps",
                "start_time": _iso(900),
                "duration_seconds": 1200.0,
                "magnitude": 0.25,
                "parameters": {
                    "root_cause": "bus_voltage_sensor_bias",
                    "affected_parameter": "bus_voltage_v",
                    "hardware_healthy": True,
                },
            },
            "expected_causal_sequence": [
                {
                    "step": 1,
                    "timestamp": _iso(900),
                    "subsystem": "eps",
                    "event_type": "sensor_drift_begins",
                    "description": "Bus voltage sensor begins drifting low; no hardware fault.",
                    "evidence_ids": ["evt_001"],
                },
                {
                    "step": 2,
                    "timestamp": _iso(1200),
                    "subsystem": "eps",
                    "event_type": "battery_voltage_sag",
                    "description": "Sensor reports undervoltage; battery voltage nominal.",
                    "evidence_ids": ["evt_002"],
                },
            ],
        },
    )
)

# 6. compound_two_cause: bus sag (eps) + heater overheat (tcs).
SCENARIOS.append(
    _scenario(
        "compound_two_cause",
        "Compound Power + Thermal Fault",
        "Two independent causes coincide: a battery cell imbalance sags the bus "
        "while a stuck heater adds thermal load.",
        "power_degradation",
        "eps",
        600.0,
        2400.0,
        0.4,
        {
            "bus_voltage_v": [(0, 28.3), (600, 28.3), (1500, 24.0), (3000, 28.3)],
            "battery_voltage_v": [(0, 28.3), (600, 28.3), (1500, 24.5), (3000, 28.3)],
            "thermal_loop_temperature_c": [(0, 21.0), (1800, 21.0), (2400, 41.0), (3000, 21.0)],
        },
        [
            {
                "timestamp": _iso(600),
                "subsystem": "eps",
                "event_type": "battery_cell_imbalance",
                "description": "Battery cell imbalance begins; bus voltage sags.",
                "severity": "medium",
            },
            {
                "timestamp": _iso(1800),
                "subsystem": "tcs",
                "event_type": "thermal_control_degraded",
                "description": "Thermal control cannot hold battery setpoint.",
                "severity": "medium",
            },
            {
                "timestamp": _iso(2400),
                "subsystem": "tcs",
                "event_type": "battery_temperature_high",
                "description": "Battery temperature exceeds warning threshold.",
                "severity": "high",
            },
        ],
        {
            "scenario_id": "compound_two_cause",
            "synthetic": True,
            "injected_fault": {
                "fault_type": "power_degradation",
                "target_subsystem": "eps",
                "start_time": _iso(600),
                "duration_seconds": 2400.0,
                "magnitude": 0.4,
                "parameters": {
                    "root_cause": "compound: battery_cell_imbalance + heater_stuck_on",
                    "affected_parameter": "bus_voltage_v",
                    "secondary_fault": "thermal_overheat",
                    "secondary_target": "tcs",
                },
            },
            "expected_causal_sequence": [
                {
                    "step": 1,
                    "timestamp": _iso(600),
                    "subsystem": "eps",
                    "event_type": "battery_cell_imbalance",
                    "description": "First cause: battery cell imbalance sags the bus.",
                    "evidence_ids": ["evt_001"],
                },
                {
                    "step": 2,
                    "timestamp": _iso(1800),
                    "subsystem": "tcs",
                    "event_type": "heater_stuck_on",
                    "description": "Second cause: heater stuck on adds thermal load.",
                    "evidence_ids": ["evt_002"],
                },
                {
                    "step": 3,
                    "timestamp": _iso(2400),
                    "subsystem": "tcs",
                    "event_type": "thermal_overheat_critical",
                    "description": "Combined load pushes thermal loop critical.",
                    "evidence_ids": ["evt_003"],
                },
            ],
        },
    )
)


def _write_yaml(scenario: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "id": scenario["id"],
        "name": scenario["name"],
        "description": scenario["description"],
        "seed": scenario["seed"],
        "mission_start_utc": scenario["mission_start_utc"],
        "duration_seconds": scenario["duration_seconds"],
        "sampling_interval_seconds": scenario["sampling_interval_seconds"],
        "subsystems": scenario["subsystems"],
        "fault": scenario["fault"],
        "telemetry_file": scenario["telemetry_file"],
        "event_log_json": scenario["event_log_json"],
        "event_log_csv": scenario["event_log_csv"],
    }
    (CONFIG_DIR / f"{scenario['id']}.yaml").write_text(yaml.safe_dump(data, sort_keys=False))


def _write_telemetry(scenario: dict) -> None:
    TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
    rows = _telemetry_rows(scenario["points"])
    path = TELEMETRY_DIR / f"{scenario['id']}_telemetry.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "subsystem", "parameter", "value", "unit", "source_id"])
        w.writerows(rows)


def _write_events(scenario: dict) -> None:
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    events = list(scenario["events"])
    for i, ev in enumerate(events, 1):
        ev.setdefault("event_id", f"evt_{i:03d}")
    path = EVENTS_DIR / f"{scenario['id']}_events.json"
    path.write_text(json.dumps(events, indent=2))


def _write_ground_truth(scenario: dict) -> None:
    EXPECTED_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPECTED_DIR / f"{scenario['id']}_ground_truth.json"
    path.write_text(json.dumps(scenario["ground_truth"], indent=2))


TERMINAL_STATES = {
    "solar_shadowing": "recovery",
    "heater_stuck_on": "safe_mode",
    "reaction_wheel_degradation": "safe_mode",
    "transmitter_overdraw": "safe_mode",
    "decoy_sensor_bias": "recovery",
    "compound_two_cause": "mission_failure",
}


def main() -> None:
    _seeded(SEED)
    for scenario in SCENARIOS:
        scenario["ground_truth"]["expected_terminal_state"] = TERMINAL_STATES[
            scenario["id"]
        ]
        _write_yaml(scenario)
        _write_telemetry(scenario)
        _write_events(scenario)
        _write_ground_truth(scenario)
        print(f"generated {scenario['id']}")


if __name__ == "__main__":
    main()
