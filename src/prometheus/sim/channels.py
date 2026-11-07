"""Channel registry and subsystem I/O layout for the synthetic mission.

These definitions are the source of truth for what the simulator writes and for
the generated ``specs.yaml``. Ingest must discover everything from the specs
file, never from this module.
"""

from __future__ import annotations

from dataclasses import dataclass

from prometheus.contracts import Subsystem


@dataclass(frozen=True)
class Channel:
    """One telemetry channel as it appears in a subsystem CSV."""

    key: str
    column: str
    unit: str
    nominal_min: float
    nominal_max: float
    description: str


@dataclass(frozen=True)
class SubsystemLayout:
    """File-level conventions for one subsystem's telemetry export."""

    file_name: str
    sample_interval_s: int
    timestamp_column: str
    timestamp_format: str
    channels: tuple[Channel, ...]


@dataclass(frozen=True)
class Dependency:
    """A plausible cross-subsystem coupling and its lag window."""

    source: Subsystem
    target: Subsystem
    mechanism: str
    lag_min_s: int
    lag_max_s: int


#: Per-subsystem sample rates, timestamp conventions and column names.
#: The formats deliberately differ so ingest has real work to do.
LAYOUTS: dict[Subsystem, SubsystemLayout] = {
    Subsystem.POWER: SubsystemLayout(
        file_name="telemetry_power.csv",
        sample_interval_s=10,
        timestamp_column="timestamp",
        timestamp_format="iso8601_utc",
        channels=(
            Channel("bus_voltage_v", "bus_voltage_v", "V", 27.0, 29.0, "main bus voltage"),
            Channel("bus_current_a", "bus_current_a", "A", 8.0, 16.0, "total bus current"),
            Channel(
                "battery_soc_pct",
                "battery_soc_pct",
                "%",
                40.0,
                100.0,
                "battery state of charge",
            ),
            Channel(
                "battery_temp_c",
                "battery_temp_c",
                "C",
                -5.0,
                25.0,
                "battery cell temperature",
            ),
            Channel("solar_input_w", "solar_input_w", "W", 380.0, 460.0, "solar array input power"),
            Channel("load_power_w", "load_power_w", "W", 220.0, 330.0, "total spacecraft load"),
        ),
    ),
    Subsystem.THERMAL: SubsystemLayout(
        file_name="telemetry_thermal.csv",
        sample_interval_s=30,
        timestamp_column="time_s",
        timestamp_format="epoch_seconds",
        channels=(
            Channel("avionics_temp_k", "node_avionics_k", "K", 285.0, 305.0, "avionics bay node"),
            Channel("battery_temp_k", "node_battery_k", "K", 275.0, 295.0, "battery node"),
            Channel("payload_temp_k", "node_payload_k", "K", 285.0, 310.0, "payload node"),
            Channel("heater_power_w", "heater_power_w", "W", 15.0, 70.0, "battery heater power"),
        ),
    ),
    Subsystem.COMMS: SubsystemLayout(
        file_name="telemetry_comms.csv",
        sample_interval_s=20,
        timestamp_column="unix_ms",
        timestamp_format="epoch_milliseconds",
        channels=(
            Channel("tx_power_dbw", "tx_power_dbw", "dBW", 6.0, 8.0, "transmitter RF output"),
            Channel("snr_db", "snr_db", "dB", 9.0, 18.0, "downlink signal-to-noise ratio"),
            Channel(
                "downlink_rate_kbps",
                "downlink_rate_kbps",
                "kbps",
                180.0,
                320.0,
                "downlink rate",
            ),
            Channel(
                "transmitter_current_a",
                "transmitter_current_a",
                "A",
                1.5,
                2.6,
                "transmitter current draw",
            ),
        ),
    ),
    Subsystem.ADCS: SubsystemLayout(
        file_name="telemetry_adcs.csv",
        sample_interval_s=5,
        timestamp_column="timestamp_utc",
        timestamp_format="iso8601_offset",
        channels=(
            Channel(
                "attitude_error_deg",
                "pointing_error_deg",
                "deg",
                0.0,
                0.3,
                "pointing error",
            ),
            Channel("wheel_current_a", "rw_current_a", "A", 0.4, 1.6, "reaction-wheel current"),
            Channel(
                "wheel_speed_rpm",
                "rw_speed_rpm",
                "rpm",
                2800.0,
                3400.0,
                "reaction-wheel speed",
            ),
            Channel("wheel_temp_c", "rw_temp_c", "C", 20.0, 45.0, "wheel bearing temperature"),
        ),
    ),
}

#: Spec dependency map. Lag windows are wide enough to be discoverable from data.
DEPENDENCIES: tuple[Dependency, ...] = (
    Dependency(
        Subsystem.POWER,
        Subsystem.COMMS,
        "bus voltage limits transmitter RF output",
        0,
        30,
    ),
    Dependency(
        Subsystem.ADCS,
        Subsystem.POWER,
        "reaction-wheel current is drawn from the bus",
        0,
        20,
    ),
    Dependency(
        Subsystem.THERMAL,
        Subsystem.POWER,
        "battery temperature changes usable capacity and internal resistance",
        300,
        900,
    ),
    Dependency(
        Subsystem.POWER,
        Subsystem.THERMAL,
        "heater and bus losses drive node temperatures",
        60,
        180,
    ),
    Dependency(
        Subsystem.POWER,
        Subsystem.ADCS,
        "bus voltage bounds wheel torque authority",
        0,
        60,
    ),
    Dependency(
        Subsystem.ADCS,
        Subsystem.THERMAL,
        "bearing friction dissipates heat into the bus structure",
        30,
        120,
    ),
    Dependency(
        Subsystem.COMMS,
        Subsystem.THERMAL,
        "transmitter dissipation heats the avionics bay",
        60,
        180,
    ),
)


def channel_keys() -> set[tuple[Subsystem, str]]:
    """Return every valid ``(subsystem, channel)`` pair."""
    return {
        (subsystem, channel.key)
        for subsystem, layout in LAYOUTS.items()
        for channel in layout.channels
    }
