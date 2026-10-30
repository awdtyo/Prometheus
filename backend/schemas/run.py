"""Wire models for investigation runs and their configuration."""

from enum import StrEnum
from typing import Any, Self

from pydantic import Field, model_validator

from backend.schemas.base import ApiModel, UtcDatetime
from backend.schemas.catalog import FaultConfig


class RunStatus(StrEnum):
    """Lifecycle states for a queued investigation run."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentConfig(ApiModel):
    """Configuration for the future hypothesis-generation stage."""

    enabled: bool = True
    max_hypotheses: int = Field(default=3, ge=1, le=20)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    model: str | None = Field(default=None, min_length=1, max_length=512)
    seed: int | None = None
    timeout_seconds: float = Field(default=60.0, gt=0)
    prompt_version: str | None = Field(default=None, min_length=1, max_length=512)


class ScoringConfig(ApiModel):
    """Weights used to rank hypotheses during analysis."""

    evidence_weight: float = Field(default=0.4, ge=0.0, le=1.0)
    consistency_weight: float = Field(default=0.35, ge=0.0, le=1.0)
    coverage_weight: float = Field(default=0.25, ge=0.0, le=1.0)
    contradiction_penalty: float = Field(default=0.2, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _weights_must_sum_to_one(self) -> Self:
        total = self.evidence_weight + self.consistency_weight + self.coverage_weight
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                "evidence_weight, consistency_weight, and coverage_weight must sum to 1.0"
            )
        return self


class InvestigationConfig(ApiModel):
    """Investigation options kept separate from the scenario definition."""

    fault_config: FaultConfig | None = None
    agent_config: AgentConfig = Field(default_factory=AgentConfig)
    scoring_config: ScoringConfig = Field(default_factory=ScoringConfig)


class RunCreate(ApiModel):
    """Payload accepted by ``POST /api/v1/runs``.

    The canonical shape nests ``investigation_config``. Flat fault/agent/scoring
    fields are accepted as a convenience and are mutually exclusive with the
    nested form.
    """

    scenario_id: str = Field(min_length=1, max_length=128)
    investigation_config: InvestigationConfig | None = None
    fault_config: FaultConfig | None = None
    agent_config: AgentConfig | None = None
    scoring_config: ScoringConfig | None = None
    title: str | None = Field(default=None, min_length=1, max_length=512)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _reject_mixed_config_shapes(self) -> Self:
        flat_fields = (
            self.fault_config,
            self.agent_config,
            self.scoring_config,
        )
        if self.investigation_config is not None and any(
            field is not None for field in flat_fields
        ):
            raise ValueError(
                "Provide either investigation_config or flat fault/agent/scoring fields, not both."
            )
        return self

    @property
    def resolved_investigation_config(self) -> InvestigationConfig:
        """Return the nested configuration or build one from flat fields."""
        if self.investigation_config is not None:
            return self.investigation_config
        return InvestigationConfig(
            fault_config=self.fault_config,
            agent_config=self.agent_config or AgentConfig(),
            scoring_config=self.scoring_config or ScoringConfig(),
        )


class RunResponse(ApiModel):
    """Immediate acknowledgement returned after a run is queued."""

    run_id: str
    scenario_id: str
    status: RunStatus
    title: str
    investigation_config: InvestigationConfig
    fault_config: FaultConfig | None = None
    queue_position: int | None = None
    created_at: UtcDatetime
    queued_at: UtcDatetime
    message: str
