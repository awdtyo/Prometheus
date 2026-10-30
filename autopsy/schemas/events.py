"""Discrete mission event contract."""

from pydantic import Field

from autopsy.schemas.base import (
    AutopsyModel,
    Description,
    EntityId,
    JsonObject,
    SubsystemId,
    TypeName,
    UtcDatetime,
)
from autopsy.schemas.enums import Severity


class MissionEvent(AutopsyModel):
    """A timestamped, human-meaningful event from the mission timeline."""

    event_id: EntityId = Field(description="Stable unique event identifier.")
    timestamp: UtcDatetime = Field(description="Event time in UTC.")
    subsystem: SubsystemId = Field(description="Subsystem identifier in kebab-case.")
    event_type: TypeName = Field(
        description="Lowercase snake_case event category, for example 'mode_change'."
    )
    description: Description = Field(description="Human-readable event description.")
    severity: Severity = Field(description="Operational severity of the event.")
    metadata: JsonObject = Field(
        default_factory=dict,
        description="Additional JSON-serializable event attributes.",
    )
