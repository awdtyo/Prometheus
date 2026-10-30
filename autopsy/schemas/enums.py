"""Controlled vocabularies used by the domain contracts."""

from enum import StrEnum


class NodeType(StrEnum):
    """Kind of entity represented by a graph node."""

    SUBSYSTEM = "subsystem"
    PARAMETER = "parameter"
    TELEMETRY = "telemetry"
    EVENT = "event"
    OBSERVATION = "observation"
    EVIDENCE = "evidence"
    HYPOTHESIS = "hypothesis"


class RelationshipType(StrEnum):
    """Semantics of a directed graph edge.

    The values intentionally match the protocol tokens used in the project
    specification so that serialized graphs are unambiguous.
    """

    TEMPORAL_PRECEDENCE = "TEMPORAL_PRECEDENCE"
    SUBSYSTEM_DEPENDENCY = "SUBSYSTEM_DEPENDENCY"
    OBSERVED_CORRELATION = "OBSERVED_CORRELATION"
    CAUSAL_HYPOTHESIS = "CAUSAL_HYPOTHESIS"
    CONTRADICTS = "CONTRADICTS"


class Severity(StrEnum):
    """Operational severity shared by events and observations."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RunStatus(StrEnum):
    """Lifecycle state of one investigation run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EvidenceType(StrEnum):
    """Source category for a piece of evidence."""

    TELEMETRY = "telemetry"
    EVENT = "event"
    OBSERVATION = "observation"
    GRAPH_RELATION = "graph_relation"
    EXTERNAL_REPORT = "external_report"


class EvidenceStance(StrEnum):
    """Whether evidence supports or contradicts a claim."""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"


class FaultType(StrEnum):
    """Fault families that the simulator will eventually inject."""

    POWER_LOSS = "power_loss"
    POWER_DEGRADATION = "power_degradation"
    THERMAL_OVERHEAT = "thermal_overheat"
    SENSOR_DRIFT = "sensor_drift"
    SENSOR_FAILURE = "sensor_failure"
    COMMUNICATION_LOSS = "communication_loss"
    ACTUATOR_FAILURE = "actuator_failure"
    SOFTWARE_FAULT = "software_fault"
    UNKNOWN = "unknown"
