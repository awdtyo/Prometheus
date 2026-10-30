"""Request and response DTOs for investigation endpoints."""

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, computed_field

from backend.schemas.base import ApiModel, UtcDatetime


class InvestigationStatus(StrEnum):
    """Lifecycle states for an investigation."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InvestigationCreate(ApiModel):
    """Payload accepted by ``POST /api/v1/investigations``."""

    scenario_id: str = Field(min_length=1, max_length=128)
    title: str | None = Field(default=None, min_length=1, max_length=512)
    description: str | None = Field(default=None, max_length=4000)
    fault_type: str | None = Field(default=None, min_length=1, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)


class InvestigationResponse(ApiModel):
    """Current state and summary of one investigation."""

    id: str
    scenario_id: str
    title: str
    description: str | None = None
    fault_type: str | None = None
    status: InvestigationStatus
    progress: int = Field(ge=0, le=100)
    current_stage: str | None = None
    error_message: str | None = None
    created_at: UtcDatetime
    updated_at: UtcDatetime
    completed_at: UtcDatetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def investigation_id(self) -> str:
        """Explicit identifier alias matching the path parameter name."""
        return self.id


class InvestigationListResponse(ApiModel):
    """Cursor-paginated collection of investigations."""

    items: list[InvestigationResponse] = Field(default_factory=list)
    next_cursor: str | None = None


class HypothesisResponse(ApiModel):
    """One ranked causal explanation."""

    hypothesis_id: str
    title: str
    summary: str
    causal_chain: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    contradiction_ids: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    score: float = Field(ge=0.0, le=1.0)


class HypothesisListResponse(ApiModel):
    """Ranked hypotheses for one investigation."""

    investigation_id: str
    hypotheses: list[HypothesisResponse] = Field(default_factory=list)


class TimelineEventResponse(ApiModel):
    """One reconstructed event in the investigation timeline."""

    event_id: str
    timestamp: UtcDatetime
    subsystem: str
    event_type: str
    description: str
    severity: Literal["info", "low", "medium", "high", "critical"]
    metadata: dict[str, Any] = Field(default_factory=dict)


class TimelineResponse(ApiModel):
    """Chronological timeline for one investigation."""

    investigation_id: str
    events: list[TimelineEventResponse] = Field(default_factory=list)


class ProgressEvent(ApiModel):
    """Payload streamed over server-sent events while an investigation runs."""

    investigation_id: str
    status: InvestigationStatus
    stage: str
    progress: int = Field(ge=0, le=100)
    message: str
    timestamp: UtcDatetime
