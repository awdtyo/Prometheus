"""Unit tests for the twelve evaluation metrics.

Each test builds a tiny hand-made graph/observation/evidence/ground-truth
fixture and asserts *exact* metric values, so a metric that is trivially
satisfied (for example matching on subsystem only, or returning 1.0 for an
empty chain) is caught immediately.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from autopsy.evaluation.metrics import compute_evaluation_metrics
from autopsy.schemas.config import FaultConfig
from autopsy.schemas.enums import FaultType, RelationshipType
from autopsy.schemas.evaluation import GroundTruth
from autopsy.schemas.events import MissionEvent
from autopsy.schemas.evidence import Evidence, EvidenceStance, EvidenceType
from autopsy.schemas.graph import Graph, GraphEdge, GraphNode
from autopsy.schemas.hypotheses import Hypothesis
from autopsy.schemas.observations import Observation

TS = datetime(2026, 3, 14, 8, 0, tzinfo=UTC)


def _t(seconds: int) -> datetime:
    return TS + timedelta(seconds=seconds)


def _obs(obs_id: str, subsystem: str, seconds: int) -> Observation:
    return Observation(
        observation_id=obs_id,
        timestamp=TS + timedelta(seconds=seconds),
        subsystem=subsystem,
        observation_type="threshold_breach",
        description="d",
        observed_value=1.0,
        threshold=None,
        severity="medium",
        source_ids=[obs_id],
    )


def _evt(event_id: str, subsystem: str, seconds: int) -> MissionEvent:
    return MissionEvent(
        event_id=event_id,
        event_type="telemetry_anomaly_detected",
        subsystem=subsystem,
        timestamp=TS + timedelta(seconds=seconds),
        severity="medium",
        description="e",
    )


def _evidence(
    evidence_id: str,
    source_id: str,
    stance: EvidenceStance,
    reliability: float = 0.9,
) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        source_id=source_id,
        timestamp=datetime(2026, 3, 14, 8, 0, 0, tzinfo=UTC),
        evidence_type=EvidenceType.OBSERVATION,
        description="d",
        supports_or_contradicts=stance,
        reliability=reliability,
    )


def _graph(edges: list[tuple[str, str, float]]) -> Graph:
    nodes: list[GraphNode] = []
    edge_objs: list[GraphEdge] = []
    for i, (a, b, conf) in enumerate(edges):
        nodes.append(
            GraphNode(node_id=a, node_type="observation", label=a, timestamp=_t(0))
        )
        nodes.append(
            GraphNode(node_id=b, node_type="observation", label=b, timestamp=_t(0))
        )
        edge_objs.append(
            GraphEdge(
                edge_id=f"e{i}",
                source=a,
                target=b,
                relationship_type=RelationshipType.TEMPORAL_PRECEDENCE,
                evidence_ids=[],
                confidence=conf,
                metadata={},
            )
        )
    return Graph(nodes=nodes, edges=edge_objs)


def _gt(target_subsystem: str, step_subsystems: list[str]) -> GroundTruth:
    steps = []
    for i, sub in enumerate(step_subsystems, 1):
        steps.append(
            {
                "step": i,
                "timestamp": TS + timedelta(seconds=i * 60),
                "subsystem": sub,
                "event_type": "telemetry_anomaly_detected",
                "description": "s",
                "evidence_ids": [],
            }
        )
    return GroundTruth(
        scenario_id="scenario",
        synthetic=True,
        injected_fault=FaultConfig(
            fault_type=FaultType.POWER_DEGRADATION,
            target_subsystem=target_subsystem,
            start_time=datetime(2026, 3, 14, 8, 0, tzinfo=UTC),
            duration_seconds=100.0,
            magnitude=0.5,
        ),
        expected_causal_sequence=steps,
        expected_terminal_state="safe_mode",
    )


def _hypo(
    chain: list[str],
    evidence_ids: list[str] | None = None,
    contradiction_ids: list[str] | None = None,
) -> Hypothesis:
    if evidence_ids is None:
        evidence_ids = [chain[0]] if chain else ["obs:obs_x_1"]
    return Hypothesis(
        hypothesis_id="h1",
        title="t",
        summary="s",
        causal_chain=chain,
        evidence_ids=evidence_ids,
        contradiction_ids=contradiction_ids or [],
        assumptions=[],
        confidence=0.5,
        score=0.0,
    )


def _run(chain, observations, events, graph, ground_truth, evidence=None, runtime_seconds=1.0):
    if evidence is None:
        evidence_ids = [chain[0]] if chain else ["obs:obs_x_1"]
    else:
        evidence_ids = [e.evidence_id for e in evidence]
    return compute_evaluation_metrics(
        [_hypo(chain, evidence_ids=evidence_ids, contradiction_ids=[])]
        if chain
        else [],
        evidence or [],
        graph,
        observations,
        events,
        ground_truth,
        runtime_seconds,
    )


# ---- perfect hypothesis ---------------------------------------------------

def test_perfect_hypothesis_all_ones_or_near():
    obs = [_obs("obs_eps_1", "eps", 100), _obs("obs_eps_2", "eps", 200),
           _obs("obs_tcs_1", "tcs", 150), _obs("obs_adcs_1", "adcs", 300)]
    events = [_evt("evt_001", "eps", 100)]
    graph = _graph([("obs:obs_eps_1", "obs:obs_eps_2", 0.9)])
    gt = _gt("eps", ["eps", "tcs"])
    m = _run(["obs:obs_eps_1", "obs:obs_eps_2"], obs, events, graph, gt,
             evidence=[_evidence("ev1", "obs:obs_eps_1", EvidenceStance.SUPPORTS)])
    assert m["root_cause_accuracy"] == 1.0
    assert m["fault_localization_accuracy"] == 1.0
    # chain names eps (step 1) but not tcs (step 2)
    assert m["causal_chain_accuracy"] == 0.5
    # chain subsystem {eps} explains the two eps observations
    assert m["evidence_coverage"] == 0.5
    assert m["temporal_ordering_accuracy"] == 1.0
    assert m["contradiction_handling"] == 1.0
    # both links are graph edges
    assert m["unsupported_claim_rate"] == 0.0


# ---- wrong subsystem ------------------------------------------------------

def test_wrong_subsystem_scores_zero_root_cause():
    obs = [_obs("obs_tcs_1", "tcs", 100), _obs("obs_adcs_1", "adcs", 200)]
    events = []
    graph = _graph([("obs:obs_tcs_1", "obs:obs_adcs_1", 0.8)])
    gt = _gt("eps", ["eps"])
    m = _run(["obs:obs_tcs_1", "obs:obs_adcs_1"], obs, events, graph, gt)
    assert m["root_cause_accuracy"] == 0.0      # chain names tcs/adcs, not eps
    assert m["fault_localization_accuracy"] == 0.0
    assert m["causal_chain_accuracy"] == 0.0    # no chain node names eps
    # coverage is subsystem-scoped: the chain names tcs and adcs, which are
    # exactly the observation subsystems
    assert m["evidence_coverage"] == 1.0
    assert m["temporal_ordering_accuracy"] == 1.0
    assert m["unsupported_claim_rate"] == 0.0   # the one link is a graph edge


def test_right_subsystem_wrong_component():
    obs = [_obs("obs_eps_1", "eps", 100), _obs("obs_eps_2", "eps", 200),
           _obs("obs_eps_3", "eps", 300)]
    events = []
    graph = _graph([])  # no edges
    gt = _gt("eps", ["eps"])
    m = _run(["obs:obs_eps_99"], obs, events, graph, gt)
    # obs_eps_99 does not resolve to a real observation, so the chain names no
    # real subsystem
    assert m["root_cause_accuracy"] == 0.0
    assert m["fault_localization_accuracy"] == 0.0
    assert m["causal_chain_accuracy"] == 0.0
    assert m["evidence_coverage"] == 0.0        # chain names no real subsystem
    assert m["temporal_ordering_accuracy"] == 1.0   # single node
    assert m["unsupported_claim_rate"] == 0.0   # single node, no links


# ---- hardware-blamed decoy ------------------------------------------------

def test_decoy_hardware_blame_scores_wrong_root_cause():
    obs = [_obs("obs_tcs_1", "tcs", 100), _obs("obs_tcs_2", "tcs", 200)]
    events = []
    graph = _graph([("obs:obs_tcs_1", "obs:obs_tcs_2", 0.9)])
    gt = _gt("eps", ["eps"])   # truth: eps power fault, hardware fine
    m = _run(["obs:obs_tcs_1", "obs:obs_tcs_2"], obs, events, graph, gt)
    assert m["root_cause_accuracy"] == 0.0   # blames tcs, not eps
    assert m["fault_localization_accuracy"] == 0.0


# ---- empty chain ----------------------------------------------------------

def test_empty_chain():
    obs = [_obs("obs_eps_1", "eps", 100)]
    events = []
    graph = _graph([])
    gt = _gt("eps", ["eps"])
    m = _run([], obs, events, graph, gt)
    assert m["root_cause_accuracy"] == 0.0
    assert m["fault_localization_accuracy"] == 0.0
    assert m["causal_chain_accuracy"] == 0.0
    assert m["evidence_coverage"] == 0.0
    assert m["temporal_ordering_accuracy"] == 1.0   # < 2 timestamps
    assert m["unsupported_claim_rate"] == 0.0   # < 2 chain nodes


# ---- all claims fabricated ------------------------------------------------

def test_all_claims_fabricated():
    obs = [_obs("obs_eps_1", "eps", 100)]
    events = []
    graph = _graph([])
    gt = _gt("eps", ["eps"])
    m = _run(["obs:obs_eps_1"], obs, events, graph, gt,
             evidence=[_evidence("ev_fake", "obs:does_not_exist", EvidenceStance.SUPPORTS)])
    assert m["root_cause_accuracy"] == 1.0
    assert m["evidence_coverage"] == 1.0
    # fabricated evidence is not supporting (source id unknown), so supporting count is 0
    assert m["contradiction_handling"] == 1.0


# ---- all claims verified --------------------------------------------------

def test_all_claims_verified():
    obs = [_obs("obs_eps_1", "eps", 100)]
    events = []
    graph = _graph([])
    gt = _gt("eps", ["eps"])
    m = _run(["obs:obs_eps_1"], obs, events, graph, gt,
             evidence=[_evidence("ev1", "obs:obs_eps_1", EvidenceStance.SUPPORTS, 0.9)])
    assert m["root_cause_accuracy"] == 1.0
    assert m["contradiction_handling"] == 1.0


# ---- reversed temporal order ---------------------------------------------

def test_reversed_temporal_order():
    obs = [_obs("obs_eps_1", "eps", 300), _obs("obs_eps_2", "eps", 100)]
    events = []
    graph = _graph([("obs:obs_eps_1", "obs:obs_eps_2", 0.9)])
    gt = _gt("eps", ["eps"])
    m = _run(["obs:obs_eps_1", "obs:obs_eps_2"], obs, events, graph, gt)
    assert m["root_cause_accuracy"] == 1.0
    assert m["temporal_ordering_accuracy"] == 0.0   # 300 then 100 is decreasing
    assert m["unsupported_claim_rate"] == 0.0


# ---- metrics reach both 0 and 1 and disagree sensibly ---------------------

def test_metrics_disagree_sensibly():
    # all claims unsupported -> low evidence coverage should still hold because
    # coverage is subsystem-based, while unsupported_claim_rate is graph-based.
    obs = [_obs("obs_eps_1", "eps", 100), _obs("obs_tcs_1", "tcs", 200)]
    events = []
    graph = _graph([])
    gt = _gt("eps", ["eps", "tcs"])
    m = _run(["obs:obs_eps_1"], obs, events, graph, gt)
    assert m["evidence_coverage"] == 0.5   # chain subsystem {eps} explains one of two obs
    assert m["unsupported_claim_rate"] == 0.0   # single-node chain, no links
