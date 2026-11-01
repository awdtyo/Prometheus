"""Tests for the judge: claim validation and scoring."""

from __future__ import annotations

from datetime import UTC, datetime

from autopsy.analysis.scoring import score_hypotheses, validate_claims
from autopsy.schemas.enums import RelationshipType
from autopsy.schemas.events import MissionEvent
from autopsy.schemas.evidence import Evidence, EvidenceStance, EvidenceType
from autopsy.schemas.graph import Graph, GraphEdge, GraphNode
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


def test_score_hypotheses_correct_chain_outscores_decoy():
    """A hand-built case: the correct causal chain (matching subsystem +
    graph edges) scores non-zero and clearly above a decoy chain."""
    ts = datetime(2026, 3, 14, 8, 15, tzinfo=UTC)
    obs = [
        _obs("obs_eps_1", "eps", ts),
        _obs("obs_eps_2", "eps", ts),
        _obs("obs_eps_3", "eps", ts),
        _obs("obs_tcs_1", "tcs", ts),
    ]
    graph = Graph(
        nodes=[
            GraphNode(node_id="obs:obs_eps_1", node_type="observation", label="e1", timestamp=ts),
            GraphNode(node_id="obs:obs_eps_2", node_type="observation", label="e2", timestamp=ts),
            GraphNode(node_id="obs:obs_eps_3", node_type="observation", label="e3", timestamp=ts),
            GraphNode(node_id="obs:obs_tcs_1", node_type="observation", label="t1", timestamp=ts),
        ],
        edges=[
            GraphEdge(
                edge_id="edge_eps_1_2",
                source="obs:obs_eps_1",
                target="obs:obs_eps_2",
                relationship_type=RelationshipType.TEMPORAL_PRECEDENCE,
                evidence_ids=[],
                confidence=0.8,
                metadata={},
            ),
            GraphEdge(
                edge_id="edge_eps_2_3",
                source="obs:obs_eps_2",
                target="obs:obs_eps_3",
                relationship_type=RelationshipType.TEMPORAL_PRECEDENCE,
                evidence_ids=[],
                confidence=0.8,
                metadata={},
            ),
        ],
    )
    correct = Hypothesis(
        hypothesis_id="h_correct",
        title="correct",
        summary="eps chain with edges",
        causal_chain=["obs:obs_eps_1", "obs:obs_eps_2", "obs:obs_eps_3"],
        evidence_ids=["ev_eps_chain"],
        contradiction_ids=[],
        assumptions=[],
        confidence=0.5,
        score=0.0,
    )
    decoy = Hypothesis(
        hypothesis_id="h_decoy",
        title="decoy",
        summary="tcs single node",
        causal_chain=["obs:obs_tcs_1"],
        evidence_ids=["ev_tcs_chain"],
        contradiction_ids=[],
        assumptions=[],
        confidence=0.5,
        score=0.0,
    )
    result = score_hypotheses([decoy, correct], [], graph, obs, events=[])
    scores = [h.score for h in result.hypotheses]
    assert scores == sorted(scores, reverse=True)
    assert result.hypotheses[0].hypothesis_id == "h_correct"
    assert result.hypotheses[0].score > 0.0
    assert result.hypotheses[0].score > result.hypotheses[1].score
    assert all(0.0 <= s <= 1.0 for s in scores)
    # scores vary across hypotheses
    assert len({round(s, 4) for s in scores}) > 1


def test_preliminary_evidence_not_counted_as_verified():
    """A hypothesis whose only evidence id is auto-filled (preliminary) scores
    lower than an identical hypothesis backed by prosecutor-verified evidence."""
    ts = datetime(2026, 3, 14, 8, 15, tzinfo=UTC)
    obs = [_obs("obs_eps_1", "eps", ts)]
    graph = Graph(
        nodes=[
            GraphNode(node_id="obs:obs_eps_1", node_type="observation", label="e1", timestamp=ts)
        ],
        edges=[],
    )
    verified = _evidence("ev_real", "obs:obs_eps_1", ts, stance=EvidenceStance.SUPPORTS)
    verified.reliability = 0.9

    verified_hyp = Hypothesis(
        hypothesis_id="h_verified",
        title="verified",
        summary="backed by real evidence",
        causal_chain=["obs:obs_eps_1"],
        evidence_ids=["ev_real"],
        contradiction_ids=[],
        assumptions=[],
        confidence=0.5,
        score=0.0,
    )
    preliminary_hyp = Hypothesis(
        hypothesis_id="h_preliminary",
        title="preliminary",
        summary="only auto-filled citation",
        causal_chain=["obs:obs_eps_1"],
        evidence_ids=["obs:obs_eps_1"],
        contradiction_ids=[],
        assumptions=[],
        confidence=0.5,
        score=0.0,
        metadata={"preliminary_evidence_ids": ["obs:obs_eps_1"]},
    )
    result = score_hypotheses(
        [preliminary_hyp, verified_hyp], [verified], graph, obs, events=[]
    )
    by_id = {h.hypothesis_id: h.score for h in result.hypotheses}
    assert by_id["h_verified"] > 0.0
    assert by_id["h_verified"] > by_id["h_preliminary"]
    # Both are non-zero because the chain explains the single observation.
    assert by_id["h_preliminary"] > 0.0
