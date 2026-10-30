"""Derived observation contract."""

from pydantic import Field, field_validator

from autopsy.schemas.base import (
    AutopsyModel,
    Description,
    EntityId,
    SubsystemId,
    TypeName,
    UtcDatetime,
    ensure_unique,
)
from autopsy.schemas.enums import Severity


class Observation(AutopsyModel):
    """An interpretation derived from telemetry or events.

    Observations are the bridge between raw evidence and graph construction.
    They always cite at least one source so a hypothesis can be traced back to
    the original data.
    """

    observation_id: EntityId = Field(description="Stable unique observation identifier.")
    timestamp: UtcDatetime = Field(description="Observation time in UTC.")
    subsystem: SubsystemId = Field(description="Subsystem identifier in kebab-case.")
    observation_type: TypeName = Field(
        description="Lowercase snake_case category, for example 'threshold_breach'."
    )
    description: Description = Field(description="Human-readable explanation of the observation.")
    observed_value: float = Field(description="Observed numeric value; must be finite.")
    threshold: float | None = Field(
        description="Threshold that makes the observation notable, or null if none applies.",
    )
    severity: Severity = Field(description="Operational severity of the observation.")
    source_ids: list[EntityId] = Field(
        min_length=1,
        description="Stable identifiers of the telemetry records, events, or evidence used.",
    )

    @field_validator("source_ids")
    @classmethod
    def _source_ids_are_unique(cls, value: list[str]) -> list[str]:
        ensure_unique(value, "source_ids")
        return value
