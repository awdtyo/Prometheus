"""Wire models for scenarios, fault injection, and subsystem catalogs."""

from enum import StrEnum
from typing import Any

from pydantic import Field

from backend.schemas.base import ApiModel, UtcDatetime


class FaultType(StrEnum):
    """Fault families that can be injected into a scenario."""

    POWER_LOSS = "power_loss"
    POWER_DEGRADATION = "power_degradation"
    THERMAL_OVERHEAT = "thermal_overheat"
    SENSOR_DRIFT = "sensor_drift"
    SENSOR_FAILURE = "sensor_failure"
    COMMUNICATION_LOSS = "communication_loss"
    ACTUATOR_FAILURE = "actuator_failure"
    SOFTWARE_FAULT = "software_fault"
    UNKNOWN = "unknown"


class FaultConfig(ApiModel):
    """Validated fault injection requested for a scenario or run."""

    fault_type: FaultType
    target_subsystem: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    start_time: UtcDatetime
    duration_seconds: float = Field(gt=0)
    magnitude: float = Field(ge=0)
    parameters: dict[str, Any] = Field(default_factory=dict)


class TelemetryParameterResponse(ApiModel):
    """Telemetry channel available in a scenario."""

    parameter: str
    subsystem: str
    unit: str
    nominal_value: float
    description: str


class SubsystemResponse(ApiModel):
    """A spacecraft subsystem and its direct dependencies."""

    id: str
    name: str
    description: str
    depends_on: list[str] = Field(default_factory=list)


class FaultOptionResponse(ApiModel):
    """A fault type supported by a scenario and its allowed targets."""

    fault_type: FaultType
    description: str
    target_subsystems: list[str] = Field(default_factory=list)
    min_duration_seconds: float = Field(gt=0)
    max_duration_seconds: float = Field(gt=0)
    min_magnitude: float = Field(ge=0)
    max_magnitude: float = Field(ge=0)


class ScenarioResponse(ApiModel):
    """Scenario metadata returned by the collection endpoint."""

    id: str
    name: str
    description: str
    duration_seconds: float = Field(gt=0)
    subsystem_ids: list[str] = Field(default_factory=list)
    fault_types: list[FaultType] = Field(default_factory=list)


class ScenarioDetailResponse(ScenarioResponse):
    """Complete scenario configuration, separate from any run configuration."""

    mission_start_utc: UtcDatetime
    subsystems: list[SubsystemResponse] = Field(default_factory=list)
    telemetry_parameters: list[TelemetryParameterResponse] = Field(default_factory=list)
    fault_options: list[FaultOptionResponse] = Field(default_factory=list)


class ScenarioListResponse(ApiModel):
    """Collection of available scenarios."""

    items: list[ScenarioResponse] = Field(default_factory=list)


class ScenarioInjectionResponse(ApiModel):
    """Injection preview that never mutates the source scenario definition."""

    injection_id: str
    scenario_id: str
    preview: bool = True
    applied: bool = False
    fault_config: FaultConfig
    effective_start_time: UtcDatetime
    effective_end_time: UtcDatetime
    scenario: ScenarioDetailResponse


class SubsystemListResponse(ApiModel):
    """Collection of available subsystems."""

    items: list[SubsystemResponse] = Field(default_factory=list)
