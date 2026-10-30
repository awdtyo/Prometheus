"""Strongly typed domain contracts for Mission Autopsy.

The models in this package are independent of FastAPI, the backend package, and
persistence. They define the JSON-compatible shapes exchanged between ingestion,
simulation, graph construction, hypothesis generation, and analysis.

Import the public surface from this module::

    from autopsy.schemas import TelemetryRecord

JSON helpers are inherited from :class:`AutopsyModel`::

    payload = record.to_json()
    restored = TelemetryRecord.from_json(payload)
"""

from autopsy.schemas.base import (
    AutopsyModel,
    Description,
    EntityId,
    JsonObject,
    Label,
    ParameterName,
    SourceId,
    SubsystemId,
    TypeName,
    Unit,
    UtcDatetime,
)
from autopsy.schemas.config import AgentConfig, FaultConfig, InvestigationConfig, ScoringConfig
from autopsy.schemas.enums import (
    EvidenceStance,
    EvidenceType,
    FaultType,
    NodeType,
    RelationshipType,
    RunStatus,
    Severity,
)
from autopsy.schemas.events import MissionEvent
from autopsy.schemas.evidence import Evidence
from autopsy.schemas.graph import Graph, GraphEdge, GraphNode
from autopsy.schemas.hypotheses import Hypothesis
from autopsy.schemas.observations import Observation
from autopsy.schemas.results import RunResult, RunTimestamps
from autopsy.schemas.telemetry import TelemetryRecord

SCHEMA_VERSION = "1.0.0"

__all__ = [
    "SCHEMA_VERSION",
    "AgentConfig",
    "AutopsyModel",
    "Description",
    "EntityId",
    "Evidence",
    "EvidenceStance",
    "EvidenceType",
    "FaultConfig",
    "FaultType",
    "Graph",
    "GraphEdge",
    "GraphNode",
    "Hypothesis",
    "InvestigationConfig",
    "JsonObject",
    "Label",
    "MissionEvent",
    "NodeType",
    "Observation",
    "ParameterName",
    "RelationshipType",
    "RunResult",
    "RunStatus",
    "RunTimestamps",
    "ScoringConfig",
    "Severity",
    "SourceId",
    "SubsystemId",
    "TelemetryRecord",
    "TypeName",
    "Unit",
    "UtcDatetime",
]
