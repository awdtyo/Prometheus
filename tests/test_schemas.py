"""Validation and JSON round-trip tests for the domain contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from autopsy.schemas import (
    SCHEMA_VERSION,
    AgentConfig,
    AutopsyModel,
    Evidence,
    EvidenceStance,
    EvidenceType,
    FaultConfig,
    FaultType,
    Graph,
    GraphEdge,
    GraphNode,
    Hypothesis,
    InvestigationConfig,
    MissionEvent,
    NodeType,
    Observation,
    RelationshipType,
    RunResult,
    RunStatus,
    RunTimestamps,
    ScoringConfig,
    Severity,
    TelemetryRecord,
)

T0 = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
T1 = T0 + timedelta(seconds=30)
T2 = T0 + timedelta(minutes=2)


def telemetry(**overrides: object) -> TelemetryRecord:
    values: dict[str, object] = {
        "timestamp": T0,
        "subsystem": "power",
        "parameter": "bus_voltage",
        "value": 28.1,
        "unit": "V",
        "source_id": "tel:bus-1",
    }
    values.update(overrides)
    return TelemetryRecord.model_validate(values)


def event(**overrides: object) -> MissionEvent:
    values: dict[str, object] = {
        "event_id": "evt_001",
        "timestamp": T1,
        "subsystem": "power",
        "event_type": "under_voltage",
        "description": "Bus voltage fell below the safe operating limit.",
        "severity": Severity.HIGH,
        "metadata": {"limit_v": 26.0},
    }
    values.update(overrides)
    return MissionEvent.model_validate(values)


def observation(**overrides: object) -> Observation:
    values: dict[str, object] = {
        "observation_id": "obs_001",
        "timestamp": T1,
        "subsystem": "power",
        "observation_type": "threshold_breach",
        "description": "Bus voltage was below the 26 V limit for 30 seconds.",
        "observed_value": 25.4,
        "threshold": 26.0,
        "severity": Severity.HIGH,
        "source_ids": ["tel:bus-1", "evt_001"],
    }
    values.update(overrides)
    return Observation.model_validate(values)


def node(node_id: str = "sub:power", **overrides: object) -> GraphNode:
    values: dict[str, object] = {
        "node_id": node_id,
        "node_type": NodeType.SUBSYSTEM,
        "label": "Power",
        "timestamp": T0,
        "metadata": {"critical": True},
    }
    values.update(overrides)
    return GraphNode.model_validate(values)


def edge(**overrides: object) -> GraphEdge:
    values: dict[str, object] = {
        "edge_id": "edg_001",
        "source": "sub:power",
        "target": "obs_001",
        "relationship_type": RelationshipType.SUBSYSTEM_DEPENDENCY,
        "evidence_ids": ["ev_001"],
        "confidence": 0.95,
        "metadata": {"note": "power feeds the observation"},
    }
    values.update(overrides)
    return GraphEdge.model_validate(values)


def graph() -> Graph:
    return Graph(
        nodes=[
            node(),
            node("obs_001", node_type=NodeType.OBSERVATION, label="Undervoltage", timestamp=T1),
        ],
        edges=[edge()],
    )


def evidence(**overrides: object) -> Evidence:
    values: dict[str, object] = {
        "evidence_id": "ev_001",
        "source_id": "tel:bus-1",
        "timestamp": T1,
        "evidence_type": EvidenceType.TELEMETRY,
        "description": "Bus voltage sample below limit.",
        "supports_or_contradicts": EvidenceStance.SUPPORTS,
        "reliability": 0.98,
    }
    values.update(overrides)
    return Evidence.model_validate(values)


def hypothesis(**overrides: object) -> Hypothesis:
    values: dict[str, object] = {
        "hypothesis_id": "hyp_001",
        "title": "Battery heater fault caused bus undervoltage",
        "summary": "A stuck heater drained the battery and caused the bus voltage to sag.",
        "causal_chain": ["Heater stuck on", "Battery depleted", "Bus voltage fell"],
        "evidence_ids": ["ev_001"],
        "contradiction_ids": [],
        "assumptions": ["Battery state of health was nominal before the fault"],
        "confidence": 0.82,
        "score": 0.79,
    }
    values.update(overrides)
    return Hypothesis.model_validate(values)


def fault(**overrides: object) -> FaultConfig:
    values: dict[str, object] = {
        "fault_type": FaultType.POWER_DEGRADATION,
        "target_subsystem": "power",
        "start_time": T0,
        "duration_seconds": 120.0,
        "magnitude": 0.25,
        "parameters": {"rate": 0.01},
    }
    values.update(overrides)
    return FaultConfig.model_validate(values)


def run_result(**overrides: object) -> RunResult:
    values: dict[str, object] = {
        "run_id": "run_001",
        "scenario_id": "scn_001",
        "status": RunStatus.COMPLETED,
        "observations": [observation()],
        "graph": graph(),
        "hypotheses": [hypothesis()],
        "investigation_report": "# Report\n\nBattery heater fault.",
        "evaluation_metrics": {"root_cause_accuracy": 1.0, "runtime_seconds": 4.2},
        "timestamps": RunTimestamps(created_at=T0, started_at=T0, completed_at=T2),
    }
    values.update(overrides)
    return RunResult.model_validate(values)


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------


def test_telemetry_round_trip_normalizes_offsets_to_utc() -> None:
    record = telemetry(timestamp=datetime(2026, 10, 30, 14, 0, tzinfo=timezone(timedelta(hours=2))))

    assert record.timestamp == T0
    assert record.timestamp.tzinfo is UTC
    assert '"timestamp":"2026-10-30T12:00:00Z"' in record.to_json()
    assert TelemetryRecord.from_json(record.to_json()) == record


def test_telemetry_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        telemetry(timestamp=datetime(2026, 10, 30, 12, 0))


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
def test_telemetry_rejects_non_finite_values(bad_value: float) -> None:
    with pytest.raises(ValidationError):
        telemetry(value=bad_value)


def test_telemetry_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        telemetry(unexpected="field")


def test_telemetry_requires_unit() -> None:
    with pytest.raises(ValidationError):
        TelemetryRecord.model_validate(
            {
                "timestamp": T0,
                "subsystem": "power",
                "parameter": "bus_voltage",
                "value": 28.1,
            }
        )


def test_telemetry_rejects_invalid_subsystem_id() -> None:
    with pytest.raises(ValidationError):
        telemetry(subsystem="Power Bus")


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


def test_mission_event_round_trip() -> None:
    item = event()

    assert MissionEvent.from_json(item.to_json()) == item
    assert '"severity":"high"' in item.to_json()


def test_mission_event_metadata_must_be_json_serializable() -> None:
    with pytest.raises(ValidationError, match="JSON-serializable"):
        event(metadata={"unsupported": object()})


def test_mission_event_rejects_unknown_severity() -> None:
    with pytest.raises(ValidationError):
        event(severity="catastrophic")


# ---------------------------------------------------------------------------
# Observations
# ---------------------------------------------------------------------------


def test_observation_round_trip() -> None:
    item = observation()

    assert Observation.from_json(item.to_json()) == item


def test_observation_requires_at_least_one_source() -> None:
    with pytest.raises(ValidationError):
        observation(source_ids=[])


def test_observation_rejects_duplicate_sources() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        observation(source_ids=["tel:bus-1", "tel:bus-1"])


def test_observation_accepts_explicit_null_threshold() -> None:
    item = observation(threshold=None)

    assert item.threshold is None
    assert '"threshold":null' in item.to_json()


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


def test_graph_round_trip() -> None:
    item = graph()

    assert Graph.from_json(item.to_json()) == item
    assert item.edges[0].relationship_type is RelationshipType.SUBSYSTEM_DEPENDENCY


def test_graph_rejects_duplicate_node_ids() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        Graph(nodes=[node(), node()], edges=[])


def test_graph_rejects_unknown_edge_endpoints() -> None:
    with pytest.raises(ValidationError, match="unknown node ids"):
        Graph(nodes=[node()], edges=[edge(target="missing")])


def test_graph_edge_rejects_self_loop() -> None:
    with pytest.raises(ValidationError, match="itself"):
        edge(source="sub:power", target="sub:power")


def test_graph_edge_rejects_duplicate_evidence() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        edge(evidence_ids=["ev_001", "ev_001"])


def test_graph_node_accepts_explicit_null_timestamp() -> None:
    item = node(timestamp=None)

    assert item.timestamp is None
    assert '"timestamp":null' in item.to_json()


def test_relationship_type_protocol_tokens_are_stable() -> None:
    assert {item.value for item in RelationshipType} == {
        "TEMPORAL_PRECEDENCE",
        "SUBSYSTEM_DEPENDENCY",
        "OBSERVED_CORRELATION",
        "CAUSAL_HYPOTHESIS",
        "CONTRADICTS",
    }


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


def test_evidence_round_trip() -> None:
    item = evidence()

    assert Evidence.from_json(item.to_json()) == item


def test_evidence_rejects_out_of_range_reliability() -> None:
    with pytest.raises(ValidationError):
        evidence(reliability=1.1)


def test_evidence_rejects_invalid_stance() -> None:
    with pytest.raises(ValidationError):
        evidence(supports_or_contradicts="maybe")


# ---------------------------------------------------------------------------
# Hypotheses
# ---------------------------------------------------------------------------


def test_hypothesis_round_trip() -> None:
    item = hypothesis()

    assert Hypothesis.from_json(item.to_json()) == item


def test_hypothesis_requires_evidence() -> None:
    with pytest.raises(ValidationError):
        hypothesis(evidence_ids=[])


def test_hypothesis_rejects_duplicate_evidence() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        hypothesis(evidence_ids=["ev_001", "ev_001"])


@pytest.mark.parametrize("field", ["confidence", "score"])
def test_hypothesis_rejects_out_of_range_scores(field: str) -> None:
    with pytest.raises(ValidationError):
        hypothesis(**{field: 1.01})


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_fault_config_round_trip() -> None:
    item = fault()

    assert FaultConfig.from_json(item.to_json()) == item


def test_fault_config_rejects_non_positive_duration() -> None:
    with pytest.raises(ValidationError):
        fault(duration_seconds=0)


def test_fault_config_rejects_negative_magnitude() -> None:
    with pytest.raises(ValidationError):
        fault(magnitude=-0.1)


def test_investigation_config_round_trip_with_defaults() -> None:
    item = InvestigationConfig(scenario_id="scn_001", fault_config=fault())

    assert isinstance(item.agent_config, AgentConfig)
    assert isinstance(item.scoring_config, ScoringConfig)
    assert InvestigationConfig.from_json(item.to_json()) == item


def test_scoring_weights_must_sum_to_one() -> None:
    with pytest.raises(ValidationError, match="must equal 1.0"):
        ScoringConfig(evidence_weight=0.5, consistency_weight=0.5, coverage_weight=0.5)


# ---------------------------------------------------------------------------
# Run results
# ---------------------------------------------------------------------------


def test_run_result_round_trip() -> None:
    item = run_result()

    assert RunResult.from_json(item.to_json()) == item
    assert item.status is RunStatus.COMPLETED


def test_run_result_completed_requires_completed_at() -> None:
    with pytest.raises(ValidationError, match="require completed_at"):
        run_result(timestamps=RunTimestamps(created_at=T0, started_at=T0))


def test_run_result_pending_rejects_started_at() -> None:
    with pytest.raises(ValidationError, match="pending runs"):
        run_result(
            status=RunStatus.PENDING,
            timestamps=RunTimestamps(created_at=T0, started_at=T0),
        )


def test_run_result_running_requires_started_at() -> None:
    with pytest.raises(ValidationError, match="running runs require started_at"):
        run_result(
            status=RunStatus.RUNNING,
            timestamps=RunTimestamps(created_at=T0),
        )


def test_run_result_timestamps_must_be_chronological() -> None:
    with pytest.raises(ValidationError, match="started_at"):
        RunTimestamps(created_at=T1, started_at=T0)


def test_run_result_rejects_duplicate_observation_ids() -> None:
    duplicate = observation(description="A second observation with the same identifier.")

    with pytest.raises(ValidationError, match="duplicate"):
        run_result(observations=[observation(), duplicate])


def test_run_result_rejects_non_finite_metrics() -> None:
    with pytest.raises(ValidationError):
        run_result(evaluation_metrics={"accuracy": float("nan")})


# ---------------------------------------------------------------------------
# Contract surface
# ---------------------------------------------------------------------------


def test_schema_version_is_set() -> None:
    assert SCHEMA_VERSION == "1.0.0"


@pytest.mark.parametrize(
    "model",
    [
        TelemetryRecord,
        MissionEvent,
        Observation,
        GraphNode,
        GraphEdge,
        Graph,
        Evidence,
        Hypothesis,
        RunTimestamps,
        RunResult,
        FaultConfig,
        AgentConfig,
        ScoringConfig,
        InvestigationConfig,
    ],
)
def test_every_contract_exports_json_schema(model: type[AutopsyModel]) -> None:
    schema = model.model_json_schema()

    assert schema["type"] == "object"
    assert schema["properties"]
