"""Deterministic evidence retrieval, contradiction checks and Judge scoring.

Nothing in this module calls an LLM. The Prosecutor's evidence set, the
Skeptic's contradictions and penalty, and every Judge component are computed
from the observation set, the graph and the spec. The LLM agents only narrate
these results.

Judge score (documented once, used everywhere)::

    base  = 0.30 * temporal_consistency
          + 0.20 * spec_consistency
          + 0.25 * statistical_support
          + 0.25 * observation_coverage
    total = clip(base - 0.30 * contradiction_penalty, 0.0, 1.0)

``temporal_consistency`` combines observation order (always available) with
forward graph edges (graph mode only). In observations-only mode the two
graph-dependent components (``spec_consistency`` and ``statistical_support``)
are set to the neutral value 0.5, so the ablation still uses the same formula.
"""

from __future__ import annotations

from prometheus.agents.citations import observation_index
from prometheus.contracts import (
    Contradiction,
    ContradictionCode,
    Dependency,
    GraphDocument,
    GraphEdge,
    Hypothesis,
    HypothesisScore,
    Observation,
    ObservationSource,
    ProsecutorReport,
    Severity,
    SkepticReport,
)

__all__ = [
    "detect_contradictions",
    "high_severity_observations",
    "score_hypothesis",
    "supporting_evidence",
]

#: An outgoing edge at or above this score counts as an expected downstream
#: effect when its target is absent from the hypothesis chain.
DOWNSTREAM_SCORE_THRESHOLD = 0.50

#: Keep the Prosecutor's structural evidence compact for prompts and reports.
MAX_SUPPORT_EDGES = 10


def high_severity_observations(observations: list[Observation]) -> list[Observation]:
    """Telemetry observations an autopsy must explain (warning or critical)."""
    return [
        observation
        for observation in observations
        if observation.source is ObservationSource.TELEMETRY
        and observation.severity is not Severity.INFO
    ]


def _adjacent_pairs(chain: list[str]) -> list[tuple[str, str]]:
    return list(zip(chain, chain[1:], strict=False))


def _has_edge(
    graph: GraphDocument,
    source: str,
    target: str,
) -> bool:
    return any(
        edge.source == source and edge.target == target for edge in graph.edges
    )


def supporting_evidence(
    hypothesis: Hypothesis,
    *,
    observations: list[Observation],
    graph: GraphDocument | None,
) -> ProsecutorReport:
    """Retrieve the evidence that supports one hypothesis.

    The cited edges are always included. In graph mode any other forward edge
    between two observations in the chain is added as further support, which
    lets the Prosecutor articulate connections the Proposer did not cite.
    """
    by_id = observation_index(observations)
    chain_order = {observation_id: index for index, observation_id in enumerate(hypothesis.chain)}
    chain_set = set(hypothesis.chain)
    observation_ids = sorted(
        chain_set,
        key=lambda observation_id: (
            by_id[observation_id].t_start,
            observation_id,
        ),
    )
    if graph is None:
        return ProsecutorReport(
            observation_ids=observation_ids,
            edge_ids=[],
            mean_edge_score=0.0,
            summary=(
                f"{len(observation_ids)} observations; no graph available in this "
                "ablation."
            ),
        )

    cited_ids = set(hypothesis.edges)
    edges: list[GraphEdge] = [
        edge for edge in graph.edges if edge.id in cited_ids
    ]
    known = {edge.id for edge in edges}
    for edge in graph.edges:
        if edge.id in known:
            continue
        if edge.source not in chain_set or edge.target not in chain_set:
            continue
        if chain_order[edge.source] >= chain_order[edge.target]:
            continue
        edges.append(edge)

    edges.sort(key=lambda edge: (-edge.edge_score, edge.id))
    edges = edges[:MAX_SUPPORT_EDGES]
    mean_score = (
        sum(edge.edge_score for edge in edges) / len(edges) if edges else 0.0
    )
    spec_count = sum(edge.spec_support for edge in edges)
    summary = (
        f"{len(observation_ids)} observations; {len(edges)} supporting edges "
        f"({spec_count} spec-supported); mean edge score {mean_score:.2f}."
    )
    return ProsecutorReport(
        observation_ids=observation_ids,
        edge_ids=[edge.id for edge in edges],
        mean_edge_score=mean_score,
        summary=summary,
    )


