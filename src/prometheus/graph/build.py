"""Build the temporal causal graph from observations and the spec.

Candidate edges come from two sources:

* **Spec**: the mission's declared subsystem dependency map. A pair is
  spec-supported when the observed onset lag falls inside the declared lag
  window, widened by ``spec_onset_slack_s`` to absorb detection timing noise.
* **Data**: every other ordered telemetry pair whose onset lag is at most
  ``max_data_lag_s``. These are kept only if the statistical evidence survives
  pruning, and they are flagged ``spec_support=False``.

Edge score (documented once, used everywhere)::

    base  = 0.65 * statistical_support
          + 0.20 * lag_agreement
          + 0.15 * (1 if spec_support else 0)
    score = base * confidence_factor

``statistical_support`` is ``|peak correlation| * (1 - permutation p)``,
``lag_agreement`` is ``1 / (1 + |cross-correlation shift| / 600 s)`` and
``confidence_factor`` is the lower Phase 3 confidence of the two endpoint
observations. Every term lies in ``[0, 1]`` and the score is monotonically
increasing in each. The endpoint factor prevents a pair of low-confidence
transients from outranking a well-established step. The weights were chosen so
a spec-only edge (no data support) cannot outrank a strong data-supported edge.

Pruning keeps an edge when ``score >= min_edge_score`` (default 0.20) and either
the permutation p-value is at most ``max_p_value`` (default 0.10) or the edge is
spec-supported with a score of at least ``min_spec_score`` (default 0.30). The
thresholds are conservative on purpose: the graph is a set of candidates for the
hypothesis agents, not a claim that every kept edge is true.

Temporal ordering is enforced before scoring: the target observation must start
strictly after the source. Event observations remain as isolated nodes because
they have no telemetry channel from which to estimate residuals; they can still
be cited by later stages.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from prometheus.contracts import (
    Dependency,
    GraphDocument,
    GraphEdge,
    Observation,
    ObservationSet,
    Subsystem,
)
from prometheus.graph.evidence import (
    EdgeEvidence,
    ResidualSeries,
    channel_residual,
    measure_edge,
)
from prometheus.ingest import IngestedRun

__all__ = [
    "GraphConfig",
    "build_graph",
]


@dataclass(frozen=True)
class GraphConfig:
    """Thresholds for candidate generation, evidence and pruning."""

    baseline_s: float = 1800.0
    grid_s: float = 60.0
    context_pre_s: float = 600.0
    context_post_s: float = 1800.0
    max_shift_s: float = 600.0
    permutations: int = 100
    rng_seed: int = 20261108
    max_data_lag_s: float = 3600.0
    spec_onset_slack_s: float = 1800.0
    lag_tolerance_s: float = 600.0
    min_edge_score: float = 0.20
    max_p_value: float = 0.10
    min_spec_score: float = 0.30


@dataclass(frozen=True)
class _Candidate:
    source: Observation
    target: Observation
    spec_support: bool
    mechanism: str


def _epoch(observation: Observation) -> float:
    return observation.t_start.timestamp()


def _dependency_lookup(
    ingested: IngestedRun,
) -> dict[tuple[Subsystem, Subsystem], Dependency]:
    return {
        (dependency.source, dependency.target): dependency
        for dependency in ingested.spec.dependencies
    }


def _candidates(
    observations: list[Observation],
    dependencies: dict[tuple[Subsystem, Subsystem], Dependency],
    config: GraphConfig,
) -> list[_Candidate]:
    """Enumerate ordered telemetry pairs, marking spec support."""
    telemetry = [
        observation
        for observation in observations
        if observation.channel is not None
    ]
    ordered = sorted(
        telemetry,
        key=lambda observation: (
            observation.t_start,
            observation.channel,
            observation.id,
        ),
    )
    candidates: list[_Candidate] = []
    for source in ordered:
        for target in ordered:
            if source.id == target.id:
                continue
            if target.t_start <= source.t_start:
                continue
            if source.channel == target.channel:
                continue
            lag = _epoch(target) - _epoch(source)
            dependency = dependencies.get((source.subsystem, target.subsystem))
            limit = config.max_data_lag_s
            if dependency is not None:
                limit = max(
                    limit,
                    dependency.lag_max_s + config.spec_onset_slack_s,
                )
            if lag > limit:
                continue

            spec_support = False
            mechanism = ""
            if dependency is not None:
                minimum = max(0.0, dependency.lag_min_s - config.spec_onset_slack_s)
                maximum = dependency.lag_max_s + config.spec_onset_slack_s
                spec_support = minimum <= lag <= maximum
                if spec_support:
                    mechanism = dependency.mechanism
            candidates.append(
                _Candidate(
                    source=source,
                    target=target,
                    spec_support=spec_support,
                    mechanism=mechanism,
                )
            )
    return candidates


def _edge_document(
    candidate: _Candidate,
    evidence: EdgeEvidence,
) -> dict[str, object]:
    """Turn one measured candidate into the fields of a ``GraphEdge``."""
    spec_bonus = 1.0 if candidate.spec_support else 0.0
    confidence_factor = float(
        min(candidate.source.confidence, candidate.target.confidence)
    )
    base = float(
        np.clip(
            0.65 * evidence.statistical_support
            + 0.20 * evidence.lag_agreement
            + 0.15 * spec_bonus,
            0.0,
            1.0,
        )
    )
    score = float(np.clip(base * confidence_factor, 0.0, 1.0))
    return {
        "source": candidate.source.id,
        "target": candidate.target.id,
        "spec_support": candidate.spec_support,
        "mechanism": candidate.mechanism,
        "onset_lag_s": evidence.onset_lag_s,
        "xcorr_lag_s": evidence.xcorr_lag_s,
        "lag_estimate_s": evidence.lag_estimate_s,
        "lag_min_s": evidence.lag_min_s,
        "lag_max_s": evidence.lag_max_s,
        "correlation": evidence.correlation,
        "p_value": evidence.p_value,
        "statistical_support": evidence.statistical_support,
        "lag_agreement": evidence.lag_agreement,
        "confidence_factor": confidence_factor,
        "edge_score": score,
        "provenance": "spec" if candidate.spec_support else "data",
    }


def _keep(row: dict[str, object], config: GraphConfig) -> bool:
    score = float(row["edge_score"])
    p_value = float(row["p_value"])
    spec_support = bool(row["spec_support"])
    if score < config.min_edge_score:
        return False
    if p_value <= config.max_p_value:
        return True
    return spec_support and score >= config.min_spec_score


def build_graph(
    ingested: IngestedRun,
    observations: ObservationSet,
    config: GraphConfig | None = None,
) -> GraphDocument:
    """Build and prune the temporal causal graph for one mission.

    Args:
        ingested: Normalized run, used for the spec and channel residuals.
        observations: Observations from Phase 3.
        config: Optional thresholds; see :class:`GraphConfig`.

    Returns:
        A validated :class:`GraphDocument` with stable ``EDGE-0001`` ids.
    """
    config = config or GraphConfig()
    residuals: dict[str, ResidualSeries] = {}
    for observation in observations.observations:
        channel = observation.channel
        if channel is None or channel in residuals:
            continue
        residuals[channel] = channel_residual(
            ingested.series[channel],
            baseline_s=config.baseline_s,
            grid_s=config.grid_s,
        )

    dependencies = _dependency_lookup(ingested)
    rng = np.random.default_rng(config.rng_seed)
    rows: list[dict[str, object]] = []
    for candidate in _candidates(
        observations.observations, dependencies, config
    ):
        source_residual = residuals.get(candidate.source.channel or "")
        target_residual = residuals.get(candidate.target.channel or "")
        if source_residual is None or target_residual is None:
            continue
        evidence = measure_edge(
            source_residual,
            target_residual,
            source_onset_epoch_s=_epoch(candidate.source),
            target_onset_epoch_s=_epoch(candidate.target),
            rng=rng,
            pre_s=config.context_pre_s,
            post_s=config.context_post_s,
            max_shift_s=config.max_shift_s,
            permutations=config.permutations,
            lag_tolerance_s=config.lag_tolerance_s,
        )
        row = _edge_document(candidate, evidence)
        if _keep(row, config):
            rows.append(row)

    rows.sort(key=lambda row: (str(row["source"]), str(row["target"])))
    edges = [
        GraphEdge(id=f"EDGE-{number:04d}", **row)
        for number, row in enumerate(rows, start=1)
    ]
    return GraphDocument(
        scenario=observations.scenario,
        seed=observations.seed,
        mission=observations.mission,
        nodes=list(observations.observations),
        edges=edges,
    )
