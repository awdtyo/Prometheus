"""Static, immutable scenario fixtures.

These definitions describe mission inputs only. Run configuration lives in
``backend.schemas.run`` and is validated separately, so a run or injection can
never mutate a scenario fixture in place.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType

from backend.schemas.catalog import FaultType


@dataclass(frozen=True)
class SubsystemDefinition:
    """One spacecraft subsystem and its dependencies."""

    id: str
    name: str
    description: str
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class TelemetryParameterDefinition:
    """One telemetry channel available during a scenario."""

    parameter: str
    subsystem: str
    unit: str
    nominal_value: float
    description: str


@dataclass(frozen=True)
class FaultOptionDefinition:
    """A fault family supported by a scenario."""

    fault_type: FaultType
    description: str
    target_subsystems: tuple[str, ...]
    min_duration_seconds: float
    max_duration_seconds: float
    min_magnitude: float
    max_magnitude: float


@dataclass(frozen=True)
class ScenarioDefinition:
    """Immutable mission scenario fixture."""

    id: str
    name: str
    description: str
    mission_start_utc: datetime
    duration_seconds: float
    subsystem_ids: tuple[str, ...]
    telemetry_parameters: tuple[TelemetryParameterDefinition, ...]
    fault_options: tuple[FaultOptionDefinition, ...]

    @property
    def fault_types(self) -> tuple[FaultType, ...]:
        """Return the supported fault types in declaration order."""
        return tuple(option.fault_type for option in self.fault_options)


_MISSION_START = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)

SUBSYSTEMS: Mapping[str, SubsystemDefinition] = MappingProxyType(
    {
        "power": SubsystemDefinition(
            id="power",
            name="Power",
            description="Solar arrays, batteries, and the main power bus.",
            depends_on=("thermal-control",),
        ),
        "thermal-control": SubsystemDefinition(
            id="thermal-control",
            name="Thermal Control",
            description="Radiators, heaters, and thermal sensors.",
        ),
        "attitude-control": SubsystemDefinition(
            id="attitude-control",
            name="Attitude Control",
            description="Star trackers, reaction wheels, and pointing control.",
            depends_on=("power",),
        ),
        "communications": SubsystemDefinition(
            id="communications",
            name="Communications",
            description="Transponders and the high-gain antenna assembly.",
            depends_on=("power", "attitude-control"),
        ),
    }
)

SCENARIOS: Mapping[str, ScenarioDefinition] = MappingProxyType(
    {
        "scn_power_undervoltage": ScenarioDefinition(
            id="scn_power_undervoltage",
            name="Power bus undervoltage",
            description="Battery heater fault causes a sustained bus undervoltage.",
            mission_start_utc=_MISSION_START,
            duration_seconds=600.0,
            subsystem_ids=("power", "thermal-control"),
            telemetry_parameters=(
                TelemetryParameterDefinition(
                    parameter="bus_voltage",
                    subsystem="power",
                    unit="V",
                    nominal_value=28.1,
                    description="Main power bus voltage.",
                ),
                TelemetryParameterDefinition(
                    parameter="battery_soc",
                    subsystem="power",
                    unit="%",
                    nominal_value=82.0,
                    description="Battery state of charge.",
                ),
                TelemetryParameterDefinition(
                    parameter="heater_current",
                    subsystem="thermal-control",
                    unit="A",
                    nominal_value=1.2,
                    description="Battery heater current draw.",
                ),
            ),
            fault_options=(
                FaultOptionDefinition(
                    fault_type=FaultType.POWER_LOSS,
                    description="Complete loss of power on the target subsystem.",
                    target_subsystems=("power",),
                    min_duration_seconds=1.0,
                    max_duration_seconds=600.0,
                    min_magnitude=0.0,
                    max_magnitude=100.0,
                ),
                FaultOptionDefinition(
                    fault_type=FaultType.POWER_DEGRADATION,
                    description="Gradual reduction in available power.",
                    target_subsystems=("power",),
                    min_duration_seconds=1.0,
                    max_duration_seconds=600.0,
                    min_magnitude=0.0,
                    max_magnitude=100.0,
                ),
                FaultOptionDefinition(
                    fault_type=FaultType.THERMAL_OVERHEAT,
                    description="Thermal control loses its heat-rejection margin.",
                    target_subsystems=("thermal-control",),
                    min_duration_seconds=1.0,
                    max_duration_seconds=600.0,
                    min_magnitude=0.0,
                    max_magnitude=100.0,
                ),
                FaultOptionDefinition(
                    fault_type=FaultType.SENSOR_DRIFT,
                    description="A power telemetry channel drifts out of calibration.",
                    target_subsystems=("power",),
                    min_duration_seconds=1.0,
                    max_duration_seconds=600.0,
                    min_magnitude=0.0,
                    max_magnitude=100.0,
                ),
                FaultOptionDefinition(
                    fault_type=FaultType.SENSOR_FAILURE,
                    description="A power telemetry channel stops reporting.",
                    target_subsystems=("power",),
                    min_duration_seconds=1.0,
                    max_duration_seconds=600.0,
                    min_magnitude=0.0,
                    max_magnitude=100.0,
                ),
                FaultOptionDefinition(
                    fault_type=FaultType.SOFTWARE_FAULT,
                    description="Flight software misconfigures the power controller.",
                    target_subsystems=("power",),
                    min_duration_seconds=1.0,
                    max_duration_seconds=600.0,
                    min_magnitude=0.0,
                    max_magnitude=100.0,
                ),
            ),
        ),
        "scn_thermal_overheat": ScenarioDefinition(
            id="scn_thermal_overheat",
            name="Thermal control overheat",
            description="A stuck radiator valve drives a thermal-control overheat.",
            mission_start_utc=_MISSION_START,
            duration_seconds=900.0,
            subsystem_ids=("thermal-control", "power"),
            telemetry_parameters=(
                TelemetryParameterDefinition(
                    parameter="radiator_temp",
                    subsystem="thermal-control",
                    unit="degC",
                    nominal_value=18.0,
                    description="Radiator outlet temperature.",
                ),
                TelemetryParameterDefinition(
                    parameter="heater_power",
                    subsystem="thermal-control",
                    unit="W",
                    nominal_value=45.0,
                    description="Heater power consumption.",
                ),
                TelemetryParameterDefinition(
                    parameter="bus_voltage",
                    subsystem="power",
                    unit="V",
                    nominal_value=28.1,
                    description="Main power bus voltage.",
                ),
            ),
            fault_options=(
                FaultOptionDefinition(
                    fault_type=FaultType.THERMAL_OVERHEAT,
                    description="Heat rejection falls below the required rate.",
                    target_subsystems=("thermal-control",),
                    min_duration_seconds=1.0,
                    max_duration_seconds=900.0,
                    min_magnitude=0.0,
                    max_magnitude=100.0,
                ),
                FaultOptionDefinition(
                    fault_type=FaultType.ACTUATOR_FAILURE,
                    description="A radiator valve or heater actuator jams.",
                    target_subsystems=("thermal-control",),
                    min_duration_seconds=1.0,
                    max_duration_seconds=900.0,
                    min_magnitude=0.0,
                    max_magnitude=100.0,
                ),
                FaultOptionDefinition(
                    fault_type=FaultType.POWER_DEGRADATION,
                    description="Reduced power limits heater and pump operation.",
                    target_subsystems=("power",),
                    min_duration_seconds=1.0,
                    max_duration_seconds=900.0,
                    min_magnitude=0.0,
                    max_magnitude=100.0,
                ),
                FaultOptionDefinition(
                    fault_type=FaultType.SENSOR_DRIFT,
                    description="A thermal sensor drifts out of calibration.",
                    target_subsystems=("thermal-control",),
                    min_duration_seconds=1.0,
                    max_duration_seconds=900.0,
                    min_magnitude=0.0,
                    max_magnitude=100.0,
                ),
                FaultOptionDefinition(
                    fault_type=FaultType.SENSOR_FAILURE,
                    description="A thermal sensor stops reporting.",
                    target_subsystems=("thermal-control",),
                    min_duration_seconds=1.0,
                    max_duration_seconds=900.0,
                    min_magnitude=0.0,
                    max_magnitude=100.0,
                ),
                FaultOptionDefinition(
                    fault_type=FaultType.SOFTWARE_FAULT,
                    description="Thermal control software ignores a temperature limit.",
                    target_subsystems=("thermal-control",),
                    min_duration_seconds=1.0,
                    max_duration_seconds=900.0,
                    min_magnitude=0.0,
                    max_magnitude=100.0,
                ),
            ),
        ),
        "scn_comms_loss": ScenarioDefinition(
            id="scn_comms_loss",
            name="Communications loss",
            description="An attitude upset interrupts the high-gain antenna link.",
            mission_start_utc=_MISSION_START,
            duration_seconds=720.0,
            subsystem_ids=("communications", "attitude-control", "power"),
            telemetry_parameters=(
                TelemetryParameterDefinition(
                    parameter="signal_strength",
                    subsystem="communications",
                    unit="dBm",
                    nominal_value=-78.0,
                    description="Received downlink signal strength.",
                ),
                TelemetryParameterDefinition(
                    parameter="antenna_azimuth",
                    subsystem="attitude-control",
                    unit="deg",
                    nominal_value=12.5,
                    description="High-gain antenna azimuth angle.",
                ),
                TelemetryParameterDefinition(
                    parameter="downlink_rate",
                    subsystem="communications",
                    unit="kbps",
                    nominal_value=256.0,
                    description="Downlink data rate.",
                ),
            ),
            fault_options=(
                FaultOptionDefinition(
                    fault_type=FaultType.COMMUNICATION_LOSS,
                    description="The communications link drops below acquisition threshold.",
                    target_subsystems=("communications",),
                    min_duration_seconds=1.0,
                    max_duration_seconds=720.0,
                    min_magnitude=0.0,
                    max_magnitude=100.0,
                ),
                FaultOptionDefinition(
                    fault_type=FaultType.ACTUATOR_FAILURE,
                    description="An attitude actuator jams and mispoints the antenna.",
                    target_subsystems=("attitude-control",),
                    min_duration_seconds=1.0,
                    max_duration_seconds=720.0,
                    min_magnitude=0.0,
                    max_magnitude=100.0,
                ),
                FaultOptionDefinition(
                    fault_type=FaultType.SENSOR_FAILURE,
                    description="A pointing or communications sensor stops reporting.",
                    target_subsystems=("attitude-control", "communications"),
                    min_duration_seconds=1.0,
                    max_duration_seconds=720.0,
                    min_magnitude=0.0,
                    max_magnitude=100.0,
                ),
                FaultOptionDefinition(
                    fault_type=FaultType.POWER_LOSS,
                    description="Loss of power disables the communications subsystem.",
                    target_subsystems=("power",),
                    min_duration_seconds=1.0,
                    max_duration_seconds=720.0,
                    min_magnitude=0.0,
                    max_magnitude=100.0,
                ),
                FaultOptionDefinition(
                    fault_type=FaultType.SOFTWARE_FAULT,
                    description="Communications software rejects valid commands.",
                    target_subsystems=("communications",),
                    min_duration_seconds=1.0,
                    max_duration_seconds=720.0,
                    min_magnitude=0.0,
                    max_magnitude=100.0,
                ),
                FaultOptionDefinition(
                    fault_type=FaultType.SENSOR_DRIFT,
                    description="The received signal-strength reading drifts.",
                    target_subsystems=("communications",),
                    min_duration_seconds=1.0,
                    max_duration_seconds=720.0,
                    min_magnitude=0.0,
                    max_magnitude=100.0,
                ),
            ),
        ),
    }
)


def list_scenarios() -> tuple[ScenarioDefinition, ...]:
    """Return all scenario definitions in stable order."""
    return tuple(SCENARIOS.values())


def get_scenario(scenario_id: str) -> ScenarioDefinition | None:
    """Return one scenario definition or ``None`` when it is unknown."""
    return SCENARIOS.get(scenario_id)


def list_subsystems() -> tuple[SubsystemDefinition, ...]:
    """Return all subsystem definitions in stable order."""
    return tuple(SUBSYSTEMS.values())
