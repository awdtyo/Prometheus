"""Evaluation-only ground-truth contracts.

Ground truth is never part of the inputs passed to hypothesis agents. Keep this
module and the files under ``fixtures/expected/`` on the evaluation side of the
boundary.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from autopsy.schemas.base import (
    AutopsyModel,
    Description,
    EntityId,
    SubsystemId,
    TypeName,
    UtcDatetime,
)
from autopsy.schemas.config import FaultConfig


class GroundTruthStep(AutopsyModel):
    """One expected step in the true causal sequence."""

    step: int = Field(ge=1, description="One-based position in the causal sequence.")
    timestamp: UtcDatetime = Field(description="When the step occurs, in UTC.")
    subsystem: SubsystemId = Field(description="Subsystem associated with the step.")
    event_type: TypeName = Field(description="Lowercase snake_case event type.")
    description: Description = Field(description="What happened and why.")
    evidence_ids: list[EntityId] = Field(
        default_factory=list,
        description="Event or observation identifiers that support this step.",
    )


class GroundTruth(AutopsyModel):
    """Injected fault and expected causal sequence for one scenario."""

    scenario_id: EntityId = Field(description="Scenario this ground truth belongs to.")
    synthetic: Literal[True] = Field(description="Marks the data as synthetic.")
    injected_fault: FaultConfig = Field(description="Fault that was actually injected.")
    expected_causal_sequence: list[GroundTruthStep] = Field(
        min_length=1,
        description="Expected causal steps from precursor to terminal state.",
    )
    expected_terminal_state: Literal["safe_mode", "mission_failure", "recovery"] = Field(
        description="Expected final spacecraft or mission state.",
    )
    notes: Description | None = Field(
        default=None,
        description="Evaluation notes; never pass to hypothesis agents.",
    )

    @model_validator(mode="after")
    def _sequence_is_ordered(self) -> Self:
        steps = [step.step for step in self.expected_causal_sequence]
        if steps != list(range(1, len(steps) + 1)):
            raise ValueError("expected_causal_sequence steps must be numbered 1..n in order")
        timestamps = [step.timestamp for step in self.expected_causal_sequence]
        if any(later < earlier for earlier, later in zip(timestamps, timestamps[1:], strict=False)):
            raise ValueError("expected_causal_sequence timestamps must be non-decreasing")
        if not any(
            step.subsystem == self.injected_fault.target_subsystem
            for step in self.expected_causal_sequence
        ):
            raise ValueError("expected_causal_sequence must include the fault target subsystem")
        return self
