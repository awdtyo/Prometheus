"""Subsystem YAML specification contracts."""

from __future__ import annotations

from typing import Self

from pydantic import Field, field_validator, model_validator

from autopsy.schemas.base import (
    AutopsyModel,
    Description,
    Label,
    ParameterName,
    SubsystemId,
    TypeName,
    Unit,
    ensure_unique,
)
from autopsy.schemas.enums import Severity


class ParameterSpec(AutopsyModel):
    """One monitored parameter and its operating thresholds.

    A parameter may define only low thresholds, only high thresholds, or both.
    ``nominal_min`` may equal ``nominal_max`` for counters that are expected to
    stay at a fixed value.
    """

    name: ParameterName = Field(description="Parameter name as used in telemetry.")
    unit: Unit = Field(description="Unit of the parameter, for example 'V' or 'degC'.")
    nominal_min: float = Field(description="Lower bound of the nominal range.")
    nominal_max: float = Field(description="Upper bound of the nominal range.")
    warning_low: float | None = Field(
        default=None,
        description="Low warning threshold, below the nominal range.",
    )
    warning_high: float | None = Field(
        default=None,
        description="High warning threshold, above the nominal range.",
    )
    critical_low: float | None = Field(
        default=None,
        description="Low critical threshold, below the warning threshold.",
    )
    critical_high: float | None = Field(
        default=None,
        description="High critical threshold, above the warning threshold.",
    )
    description: Description = Field(description="What the parameter measures.")

    @model_validator(mode="after")
    def _thresholds_are_ordered(self) -> Self:
        if self.nominal_min > self.nominal_max:
            raise ValueError("nominal_min must be less than or equal to nominal_max")
        if self.warning_low is not None and self.warning_low >= self.nominal_min:
            raise ValueError("warning_low must be below nominal_min")
        if self.warning_high is not None and self.warning_high <= self.nominal_max:
            raise ValueError("warning_high must be above nominal_max")
        if self.critical_low is not None:
            if self.warning_low is None:
                raise ValueError("critical_low requires warning_low")
            if self.critical_low >= self.warning_low:
                raise ValueError("critical_low must be below warning_low")
        if self.critical_high is not None:
            if self.warning_high is None:
                raise ValueError("critical_high requires warning_high")
            if self.critical_high <= self.warning_high:
                raise ValueError("critical_high must be above warning_high")
        return self


class EventSpec(AutopsyModel):
    """An event type that a subsystem may emit."""

    event_type: TypeName = Field(description="Lowercase snake_case event type.")
    description: Description = Field(description="What the event means.")
    severity: Severity = Field(description="Expected severity of the event.")


class SubsystemSpec(AutopsyModel):
    """Declarative definition of one spacecraft subsystem."""

    id: SubsystemId = Field(description="Stable kebab-case subsystem identifier.")
    name: Label = Field(description="Human-readable subsystem name.")
    description: Description = Field(description="Responsibility of the subsystem.")
    monitored_parameters: list[ParameterSpec] = Field(
        min_length=1,
        description="Telemetry parameters monitored for this subsystem.",
    )
    dependencies: list[SubsystemId] = Field(
        default_factory=list,
        description="Subsystems this subsystem depends on.",
    )
    relevant_events: list[EventSpec] = Field(
        min_length=1,
        description="Event types this subsystem may emit.",
    )
    expected_downstream_effects: list[Description] = Field(
        min_length=1,
        description="Effects expected when this subsystem degrades.",
    )

    @field_validator("monitored_parameters")
    @classmethod
    def _parameter_names_are_unique(cls, value: list[ParameterSpec]) -> list[ParameterSpec]:
        ensure_unique([parameter.name for parameter in value], "monitored_parameters.name")
        return value

    @field_validator("dependencies")
    @classmethod
    def _dependencies_are_unique(cls, value: list[str]) -> list[str]:
        ensure_unique(value, "dependencies")
        return value

    @field_validator("relevant_events")
    @classmethod
    def _event_types_are_unique(cls, value: list[EventSpec]) -> list[EventSpec]:
        ensure_unique([event.event_type for event in value], "relevant_events.event_type")
        return value

    @model_validator(mode="after")
    def _does_not_depend_on_itself(self) -> Self:
        if self.id in self.dependencies:
            raise ValueError("a subsystem cannot depend on itself")
        return self
