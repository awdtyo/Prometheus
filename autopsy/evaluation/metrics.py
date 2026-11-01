"""Evaluation metrics computation.

Computes the twelve ``EvaluationMetrics`` fields documented in
``docs/api-contract.md`` for a completed run.

Ground truth (``fixtures/expected/*_ground_truth.json``) is read *only* here,
on the evaluation side of the boundary. It is never passed to hypothesis
agents. When ground truth is unavailable for a scenario, the metrics that
require it (root cause, fault localization, causal chain) are reported as
``0.0`` rather than fabricated.
"""

from __future__ import annotations

from datetime import datetime

from autopsy.analysis.scoring import ScoringConfig
from autopsy.schemas.evaluation import GroundTruth
from autopsy.schemas.events import MissionEvent
from autopsy.schemas.evidence import Evidence, EvidenceStance
from autopsy.schemas.graph import Graph
from autopsy.schemas.hypotheses import Hypothesis
from autopsy.schemas.observations import Observation

# The twelve EvaluationMetrics fields, in canonical order.
METRIC_KEYS: tuple[str, ...] = (
    "root_cause_accuracy",
    "fault_localization_accuracy",
    "causal_chain_accuracy",
    "evidence_coverage",
    "temporal_ordering_accuracy",
    "contradiction_handling",
    "unsupported_claim_rate",
    "runtime_seconds",
    "evidence_weight",
    "consistency_weight",
    "coverage_weight",
    "contradiction_penalty",
)


def _resolve_node(
    node_id: str,
    obs_by_id: dict[str, Observation],
    ev_by_id: dict[str, MissionEvent],
) -> tuple[str, datetime] | None:
    """Resolve a causal-chain node id to ``(subsystem, timestamp)``.

    Hypothesis chains may cite either the canonical graph node id
    (``obs:obs_eps_battery_voltage_v_1`` / ``evt:evt_003``) or the bare
    observation/event id (``obs_eps_battery_voltage_v_1`` / ``evt_003``).
    Both forms are accepted so chains are not penalised for id formatting.
    """
    if node_id.startswith("obs:"):
        obs = obs_by_id.get(node_id[len("obs:") :])
        return (obs.subsystem, obs.timestamp) if obs is not None else None
    if node_id.startswith("evt:"):
        ev = ev_by_id.get(node_id[len("evt:") :])
        return (ev.subsystem, ev.timestamp) if ev is not None else None
    obs = obs_by_id.get(node_id)
    if obs is not None:
        return (obs.subsystem, obs.timestamp)
    ev = ev_by_id.get(node_id)
    if ev is not None:
        return (ev.subsystem, ev.timestamp)
    return None


def _chain_subsystems(
    chain: list[str],
    obs_by_id: dict[str, Observation],
    ev_by_id: dict[str, MissionEvent],
) -> set[str]:
    """Subsystems referenced by a causal chain (case-insensitive)."""
    subsystems: set[str] = set()
    for node_id in chain:
        resolved = _resolve_node(node_id, obs_by_id, ev_by_id)
        if resolved is not None:
            subsystems.add(resolved[0].lower())
    return subsystems


def _chain_timestamps(
    chain: list[str],
    obs_by_id: dict[str, Observation],
    ev_by_id: dict[str, MissionEvent],
) -> list[datetime]:
    """Non-decreasing check input: timestamps cited by a causal chain."""
    timestamps: list[datetime] = []
    for node_id in chain:
        resolved = _resolve_node(node_id, obs_by_id, ev_by_id)
        if resolved is not None:
            timestamps.append(resolved[1])
    return timestamps


def _normalize_chain(
    chain: list[str],
    obs_by_id: dict[str, Observation],
    ev_by_id: dict[str, MissionEvent],
) -> list[str]:
    """Normalize chain ids to canonical graph node ids (``obs:...`` / ``evt:...``)."""
    normalized: list[str] = []
    for node_id in chain:
        if node_id.startswith("obs:") or node_id.startswith("evt:"):
            normalized.append(node_id)
        elif node_id in obs_by_id:
            normalized.append(f"obs:{node_id}")
        elif node_id in ev_by_id:
            normalized.append(f"evt:{node_id}")
        else:
            normalized.append(node_id)
    return normalized


def _chain_references_subsystem(
    chain: list[str],
    target: str,
    obs_by_id: dict[str, Observation],
    ev_by_id: dict[str, MissionEvent],
) -> bool:
    target = target.lower()
    return target in _chain_subsystems(chain, obs_by_id, ev_by_id)


