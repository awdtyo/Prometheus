from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from autopsy.schemas.evidence import Evidence
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


def _valid_ids(graph, observations, events) -> set[str]:
    ids = set(n.node_id for n in graph.nodes)
    ids |= set(o.observation_id for o in observations)
    ids |= set(e.event_id for e in events) if hasattr(events, "__iter__") else set()
    return ids


def _verify_evidence(
    evidence: list[Evidence],
    observations: list[Observation],
    valid_ids: set[str],
) -> tuple[list[Evidence], list[Downgrade]]:
    obs_map = {o.observation_id: o for o in observations}
    downgrades: list[Downgrade] = []
    out = []
    for ev in evidence:
        if ev.source_id not in valid_ids:
            # evidence cites an unknown source id; downgrade to speculation.
            downgrades.append(
                Downgrade(ev.evidence_id, "evidence", "speculation", "unknown source id")
            )
            continue
        # check subsystem/time match for observations
        if ev.source_id in obs_map:
            # if evidence claims subsystem mismatch -> downgrade
            # We can't parse claim text; assume match. Keep.
            pass
    return out, downgrades


def _chain_explains(h: Hypothesis, observations: list[Observation], graph: Graph) -> set[str]:
    # Observations whose subsystem is referenced by the causal chain. Chain node
    # ids may be canonical graph ids (``obs:obs_eps_battery_voltage_v_1``) or
    # bare observation ids (``obs_eps_battery_voltage_v_1``); both are accepted.
    obs_by_id = {o.observation_id: o for o in observations}
    chain_subsystems: set[str] = set()
    for node_id in h.causal_chain:
        obs_id = node_id[len("obs:"):] if node_id.startswith("obs:") else node_id
        obs = obs_by_id.get(obs_id)
        if obs is not None:
            chain_subsystems.add(obs.subsystem.lower())
    explained = {o.observation_id for o in observations if o.subsystem.lower() in chain_subsystems}
    return explained


def score_hypotheses(hypotheses, evidence, graph, observations, config=None, events=None):
    cfg = config or ScoringConfig()
    events = events or []
    valid_ids = _valid_ids(graph, observations, events)
    verified_evidence, downgrades = _verify_evidence(list(evidence), observations, valid_ids)

    # evidence reliability by id
    ev_by_id = {e.evidence_id: e for e in verified_evidence}

    scored = []
    for h in hypotheses:
        # explained observations
        explained = _chain_explains(h, observations, graph)
        total = max(1, len(observations))
        frac_explained = len(explained) / total

        # edge confidence along chain: map node->node edges
        edge_map = {(e.source, e.target): e for e in graph.edges}
        edge_confs = []
        spec_allowed_count = 0
        unsupported = 0
        for i in range(len(h.causal_chain) - 1):
            a, b = h.causal_chain[i], h.causal_chain[i + 1]
            e = edge_map.get((a, b))
            if e is None:
                unsupported += 1
                edge_confs.append(0.0)
            else:
                edge_confs.append(e.confidence)
                if e.metadata.get("spec_allowed"):
                    spec_allowed_count += 1
        avg_edge = sum(edge_confs) / max(1, len(edge_confs)) if edge_confs else 0.0

        # verified supporting evidence reliability
        sup_rels = []
        for eid in h.evidence_ids:
            ev = ev_by_id.get(eid)
            if ev is not None and ev.supports_or_contradicts.value == "supports":
                sup_rels.append(ev.reliability)
        avg_evidence = sum(sup_rels) / max(1, len(sup_rels)) if sup_rels else 0.0

        # contradictions
        contra_count = 0
        for eid in h.contradiction_ids:
            ev = ev_by_id.get(eid)
            if ev is not None:
                contra_count += 1

        # unexplained downstream observations
        unexplained_downstream = len(observations) - len(explained)

        # score. Penalties are normalized per chain element so a single
        # contradiction or missing edge cannot wipe out the whole score, and
        # weights sum to one so the raw score stays in [0, 1] before clamping.
        chain_len = max(1, len(h.causal_chain))
        links = max(1, len(h.causal_chain) - 1)
        score = (
            cfg.w_explained * frac_explained
            + cfg.w_edge_conf * avg_edge
            + cfg.w_evidence * avg_evidence
            - cfg.penalty_contradiction * (contra_count / chain_len)
            - cfg.penalty_unexplained_downstream * (unexplained_downstream / total)
            - cfg.penalty_unsupported_link * (unsupported / links)
        )
        score = max(0.0, min(1.0, score))

        # rejection reason
        rejected_reason = None
        if contra_count > 0:
            rejected_reason = f"contradicted by {contra_count} evidence"
        if unsupported > 0 and score < 0.3:
            rejected_reason = (rejected_reason or "") + f"; {unsupported} unsupported links"

        h.score = score
        h.confidence = min(1.0, max(0.0, (h.confidence + score) / 2))
        if rejected_reason:
            h.assumptions = list(h.assumptions) + [f"REJECTED: {rejected_reason}"]

        scored.append((h, explained))

    # rank
    hypotheses_sorted = sorted(hypotheses, key=lambda h: h.score, reverse=True)

    # summary
    tag_counts = {"evidence": 0, "inference": 0, "speculation": 0}
    # recompute unexplained globally: observations no chain explains
    all_explained = set()
    for _h, explained in scored:
        all_explained |= explained
    unexplained_ids = [
        o.observation_id
        for o in observations
        if o.observation_id not in all_explained
    ]

    summary = {
        "tag_counts": tag_counts,
        "unexplained_observation_ids": unexplained_ids,
        "num_hypotheses": len(hypotheses_sorted),
    }

    return ScoredResult(
        hypotheses=hypotheses_sorted,
        evidence=verified_evidence,
        downgrades=downgrades,
        summary=summary,
    )
