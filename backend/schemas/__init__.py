"""Pydantic request/response DTOs for the HTTP API.

API schemas are intentionally separate from ``autopsy.schemas`` domain contracts
so the wire contract can evolve without coupling the core package to HTTP.
"""

from backend.schemas.catalog import (
    ScenarioListResponse,
    ScenarioResponse,
    SubsystemListResponse,
    SubsystemResponse,
)
from backend.schemas.health import HealthResponse
from backend.schemas.investigation import (
    HypothesisListResponse,
    HypothesisResponse,
    InvestigationCreate,
    InvestigationListResponse,
    InvestigationResponse,
    InvestigationStatus,
    ProgressEvent,
    TimelineEventResponse,
    TimelineResponse,
)
from backend.schemas.problem import ProblemDetail, ValidationIssue

__all__ = [
    "HealthResponse",
    "HypothesisListResponse",
    "HypothesisResponse",
    "InvestigationCreate",
    "InvestigationListResponse",
    "InvestigationResponse",
    "InvestigationStatus",
    "ProblemDetail",
    "ProgressEvent",
    "ScenarioListResponse",
    "ScenarioResponse",
    "SubsystemListResponse",
    "SubsystemResponse",
    "TimelineEventResponse",
    "TimelineResponse",
    "ValidationIssue",
]