def compute_evaluation_metrics(
    hypotheses: list[Hypothesis],
    evidence: list[Evidence],
    graph: Graph,
    observations: list[Observation],
    events: list[MissionEvent],
    ground_truth: GroundTruth | None,
    runtime_seconds: float,
    config: ScoringConfig | None = None,
) -> dict[str, float]:
    """Compute all twelve :data:`METRIC_KEYS` for one completed run."""
    cfg = config or ScoringConfig()
    obs_by_id = {o.observation_id: o for o in observations}
    ev_by_id = {e.event_id: e for e in events}
    edge_set = {(e.source, e.target) for e in graph.edges}

    leading = hypotheses[0] if hypotheses else None
    target_subsystem = (
        ground_truth.injected_fault.target_subsystem if ground_truth is not None else None
    )

    # ---- 1. root_cause_accuracy ---------------------------------------
    root_cause = 0.0
    if leading is not None and target_subsystem is not None and _chain_references_subsystem(
        leading.causal_chain, target_subsystem, obs_by_id, ev_by_id
    ):
        root_cause = 1.0

    # ---- 2. fault_localization_accuracy -------------------------------
    fault_localization = 0.0
    if target_subsystem is not None and any(
        _chain_references_subsystem(h.causal_chain, target_subsystem, obs_by_id, ev_by_id)
        for h in hypotheses
    ):
            fault_localization = 1.0

    # ---- 3. causal_chain_accuracy -------------------------------------
    chain_accuracy = 0.0
    if ground_truth is not None and leading is not None:
        steps = ground_truth.expected_causal_sequence or []
        if steps:
            recovered = 0
            for step in steps:
                if _chain_references_subsystem(
                    leading.causal_chain, step.subsystem, obs_by_id, ev_by_id
                ):
                    recovered += 1
            chain_accuracy = recovered / len(steps)

    # ---- 4. evidence_coverage -----------------------------------------
    coverage = 0.0
    if observations:
        chain_subsystems = _chain_subsystems(
            leading.causal_chain if leading else [], obs_by_id, ev_by_id
        )
        explained = {
            o.observation_id
            for o in observations
            if o.subsystem.lower() in chain_subsystems
        }
        coverage = len(explained) / len(observations)

    # ---- 5. temporal_ordering_accuracy --------------------------------
    temporal = 1.0
    if leading is not None:
        timestamps = _chain_timestamps(
            leading.causal_chain, obs_by_id, ev_by_id
        )
        if len(timestamps) >= 2 and any(
            later < earlier for earlier, later in zip(timestamps, timestamps[1:])  # noqa: B905
        ):
            temporal = 0.0

    # ---- 6. contradiction_handling ------------------------------------
    supporting = [
        e for e in evidence if e.supports_or_contradicts == EvidenceStance.SUPPORTS
    ]
    contradicted_ids = {
        eid
        for h in hypotheses
        for eid in h.contradiction_ids
        if any(e.evidence_id == eid and e in supporting for e in evidence)
    }
    contradiction_handling = 1.0 - (len(contradicted_ids) / max(1, len(supporting)))

    # ---- 7. unsupported_claim_rate ------------------------------------
    unsupported_rate = 0.0
    if leading is not None and len(leading.causal_chain) >= 2:
        norm_chain = _normalize_chain(
            leading.causal_chain, obs_by_id, ev_by_id
        )
        links = len(norm_chain) - 1
        unsupported = sum(
            1
            for i in range(links)
            if (norm_chain[i], norm_chain[i + 1]) not in edge_set
        )
        unsupported_rate = unsupported / links

    return {
        "root_cause_accuracy": round(root_cause, 4),
        "fault_localization_accuracy": round(fault_localization, 4),
        "causal_chain_accuracy": round(chain_accuracy, 4),
        "evidence_coverage": round(coverage, 4),
        "temporal_ordering_accuracy": round(temporal, 4),
        "contradiction_handling": round(contradiction_handling, 4),
        "unsupported_claim_rate": round(unsupported_rate, 4),
        "runtime_seconds": round(runtime_seconds, 4),
        "evidence_weight": cfg.w_evidence,
        "consistency_weight": cfg.w_edge_conf,
        "coverage_weight": cfg.w_explained,
        "contradiction_penalty": cfg.penalty_contradiction,
    }
