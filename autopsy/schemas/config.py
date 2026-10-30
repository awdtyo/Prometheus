"""Investigation, fault-injection, agent, and scoring configuration contracts."""

from __future__ import annotations

import math
from typing import Self

from pydantic import Field, model_validator

from autopsy.schemas.base import (
    AutopsyModel,
    EntityId,
    JsonObject,
    Label,
    SubsystemId,
    UtcDatetime,
)
from autopsy.schemas.enums import FaultType


class FaultConfig(AutopsyModel):
    """One fault injection to apply during a simulated scenario.

    ``start_time`` is an absolute UTC instant. Scenario files may express a
    relative mission elapsed time (MET); ingestion converts it with
    ``mission_start_utc + timedelta(seconds=met_seconds)`` before constructing
    this model. ``magnitude`` is interpreted in units specific to ``fault_type``.
    """

    fault_type: FaultType = Field(description="Fault family to inject.")
    target_subsystem: SubsystemId = Field(description="Subsystem identifier in kebab-case.")
    start_time: UtcDatetime = Field(description="Fault start time in UTC.")
    duration_seconds: float = Field(
        gt=0.0,
        description="Fault duration in seconds; must be greater than zero.",
    )
    magnitude: float = Field(
        ge=0.0,
        description="Non-negative fault magnitude in fault-type-specific units.",
    )
    parameters: JsonObject = Field(
        default_factory=dict,
        description="Optional JSON-serializable fault parameters.",
    )


class AgentConfig(AutopsyModel):
    """Configuration for the hypothesis-generation stage."""

    enabled: bool = Field(default=True, description="Whether agent generation is enabled.")
    max_hypotheses: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Maximum number of competing hypotheses to request.",
    )
    temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Sampling temperature for model-backed agents.",
    )
    model: Label | None = Field(
        default=None,
        description="Optional model identifier; provider-specific.",
    )
    seed: int | None = Field(
        default=None,
        description="Optional deterministic seed for reproducible generation.",
    )
    timeout_seconds: float = Field(
        default=60.0,
        gt=0.0,
        description="Per-stage timeout in seconds.",
    )
    prompt_version: Label | None = Field(
        default=None,
        description="Optional prompt template version for reproducibility.",
    )


class ScoringConfig(AutopsyModel):
    """Weights used to rank competing hypotheses.

    The three positive weights must sum to 1.0. ``contradiction_penalty`` is
    applied separately and is not part of that sum.
    """

    evidence_weight: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Weight for supporting evidence.",
    )
    consistency_weight: float = Field(
        default=0.35,
        ge=0.0,
        le=1.0,
        description="Weight for consistency with telemetry and the graph.",
    )
    coverage_weight: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="Weight for explanatory coverage of observations.",
    )
    contradiction_penalty: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Penalty applied per unit of contradiction.",
    )

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> Self:
        total = self.evidence_weight + self.consistency_weight + self.coverage_weight
        if not math.isclose(total, 1.0, abs_tol=1e-6):
            raise ValueError(
                "evidence_weight + consistency_weight + coverage_weight must equal 1.0"
            )
        return self


class InvestigationConfig(AutopsyModel):
    """Complete input configuration for one investigation run."""

    scenario_id: EntityId = Field(description="Stable unique scenario identifier.")
    fault_config: FaultConfig = Field(description="Fault to inject for this run.")
    agent_config: AgentConfig = Field(
        default_factory=AgentConfig,
        description="Hypothesis-generation configuration.",
    )
    scoring_config: ScoringConfig = Field(
        default_factory=ScoringConfig,
        description="Hypothesis-ranking configuration.",
    )
