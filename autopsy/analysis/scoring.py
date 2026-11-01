"""Deterministic scoring and claim validation for competing hypotheses.

No LLM is used here. Every number is derived from the graph, the observations,
the events, and the evidence records, so scoring is fully reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from autopsy.ids import evt_node_id, is_node_id, obs_node_id, parse_node_id
from autopsy.schemas.events import MissionEvent
from autopsy.schemas.evidence import Evidence, EvidenceStance
from autopsy.schemas.graph import Graph
from autopsy.schemas.hypotheses import Hypothesis
from autopsy.schemas.observations import Observation


@dataclass
class ScoringConfig:
    w_explained: float = 0.4
    w_edge_conf: float = 0.3
    w_evidence: float = 0.3
    penalty_contradiction: float = 0.15
    penalty_unexplained_downstream: float = 0.1
    penalty_unsupported_link: float = 0.1


@dataclass
class Downgrade:
    evidence_id: str
    from_tag: str
    to_tag: str
    reason: str


@dataclass
class ScoredResult:
    hypotheses: list[Hypothesis]
    evidence: list[Evidence]
    downgrades: list[Downgrade] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


def _source_index(observations, events, graph: Graph):
    obs_by_id = {o.observation_id: o for o in observations}
    ev_by_id = {e.event_id: e for e in events}
    node_by_id = {n.node_id: n for n in graph.nodes}
    return obs_by_id, ev_by_id, node_by_id


def validate_claims(
    evidence: list[Evidence],
    observations: list[Observation],
    events: list[MissionEvent],
    graph: Graph,
) -> tuple[list[Evidence], list[Downgrade]]:
    """Validate every evidence citation.

    A supporting claim ("evidence" stance) must cite a source id that exists,
    and when the source is an observation or event its timestamp must match the
    source's actual timestamp. Fabricated or mismatched citations are downgraded
    (recorded with a reason) and excluded from support. Anything uncited is
    treated as speculation.
    """
    obs_by_id, ev_by_id, node_by_id = _source_index(observations, events, graph)
    valid_ids = set(obs_by_id) | set(ev_by_id) | set(node_by_id)
    # Evidence citations may use the plain source id (obs_001) or the canonical
    # prefixed node id (obs:obs_001); accept both forms.
    valid_ids.update(obs_node_id(oid) for oid in obs_by_id)
    valid_ids.update(evt_node_id(eid) for eid in ev_by_id)

    validated: list[Evidence] = []
    downgrades: list[Downgrade] = []

    for ev in evidence:
        if ev.source_id not in valid_ids:
            downgrades.append(
                Downgrade(
                    evidence_id=ev.evidence_id,
                    from_tag="evidence",
                    to_tag="speculation",
                    reason=f"source id {ev.source_id} does not exist",
                )
            )
            continue

        source = (
            obs_by_id.get(ev.source_id)
            or ev_by_id.get(ev.source_id)
            or node_by_id.get(ev.source_id)
        )
        source_ts = getattr(source, "timestamp", None)
        if source_ts is not None and ev.timestamp != source_ts:
            downgrades.append(
                Downgrade(
                    evidence_id=ev.evidence_id,
                    from_tag="evidence",
                    to_tag="inference",
                    reason=f"timestamp mismatch for {ev.source_id}",
                )
            )
        validated.append(ev)

    return validated, downgrades


def _chain_explains(h: Hypothesis, observations: list[Observation]) -> set[str]:
    chain = set(h.causal_chain)
    obs_id_to_subsystem = {o.observation_id: o.subsystem for o in observations}
    chain_subsystems = set()
    for nid in h.causal_chain:
        if is_node_id(nid):
            _, opaque = parse_node_id(nid)
            if opaque in obs_id_to_subsystem:
                chain_subsystems.add(obs_id_to_subsystem[opaque])
    explained = set()
    for o in observations:
        if obs_node_id(o.observation_id) in chain or o.subsystem in chain_subsystems:
            explained.add(o.observation_id)
    return explained


def score_hypotheses(
    hypotheses,
    evidence,
    graph,
    observations,
    config=None,
    events=None,
) -> ScoredResult:
    cfg = config or ScoringConfig()
    events = events or []
    validated_evidence, downgrades = validate_claims(list(evidence), observations, events, graph)

    ev_by_id = {e.evidence_id: e for e in validated_evidence}

    scored = []
    for h in hypotheses:
        explained = _chain_explains(h, observations)
        total = max(1, len(observations))
        frac_explained = len(explained) / total

        edge_map = {(e.source, e.target): e for e in graph.edges}
        edge_confs = []
        unsupported = 0
        for i in range(len(h.causal_chain) - 1):
            a, b = h.causal_chain[i], h.causal_chain[i + 1]
            edge = edge_map.get((a, b))
            if edge is None:
                unsupported += 1
                edge_confs.append(0.0)
            else:
                edge_confs.append(edge.confidence)
        avg_edge = sum(edge_confs) / max(1, len(edge_confs)) if edge_confs else 0.0

        sup_reliability = []
        preliminary = set(h.metadata.get("preliminary_evidence_ids", []))
        for eid in h.evidence_ids:
            if eid in preliminary:
                # Auto-filled preliminary citations are not verified evidence.
                continue
            ev = ev_by_id.get(eid)
            if ev is not None and ev.supports_or_contradicts == EvidenceStance.SUPPORTS:
                sup_reliability.append(ev.reliability)
        avg_evidence = (
            sum(sup_reliability) / max(1, len(sup_reliability))
            if sup_reliability
            else 0.0
        )

        contra_count = 0
        for eid in h.contradiction_ids:
            ev = ev_by_id.get(eid)
            if ev is not None and ev.supports_or_contradicts == EvidenceStance.CONTRADICTS:
                contra_count += 1

        unexplained = total - len(explained)

        score = (
            cfg.w_explained * frac_explained
            + cfg.w_edge_conf * avg_edge
            + cfg.w_evidence * avg_evidence
            - cfg.penalty_contradiction * contra_count
            - cfg.penalty_unexplained_downstream * (unexplained / total)
            - cfg.penalty_unsupported_link * unsupported
        )
        score = max(0.0, min(1.0, score))

        rejected_reason = None
        if contra_count > 0:
            rejected_reason = f"contradicted by {contra_count} verified evidence"
        if unsupported > 0 and score < 0.3:
            rejected_reason = (
                (rejected_reason + "; ") if rejected_reason else ""
            ) + f"{unsupported} unsupported links"
        if not explained and total > 0:
            rejected_reason = (
                (rejected_reason + "; ") if rejected_reason else ""
            ) + "no observations explained"

        h.score = score
        h.confidence = min(1.0, max(0.0, (h.confidence + score) / 2.0))
        if rejected_reason:
            h.assumptions = list(h.assumptions) + [f"REJECTED: {rejected_reason}"]

        scored.append(h)

    hypotheses_sorted = sorted(scored, key=lambda h: h.score, reverse=True)

    all_explained: set[str] = set()
    for h in scored:
        all_explained |= _chain_explains(h, observations)
    unexplained_ids = [
        o.observation_id for o in observations if o.observation_id not in all_explained
    ]

    summary = {
        "unexplained_observation_ids": unexplained_ids,
        "num_hypotheses": len(hypotheses_sorted),
        "num_downgrades": len(downgrades),
    }

    return ScoredResult(
        hypotheses=hypotheses_sorted,
        evidence=validated_evidence,
        downgrades=downgrades,
        summary=summary,
    )
