"""Fault injection: apply YAML-declared effects and couplings to the state.

The injector is the only module that knows the true chain. It applies each
chain step at exactly the onset and ramp declared in the scenario, so the data
and ``ground_truth.json`` cannot drift apart.
"""

from __future__ import annotations

import numpy as np

from prometheus.contracts import Subsystem
from prometheus.sim.scenario import ChainStep, Scenario


def smoothstep(t: np.ndarray, onset_s: float, ramp_s: float) -> np.ndarray:
    """Return a 0..1 smooth ramp starting at ``onset_s`` over ``ramp_s``."""
    if ramp_s <= 0:
        return (t >= onset_s).astype(float)
    x = np.clip((t - onset_s) / ramp_s, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def step_for(scenario: Scenario, subsystem: Subsystem, channel: str) -> ChainStep:
    """Look up the chain step that drives ``subsystem/channel``."""
    for step in scenario.chain:
        if step.subsystem is subsystem and step.channel == channel:
            return step
    raise KeyError(f"{scenario.name}: no chain step for {subsystem}/{channel}")


def step_factor(
    scenario: Scenario, subsystem: Subsystem, channel: str, t: np.ndarray
) -> np.ndarray:
    """Return the normalized ramp of the chain step for ``subsystem/channel``."""
    step = step_for(scenario, subsystem, channel)
    onset = scenario.fault.start_s + step.onset_offset_s
    return smoothstep(t, onset, step.ramp_s)


def _apply_chain(
    scenario: Scenario, t: np.ndarray, ch: dict[Subsystem, dict[str, np.ndarray]]
) -> None:
    """Apply every YAML chain step generically at its declared onset."""
    for step in scenario.chain:
        onset = scenario.fault.start_s + step.onset_offset_s
        ch[step.subsystem][step.channel] += step.expected_delta * smoothstep(
            t, onset, step.ramp_s
        )


def _battery_voltage_drop(
    scenario: Scenario, t: np.ndarray, ch: dict[Subsystem, dict[str, np.ndarray]]
) -> None:
    """Cell degradation cascades into comms, thermal and attitude effects."""
    _apply_chain(scenario, t, ch)
    params = scenario.fault.params

    tx = step_factor(scenario, Subsystem.COMMS, "tx_power_dbw", t)
    ch[Subsystem.COMMS]["snr_db"] -= params.get("snr_cut_db", 2.4) * tx
    ch[Subsystem.COMMS]["downlink_rate_kbps"] *= 1.0 - params.get(
        "downlink_cut_frac", 0.35
    ) * tx
    ch[Subsystem.COMMS]["transmitter_current_a"] -= 0.12 * tx

    shed = step_factor(scenario, Subsystem.POWER, "load_power_w", t)
    ch[Subsystem.POWER]["bus_current_a"] -= params.get("load_shed_current_a", 2.2) * shed

    sag = step_factor(scenario, Subsystem.POWER, "bus_voltage_v", t)
    ch[Subsystem.POWER]["battery_soc_pct"] -= params.get("soc_loss_pct", 6.0) * sag

    drift = step_factor(scenario, Subsystem.ADCS, "attitude_error_deg", t)
    ch[Subsystem.ADCS]["wheel_current_a"] -= params.get("wheel_current_loss_a", 0.25) * drift


def _reaction_wheel_friction(
    scenario: Scenario, t: np.ndarray, ch: dict[Subsystem, dict[str, np.ndarray]]
) -> None:
    """Bearing friction loads the bus and degrades pointing."""
    _apply_chain(scenario, t, ch)
    params = scenario.fault.params

    load = step_factor(scenario, Subsystem.POWER, "bus_current_a", t)
    ch[Subsystem.POWER]["bus_voltage_v"] -= params.get("voltage_drop_v", 0.45) * load

    snr = step_factor(scenario, Subsystem.COMMS, "snr_db", t)
    ch[Subsystem.COMMS]["downlink_rate_kbps"] *= 1.0 - 0.15 * snr

    friction = step_factor(scenario, Subsystem.ADCS, "wheel_current_a", t)
    ch[Subsystem.ADCS]["wheel_speed_rpm"] -= params.get("speed_loss_rpm", 25.0) * friction
    ch[Subsystem.THERMAL]["payload_temp_k"] += params.get("payload_heat_k", 0.8) * friction


def _heater_stuck_on(
    scenario: Scenario, t: np.ndarray, ch: dict[Subsystem, dict[str, np.ndarray]]
) -> None:
    """A stuck heater overheats the battery and strains the power budget."""
    _apply_chain(scenario, t, ch)
    params = scenario.fault.params

    heater = step_factor(scenario, Subsystem.THERMAL, "heater_power_w", t)
    ch[Subsystem.THERMAL]["payload_temp_k"] += params.get("payload_heat_k", 1.0) * heater

    load = step_factor(scenario, Subsystem.POWER, "load_power_w", t)
    ch[Subsystem.POWER]["bus_current_a"] += params.get("extra_bus_current_a", 3.0) * load

    warm = step_factor(scenario, Subsystem.THERMAL, "battery_temp_k", t)
    ch[Subsystem.POWER]["battery_soc_pct"] -= params.get("soc_loss_pct", 8.0) * warm

    tx = step_factor(scenario, Subsystem.COMMS, "tx_power_dbw", t)
    ch[Subsystem.COMMS]["snr_db"] -= params.get("snr_cut_db", 0.6) * tx
    ch[Subsystem.COMMS]["downlink_rate_kbps"] *= 1.0 - params.get(
        "downlink_cut_frac", 0.08
    ) * tx


_FAULTS = {
    "battery_voltage_drop": _battery_voltage_drop,
    "reaction_wheel_friction": _reaction_wheel_friction,
    "heater_stuck_on": _heater_stuck_on,
}


def apply_fault(
    scenario: Scenario, t: np.ndarray, ch: dict[Subsystem, dict[str, np.ndarray]]
) -> None:
    """Apply the scenario's fault and its secondary couplings in place."""
    try:
        fault = _FAULTS[scenario.fault.type]
    except KeyError as exc:  # pragma: no cover - guarded by scenario validation
        raise ValueError(f"unsupported fault type {scenario.fault.type!r}") from exc
    fault(scenario, t, ch)


def _triangular_bump(t: np.ndarray, start_s: float, duration_s: float) -> np.ndarray:
    x = np.clip((t - start_s) / duration_s, 0.0, 1.0)
    inside = (t >= start_s) & (t <= start_s + duration_s)
    return np.where(inside, np.sin(np.pi * x), 0.0)


def apply_distractor(
    scenario: Scenario, t: np.ndarray, ch: dict[Subsystem, dict[str, np.ndarray]]
) -> None:
    """Apply the benign transient. It never appears in the causal chain."""
    spec = scenario.distractor
    bump = _triangular_bump(t, spec.start_s, spec.duration_s)
    magnitude = spec.magnitude

    if spec.type == "comms_snr_dip":
        ch[Subsystem.COMMS]["snr_db"] += magnitude * bump
        ch[Subsystem.COMMS]["downlink_rate_kbps"] *= 1.0 + 0.2 * magnitude / 3.0 * bump
    elif spec.type == "payload_current_spike":
        ch[Subsystem.POWER]["load_power_w"] += magnitude * bump
        ch[Subsystem.POWER]["bus_current_a"] += magnitude / 28.4 * bump
        ch[Subsystem.POWER]["bus_voltage_v"] -= 0.08 * bump
    elif spec.type == "attitude_slew":
        ch[Subsystem.ADCS]["attitude_error_deg"] += magnitude * bump
        ch[Subsystem.ADCS]["wheel_current_a"] += 0.3 * bump
        ch[Subsystem.ADCS]["wheel_temp_c"] += 1.0 * bump
    else:  # pragma: no cover - guarded by scenario validation
        raise ValueError(f"unsupported distractor type {spec.type!r}")
