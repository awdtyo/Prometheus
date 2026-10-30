"""Pydantic request/response DTOs for the HTTP API.

API schemas are intentionally separate from ``autopsy.schemas`` domain contracts
so the wire contract can evolve without coupling the core package to HTTP.
"""

from backend.schemas.catalog import (
    FaultConfig,
    FaultOptionResponse,
    FaultType,
    ScenarioDetailResponse,
    ScenarioInjectionResponse,
    ScenarioListResponse,
    ScenarioResponse,
    SubsystemListResponse,
    SubsystemResponse,
    TelemetryParameterResponse,
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
from backend.schemas.run import (
    AgentConfig,
    InvestigationConfig,
    RunCreate,
    RunResponse,
    RunStatus,
    ScoringConfig,
)

__all__ = [
    "AgentConfig",
    "FaultConfig",
    "FaultOptionResponse",
    "FaultType",
    "HealthResponse",
    "HypothesisListResponse",
    "HypothesisResponse",
    "InvestigationCreate",
    "InvestigationConfig",
    "InvestigationListResponse",
    "InvestigationResponse",
    "InvestigationStatus",
    "ProblemDetail",
    "ProgressEvent",
    "RunCreate",
    "RunResponse",
    "RunStatus",
    "ScenarioDetailResponse",
    "ScenarioInjectionResponse",
    "ScenarioListResponse",
    "ScenarioResponse",
    "ScoringConfig",
    "SubsystemListResponse",
    "SubsystemResponse",
    "TelemetryParameterResponse",
    "TimelineEventResponse",
    "TimelineResponse",
    "ValidationIssue",
]
