"""Telemetry sample contract."""

from pydantic import Field

from autopsy.schemas.base import (
    AutopsyModel,
    ParameterName,
    SourceId,
    SubsystemId,
    Unit,
    UtcDatetime,
)


class TelemetryRecord(AutopsyModel):
    """One scalar sample from a telemetry channel at a UTC instant."""

    timestamp: UtcDatetime = Field(description="Sample time in UTC.")
    subsystem: SubsystemId = Field(description="Subsystem identifier in kebab-case.")
    parameter: ParameterName = Field(description="Channel or parameter name.")
    value: float = Field(description="Scalar sample value; must be finite.")
    unit: Unit = Field(description="Unit of the value, for example 'V' or 'degC'.")
    source_id: SourceId | None = Field(
        default=None,
        description="Optional stable identifier of the originating source or channel.",
    )
