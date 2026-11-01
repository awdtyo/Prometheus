"""Sanitized investigation inputs passed to analysis and hypothesis stages."""

from __future__ import annotations

from datetime import timedelta
from typing import Self

from pydantic import Field, model_validator

from autopsy.schemas.base import AutopsyModel, EntityId, Label, UtcDatetime, ensure_unique
from autopsy.schemas.events import MissionEvent
from autopsy.schemas.subsystems import SubsystemSpec
from autopsy.schemas.telemetry import TelemetryRecord


class InvestigationInputs(AutopsyModel):
    """Everything an investigation may use, with no fault or ground truth.

    This aggregate intentionally has no ``fault`` field and no reference to
    ``fixtures/expected/``. It is the only object that should be handed to
    hypothesis agents.
    """

    scenario_id: EntityId = Field(description="Stable scenario identifier.")
    scenario_name: Label = Field(description="Human-readable scenario name.")
    mission_start_utc: UtcDatetime = Field(description="Mission epoch in UTC.")
    duration_seconds: float = Field(gt=0.0, description="Scenario duration in seconds.")
    sampling_interval_seconds: float = Field(
        gt=0.0,
        description="Telemetry sampling interval in seconds.",
    )
    subsystems: list[SubsystemSpec] = Field(
        min_length=1,
        description="Subsystem definitions used by the investigation.",
    )
    telemetry: list[TelemetryRecord] = Field(
        min_length=1,
        description="Telemetry records available to the investigation.",
    )
    events: list[MissionEvent] = Field(
        min_length=1,
        description="Mission events available to the investigation.",
    )

    @model_validator(mode="after")
    def _inputs_are_consistent(self) -> Self:
        subsystem_ids = [subsystem.id for subsystem in self.subsystems]
        ensure_unique(subsystem_ids, "subsystems.id")
        known = set(subsystem_ids)

        unknown_telemetry = sorted(
            {record.subsystem for record in self.telemetry if record.subsystem not in known}
        )
        if unknown_telemetry:
            raise ValueError(
                f"telemetry references unknown subsystems: {', '.join(unknown_telemetry)}"
            )

        unknown_events = sorted(
            {event.subsystem for event in self.events if event.subsystem not in known}
        )
        if unknown_events:
            raise ValueError(f"events reference unknown subsystems: {', '.join(unknown_events)}")

        end = self.mission_start_utc + timedelta(seconds=self.duration_seconds)
        if any(
            record.timestamp < self.mission_start_utc or record.timestamp > end
            for record in self.telemetry
        ):
            raise ValueError("telemetry timestamps must fall within the scenario window")
        if any(
            event.timestamp < self.mission_start_utc or event.timestamp > end
            for event in self.events
        ):
            raise ValueError("event timestamps must fall within the scenario window")
        if any(
            later.timestamp < earlier.timestamp
            for earlier, later in zip(self.telemetry, self.telemetry[1:], strict=False)
        ):
            raise ValueError("telemetry must be ordered by timestamp")
        if any(
            later.timestamp < earlier.timestamp
            for earlier, later in zip(self.events, self.events[1:], strict=False)
        ):
            raise ValueError("events must be ordered by timestamp")
        return self