def detect_contradictions(
    hypothesis: Hypothesis,
    *,
    observations: list[Observation],
    graph: GraphDocument | None,
    dependencies: list[Dependency],
) -> SkepticReport:
    """Run the deterministic Skeptic checks and compute the penalty.

    The penalty weights are: 0.35 ordering, 0.25 unexplained downstream,
    0.25 unexplained high severity, 0.15 missing spec effects, plus 0.10 for a
    root-subsystem mismatch. The value is clipped to ``[0, 1]``.
    """
    by_id = observation_index(observations)
    chain_set = set(hypothesis.chain)
    contradictions: list[Contradiction] = []

    for source_id, target_id in _adjacent_pairs(hypothesis.chain):
        source = by_id[source_id]
        target = by_id[target_id]
        if target.t_start <= source.t_start:
            contradictions.append(
                Contradiction(
                    code=ContradictionCode.ORDERING,
                    detail=f"{target_id} starts at or before {source_id}",
                    observation_ids=[source_id, target_id],
                )
            )

    if graph is not None:
        for source_id, target_id in _adjacent_pairs(hypothesis.chain):
            if _has_edge(graph, source_id, target_id):
                continue
            if _has_edge(graph, target_id, source_id):
                contradictions.append(
                    Contradiction(
                        code=ContradictionCode.REVERSE_EDGE,
                        detail=(
                            f"graph supports {target_id}->{source_id}, the reverse "
                            f"of the chain step {source_id}->{target_id}"
                        ),
                        observation_ids=[source_id, target_id],
                    )
                )

        terminal = hypothesis.chain[-1]
        downstream = {
            edge.target: edge
            for edge in graph.edges
            if edge.source == terminal
            and edge.target not in chain_set
            and edge.edge_score >= DOWNSTREAM_SCORE_THRESHOLD
        }
        if downstream:
            targets = sorted(
                downstream,
                key=lambda observation_id: (
                    by_id[observation_id].t_start,
                    observation_id,
                ),
            )
            contradictions.append(
                Contradiction(
                    code=ContradictionCode.UNEXPLAINED_DOWNSTREAM,
                    detail=(
                        f"{len(targets)} strong outgoing edge(s) from terminal "
                        f"observation {terminal} point outside the chain"
                    ),
                    observation_ids=targets[:5],
                )
            )

    high_severity = high_severity_observations(observations)
    unexplained = [
        observation.id
        for observation in high_severity
        if observation.id not in chain_set
    ]
    if unexplained:
        contradictions.append(
            Contradiction(
                code=ContradictionCode.UNEXPLAINED_HIGH_SEVERITY,
                detail=(
                    f"{len(unexplained)} high-severity observation(s) are not "
                    "explained by the chain"
                ),
                observation_ids=unexplained,
            )
        )

    chain_subsystems = {by_id[observation_id].subsystem for observation_id in chain_set}
    missing_spec = [
        dependency
        for dependency in dependencies
        if dependency.source == hypothesis.root_subsystem
        and dependency.target not in chain_subsystems
    ]
    for dependency in missing_spec:
        contradictions.append(
            Contradiction(
                code=ContradictionCode.MISSING_SPEC_EFFECT,
                detail=(
                    f"spec expects {dependency.source.value}->"
                    f"{dependency.target.value}: {dependency.mechanism}"
                ),
                observation_ids=[],
            )
        )

    if by_id[hypothesis.chain[0]].subsystem != hypothesis.root_subsystem:
        contradictions.append(
            Contradiction(
                code=ContradictionCode.ROOT_MISMATCH,
                detail=(
                    f"chain starts in {by_id[hypothesis.chain[0]].subsystem.value}, "
                    f"but the root cause is {hypothesis.root_subsystem.value}"
                ),
                observation_ids=[hypothesis.chain[0]],
            )
        )

    ordering_count = sum(
        contradiction.code is ContradictionCode.ORDERING
        for contradiction in contradictions
    )
    downstream_count = sum(
        len(contradiction.observation_ids)
        for contradiction in contradictions
        if contradiction.code is ContradictionCode.UNEXPLAINED_DOWNSTREAM
    )
    severity_fraction = len(unexplained) / max(1, len(high_severity))
    spec_fraction = len(missing_spec) / max(1, len(dependencies))
    penalty = min(
        1.0,
        0.35 * ordering_count / max(1, len(hypothesis.chain) - 1)
        + 0.25 * min(downstream_count / 3.0, 1.0)
        + 0.25 * severity_fraction
        + 0.15 * min(spec_fraction, 1.0),
    )
    if any(
        contradiction.code is ContradictionCode.ROOT_MISMATCH
        for contradiction in contradictions
    ):
        penalty = min(1.0, penalty + 0.10)

    summary = (
        f"{len(contradictions)} deterministic contradiction(s); "
        f"penalty {penalty:.2f}."
    )
    return SkepticReport(
        contradictions=contradictions,
        alternatives=[],
        penalty=penalty,
        summary=summary,
    )


