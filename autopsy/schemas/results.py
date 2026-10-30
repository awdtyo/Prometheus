"""Run result and lifecycle timestamp contracts."""

from __future__ import annotations

import math
from typing import Self

from pydantic import Field, field_validator, model_validator

from autopsy.schemas.base import AutopsyModel, EntityId, UtcDatetime, ensure_unique
from autopsy.schemas.enums import RunStatus
from autopsy.schemas.graph import Graph
from autopsy.schemas.hypotheses import Hypothesis
from autopsy.schemas.observations import Observation


class RunTimestamps(AutopsyModel):
    """Lifecycle timestamps for one investigation run, all in UTC."""

    created_at: UtcDatetime = Field(description="When the run record was created.")
    started_at: UtcDatetime | None = Field(
        default=None,
        description="When execution started.",
    )
    completed_at: UtcDatetime | None = Field(
        default=None,
        description="When execution reached a terminal state.",
    )

    @model_validator(mode="after")
    def _chronological_order(self) -> Self:
        if self.started_at is not None and self.started_at < self.created_at:
            raise ValueError("started_at cannot be earlier than created_at")
        if self.completed_at is not None:
            last_started = self.started_at or self.created_at
            if self.completed_at < last_started:
                raise ValueError("completed_at cannot be earlier than started_at or created_at")
        return self


class RunResult(AutopsyModel):
    """Serializable output of one investigation run."""

    run_id: EntityId = Field(description="Stable unique run identifier.")
    scenario_id: EntityId = Field(description="Stable unique scenario identifier.")
    status: RunStatus = Field(description="Lifecycle state of the run.")
    observations: list[Observation] = Field(
        default_factory=list,
        description="Observations derived during the run.",
    )
    graph: Graph = Field(
        default_factory=Graph,
        description="Causal and temporal graph snapshot.",
    )
    hypotheses: list[Hypothesis] = Field(
        default_factory=list,
        description="Competing hypotheses produced by the run.",
    )
    investigation_report: str | None = Field(
        default=None,
        min_length=1,
        description="Optional Markdown investigation report.",
    )
    evaluation_metrics: dict[str, float] = Field(
        default_factory=dict,
        description="Finite numeric evaluation metrics keyed by metric name.",
    )
    timestamps: RunTimestamps = Field(description="Run lifecycle timestamps.")

    @field_validator("observations")
    @classmethod
    def _observation_ids_are_unique(cls, value: list[Observation]) -> list[Observation]:
        ensure_unique([observation.observation_id for observation in value], "observation_id")
        return value

    @field_validator("hypotheses")
    @classmethod
    def _hypothesis_ids_are_unique(cls, value: list[Hypothesis]) -> list[Hypothesis]:
        ensure_unique([hypothesis.hypothesis_id for hypothesis in value], "hypothesis_id")
        return value

    @field_validator("evaluation_metrics")
    @classmethod
    def _metrics_are_finite(cls, value: dict[str, float]) -> dict[str, float]:
        for name, metric in value.items():
            if not name.strip():
                raise ValueError("evaluation metric names must not be empty")
            if not math.isfinite(metric):
                raise ValueError(f"evaluation metric '{name}' must be finite")
        return value

    @model_validator(mode="after")
    def _status_matches_timestamps(self) -> Self:
        timestamps = self.timestamps
        if self.status is RunStatus.PENDING:
            if timestamps.started_at is not None or timestamps.completed_at is not None:
                raise ValueError("pending runs cannot have started_at or completed_at")
        elif self.status is RunStatus.RUNNING:
            if timestamps.started_at is None:
                raise ValueError("running runs require started_at")
            if timestamps.completed_at is not None:
                raise ValueError("running runs cannot have completed_at")
        elif timestamps.completed_at is None:
            raise ValueError(f"{self.status.value} runs require completed_at")
        return self
