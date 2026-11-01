"""Tests for the judge: claim validation and scoring."""

from __future__ import annotations

from datetime import UTC, datetime

from autopsy.analysis.scoring import score_hypotheses, validate_claims
from autopsy.schemas.events import MissionEvent
from autopsy.schemas.evidence import Evidence, EvidenceStance, EvidenceType
from autopsy.schemas.graph import Graph, GraphNode
from autopsy.schemas.hypotheses import Hypothesis
from autopsy.schemas.observations import Observation


def _obs(obs_id, subsystem, ts):
    return Observation(
        observation_id=obs_id,
        timestamp=ts,
        subsystem=subsystem,
        observation_type="threshold_breach",
        description="d",
        observed_value=1.0,
        threshold=None,
        severity="medium",
        source_ids=[obs_id],
    )


def _evt(event_id, subsystem, ts):
    return MissionEvent(
        event_id=event_id,
        event_type="telemetry_anomaly_detected",
        subsystem=subsystem,
        timestamp=ts,
        severity="medium",
        description="e",
    )



def _graph(ts):
    return Graph(
        nodes=[GraphNode(node_id="obs:obs_001", node_type="observation", label="x", timestamp=ts)],
        edges=[],
    )

def _evidence(evidence_id, source_id, ts, stance=EvidenceStance.SUPPORTS):
    return Evidence(
        evidence_id=evidence_id,
        source_id=source_id,
        timestamp=ts,
        evidence_type=EvidenceType.OBSERVATION,
        description="d",
        supports_or_contradicts=stance,
        reliability=0.9,
    )


def test_validate_claims_rejects_fabricated_citation():
    ts = datetime(2026, 3, 14, 8, 15, tzinfo=UTC)
    obs = _obs("obs_001", "eps", ts)
    graph = _graph(ts)
    ev = _evidence("ev_fake", "obs:does_not_exist", ts)
    validated, downgrades = validate_claims([ev], [obs], [], graph)
    assert validated == []
    assert len(downgrades) == 1
    assert downgrades[0].to_tag == "speculation"
    assert "does not exist" in downgrades[0].reason


def test_validate_claims_downgrades_timestamp_mismatch():
    ts = datetime(2026, 3, 14, 8, 15, tzinfo=UTC)
    wrong = datetime(2026, 3, 14, 9, 0, tzinfo=UTC)
    obs = _obs("obs_001", "eps", ts)
    graph = _graph(ts)
    ev = _evidence("ev_ts", "obs:obs_001", wrong)
    validated, downgrades = validate_claims([ev], [obs], [], graph)
    assert len(validated) == 1
    assert len(downgrades) == 1
    assert downgrades[0].to_tag == "inference"
    assert "timestamp mismatch" in downgrades[0].reason


def test_validate_claims_keeps_valid_citation():
    ts = datetime(2026, 3, 14, 8, 15, tzinfo=UTC)
    obs = _obs("obs_001", "eps", ts)
    graph = _graph(ts)
    ev = _evidence("ev_ok", "obs:obs_001", ts)
    validated, downgrades = validate_claims([ev], [obs], [], graph)
    assert len(validated) == 1
    assert downgrades == []


def test_score_hypotheses_ranks_and_bounds_scores():
    ts = datetime(2026, 3, 14, 8, 15, tzinfo=UTC)
    obs = _obs("obs_001", "eps", ts)
    h1 = Hypothesis(
        hypothesis_id="h_a",
        title="A",
        summary="explains eps",
        causal_chain=["obs:obs_001"],
        evidence_ids=["ev_ok"],
        contradiction_ids=[],
        assumptions=[],
        confidence=0.9,
        score=0.0,
    )
    h2 = Hypothesis(
        hypothesis_id="h_b",
        title="B",
        summary="unrelated",
        causal_chain=["obs:obs_001"],
        evidence_ids=["obs:nonexistent"],
        contradiction_ids=[],
        assumptions=[],
        confidence=0.9,
        score=0.0,
    )
    graph = Graph(nodes=[], edges=[])
    ev = _evidence("ev_ok", "obs:obs_001", ts)
    result = score_hypotheses([h2, h1], [ev], graph, [obs], events=[])
    scores = [h.score for h in result.hypotheses]
    assert scores == sorted(scores, reverse=True)
    assert all(0.0 <= s <= 1.0 for s in scores)
    assert result.hypotheses[0].hypothesis_id == "h_a"