def _temporal_consistency(
    hypothesis: Hypothesis,
    *,
    observations: dict[str, Observation],
    graph: GraphDocument | None,
) -> float:
    pairs = _adjacent_pairs(hypothesis.chain)
    if not pairs:
        return 1.0
    order_ok = sum(
        observations[target].t_start > observations[source].t_start
        for source, target in pairs
    ) / len(pairs)
    if graph is None:
        return order_ok
    edge_ok = sum(
        _has_edge(graph, source, target) for source, target in pairs
    ) / len(pairs)
    return 0.6 * order_ok + 0.4 * edge_ok


def _spec_consistency(
    hypothesis: Hypothesis,
    *,
    edges: dict[str, GraphEdge],
    graph: GraphDocument | None,
) -> float:
    if graph is None or not hypothesis.edges:
        return 0.5
    cited = [edges[edge_id] for edge_id in hypothesis.edges if edge_id in edges]
    if not cited:
        return 0.0
    return sum(edge.spec_support for edge in cited) / len(cited)


def _statistical_support(
    hypothesis: Hypothesis,
    *,
    edges: dict[str, GraphEdge],
    graph: GraphDocument | None,
) -> float:
    if graph is None or not hypothesis.edges:
        return 0.5
    cited = [edges[edge_id] for edge_id in hypothesis.edges if edge_id in edges]
    if not cited:
        return 0.0
    return sum(edge.edge_score for edge in cited) / len(cited)


def _observation_coverage(
    hypothesis: Hypothesis,
    *,
    observations: list[Observation],
) -> float:
    high_severity = high_severity_observations(observations)
    if not high_severity:
        return 1.0
    chain = set(hypothesis.chain)
    covered = sum(observation.id in chain for observation in high_severity)
    return covered / len(high_severity)


def score_hypothesis(
    hypothesis: Hypothesis,
    *,
    observations: list[Observation],
    graph: GraphDocument | None,
    edges: dict[str, GraphEdge],
    skeptic: SkepticReport,
) -> HypothesisScore:
    """Compute every Judge component in code.

    The LLM never sees this function's inputs as writable fields and never
    returns a score; its only output is prose attached after ranking.
    """
    by_id = observation_index(observations)
    temporal = _temporal_consistency(
        hypothesis, observations=by_id, graph=graph
    )
    spec = _spec_consistency(hypothesis, edges=edges, graph=graph)
    statistical = _statistical_support(hypothesis, edges=edges, graph=graph)
    coverage = _observation_coverage(hypothesis, observations=observations)
    base = 0.30 * temporal + 0.20 * spec + 0.25 * statistical + 0.25 * coverage
    total = max(0.0, min(1.0, base - 0.30 * skeptic.penalty))
    return HypothesisScore(
        temporal_consistency=temporal,
        spec_consistency=spec,
        statistical_support=statistical,
        observation_coverage=coverage,
        contradiction_penalty=skeptic.penalty,
        total=total,
    )
