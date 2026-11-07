"""Deterministic spacecraft model across power, thermal, comms and ADCS.

The model runs at a 5 s base step; each subsystem is then exported at its own
cadence by :mod:`prometheus.sim.output`. Every random draw comes from a single
seeded generator, so a seed fully determines a run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from prometheus.contracts import Subsystem
from prometheus.sim import faults
from prometheus.sim.ground_truth import build_ground_truth
from prometheus.sim.scenario import EventSpec, Scenario

#: Base integration step. Every subsystem sample interval divides this interval.
BASE_DT_S: float = 5.0


@dataclass(frozen=True)
class Event:
    """A command or alarm produced by a run."""

    at_s: float
    kind: str
    subsystem: Subsystem
    severity: str
    code: str
    message: str


@dataclass
class Run:
    """One simulated mission with telemetry, events and the true chain."""

    scenario: Scenario
    seed: int
    time_s: np.ndarray
    channels: dict[Subsystem, dict[str, np.ndarray]]
    events: list[Event]
    ground_truth: dict[str, Any] = field(default_factory=dict)


def _noise(rng: np.random.Generator, size: int, std: float) -> np.ndarray:
    return rng.normal(0.0, std, size)


def nominal_channels(
    scenario: Scenario, t: np.ndarray, rng: np.random.Generator
) -> dict[Subsystem, dict[str, np.ndarray]]:
    """Build the healthy-mission telemetry, including cross-subsystem couplings."""
    orbital = np.sin(2.0 * np.pi * t / 5400.0)
    payload_on = ((t % 1800.0) < 1080.0).astype(float)

    heater = 35.0 + 6.0 * np.sin(2.0 * np.pi * t / 7200.0)
    wheel_current = 0.80 + 0.25 * payload_on + 0.05 * orbital
    load = 180.0 + 80.0 * payload_on + heater
    bus_current = load / 28.4 + wheel_current
    bus_voltage = 28.35 - 0.045 * (bus_current - 11.3) + 0.05 * orbital

    tx_power = 7.20 - 0.60 * np.maximum(0.0, 27.4 - bus_voltage)
    snr = 14.0 + 0.8 * (tx_power - 7.2) + 0.5 * orbital
    downlink = 256.0 * (tx_power / 7.2) ** 1.5
    tx_current = 1.80 + 0.05 * tx_power

    battery_temp_c = 12.0 + 0.12 * (heater - 35.0) + 0.05 * (bus_current - 11.0)
    battery_noise = _noise(rng, t.size, 0.08)
    soc = np.clip(92.0 - 0.0009 * t + 0.4 * orbital, 0.0, 100.0)
    avionics_k = 293.0 + 0.25 * (heater - 35.0) + 0.30 * payload_on + 0.20 * (tx_power - 7.2)
    payload_k = 296.0 + 2.0 * payload_on + 0.5 * orbital
    wheel_temp_c = 30.0 + 2.5 * (wheel_current - 0.8) / 0.25 + 0.0005 * t
    wheel_speed = 3200.0 + 40.0 * orbital
    attitude = 0.08 + 0.02 * orbital + 0.01 * payload_on

    return {
        Subsystem.POWER: {
            "bus_voltage_v": bus_voltage + _noise(rng, t.size, 0.02),
            "bus_current_a": bus_current + _noise(rng, t.size, 0.03),
            "battery_soc_pct": soc + _noise(rng, t.size, 0.05),
            "battery_temp_c": battery_temp_c + battery_noise,
            "solar_input_w": 420.0
            + 15.0 * orbital
            - 5.0 * np.cos(2.0 * np.pi * t / 2700.0)
            + _noise(rng, t.size, 2.0),
            "load_power_w": load + _noise(rng, t.size, 1.5),
        },
        Subsystem.THERMAL: {
            "avionics_temp_k": avionics_k + _noise(rng, t.size, 0.10),
            "battery_temp_k": battery_temp_c + battery_noise + 273.15,
            "payload_temp_k": payload_k + _noise(rng, t.size, 0.15),
            "heater_power_w": heater + _noise(rng, t.size, 0.60),
        },
        Subsystem.COMMS: {
            "tx_power_dbw": tx_power + _noise(rng, t.size, 0.04),
            "snr_db": snr + _noise(rng, t.size, 0.18),
            "downlink_rate_kbps": downlink + _noise(rng, t.size, 1.5),
            "transmitter_current_a": tx_current + _noise(rng, t.size, 0.02),
        },
        Subsystem.ADCS: {
            "attitude_error_deg": attitude + _noise(rng, t.size, 0.004),
            "wheel_current_a": wheel_current + _noise(rng, t.size, 0.015),
            "wheel_speed_rpm": wheel_speed + _noise(rng, t.size, 8.0),
            "wheel_temp_c": wheel_temp_c + _noise(rng, t.size, 0.15),
        },
    }


def _events_from_specs(specs: list[EventSpec]) -> list[Event]:
    events = [
        Event(
            at_s=float(spec.at_s),
            kind=spec.kind,
            subsystem=spec.subsystem,
            severity=spec.severity,
            code=spec.code,
            message=spec.message,
        )
        for spec in specs
    ]
    return sorted(events, key=lambda event: (event.at_s, event.code))


def simulate(scenario: Scenario, seed: int) -> Run:
    """Simulate one mission with the scenario fault and its distractor.

    Args:
        scenario: Validated scenario definition.
        seed: Non-negative integer controlling all noise.

    Returns:
        A :class:`Run` with base-step arrays, events and ground truth.
    """
    if seed < 0:
        raise ValueError("seed must be non-negative")
    rng = np.random.default_rng(seed)
    steps = int(scenario.duration_s / BASE_DT_S) + 1
    t = np.arange(steps, dtype=float) * BASE_DT_S
    t[-1] = min(t[-1], scenario.duration_s)

    channels = nominal_channels(scenario, t, rng)
    faults.apply_fault(scenario, t, channels)
    faults.apply_distractor(scenario, t, channels)

    # Keep the duplicate battery temperature representation physically consistent.
    channels[Subsystem.POWER]["battery_temp_c"] = (
        channels[Subsystem.THERMAL]["battery_temp_k"] - 273.15
    )
    channels[Subsystem.POWER]["battery_soc_pct"] = np.clip(
        channels[Subsystem.POWER]["battery_soc_pct"], 0.0, 100.0
    )
    channels[Subsystem.ADCS]["attitude_error_deg"] = np.maximum(
        0.0, channels[Subsystem.ADCS]["attitude_error_deg"]
    )

    events = _events_from_specs(scenario.events)
    ground_truth = build_ground_truth(scenario, seed)

    return Run(
        scenario=scenario,
        seed=seed,
        time_s=t,
        channels=channels,
        events=events,
        ground_truth=ground_truth,
    )
