"""Scenario YAML specification contracts."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Self

from pydantic import AfterValidator, Field, field_validator, model_validator

from autopsy.schemas.base import (
    AutopsyModel,
    Description,
    EntityId,
    JsonObject,
    Label,
    SubsystemId,
    UtcDatetime,
    ensure_unique,
)
from autopsy.schemas.config import FaultConfig
from autopsy.schemas.enums import FaultType


def _validate_input_path(value: str) -> str:
    """Keep scenario references relative and away from evaluation data."""
    if not value.strip():
        raise ValueError("scenario input paths must not be empty")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or value.startswith("~"):
        raise ValueError("scenario input paths must be relative and stay inside the repository")
    if "expected" in path.parts:
        raise ValueError("scenario input paths must not reference fixtures/expected")
    return value


InputPath = Annotated[str, AfterValidator(_validate_input_path)]


class ScenarioFaultSpec(AutopsyModel):
    """Fault injection expressed in mission elapsed time (MET).

    The scenario YAML is a simulation input. Convert it to an absolute
    :class:`~autopsy.schemas.config.FaultConfig` only when generating or
    replaying the scenario; do not pass this object to hypothesis agents.
    """

    fault_type: FaultType = Field(description="Fault family to inject.")
    target_subsystem: SubsystemId = Field(description="Subsystem to inject the fault into.")
    start_met_seconds: float = Field(
        ge=0.0,
        description="Fault start time as seconds since mission start.",
    )
    duration_seconds: float = Field(
        gt=0.0,
        description="Fault duration in seconds.",
    )
    magnitude: float = Field(
        ge=0.0,
        description="Non-negative fault magnitude in fault-type-specific units.",
    )
    parameters: JsonObject = Field(
        default_factory=dict,
        description="Optional JSON-serializable fault parameters.",
    )

    def to_fault_config(self, mission_start_utc: datetime) -> FaultConfig:
        """Convert MET to an absolute UTC fault configuration."""
        return FaultConfig(
            fault_type=self.fault_type,
            target_subsystem=self.target_subsystem,
            start_time=mission_start_utc + timedelta(seconds=self.start_met_seconds),
            duration_seconds=self.duration_seconds,
            magnitude=self.magnitude,
            parameters=self.parameters,
        )


class ScenarioSpec(AutopsyModel):
    """Declarative scenario setup for deterministic fixture generation."""

    id: EntityId = Field(description="Stable scenario identifier.")
    name: Label = Field(description="Human-readable scenario name.")
    description: Description = Field(description="Scenario purpose and assumptions.")
    seed: int = Field(description="Deterministic seed for scenario generation.")
    mission_start_utc: UtcDatetime = Field(description="Mission epoch in UTC.")
    duration_seconds: float = Field(gt=0.0, description="Scenario duration in seconds.")
    sampling_interval_seconds: float = Field(
        gt=0.0,
        description="Telemetry sampling interval in seconds.",
    )
    subsystems: list[SubsystemId] = Field(
        min_length=1,
        description="Subsystems participating in the scenario.",
    )
    fault: ScenarioFaultSpec = Field(description="Fault injection setup.")
    telemetry_file: InputPath = Field(description="Relative path to the telemetry CSV.")
    event_log_json: InputPath = Field(description="Relative path to the JSON event log.")
    event_log_csv: InputPath = Field(description="Relative path to the CSV event log.")

    @field_validator("subsystems")
    @classmethod
    def _subsystems_are_unique(cls, value: list[str]) -> list[str]:
        ensure_unique(value, "subsystems")
        return value

    @model_validator(mode="after")
    def _fault_fits_scenario(self) -> Self:
        if self.fault.target_subsystem not in self.subsystems:
            raise ValueError("fault.target_subsystem must be listed in scenario.subsystems")
        fault_end = self.fault.start_met_seconds + self.fault.duration_seconds
        if fault_end > self.duration_seconds:
            raise ValueError("fault must end within the scenario duration")
        if self.sampling_interval_seconds > self.duration_seconds:
            raise ValueError("sampling interval cannot exceed scenario duration")
        intervals = self.duration_seconds / self.sampling_interval_seconds
        if not math.isclose(intervals, round(intervals), abs_tol=1e-6):
            raise ValueError(
                "scenario duration must be an integer multiple of the sampling interval"
            )
        return self
