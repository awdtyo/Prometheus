"""Citation validation and stable hypothesis identifiers.

The LLM may only cite identifiers that already exist. This module is the single
gate between raw proposals and the validated :class:`Hypothesis` contract. It
also owns the deterministic id assignment, so the same accepted proposals always
produce the same ``HYPO-0001`` ordering regardless of the order the model used.
"""

from __future__ import annotations

from prometheus.agents.schemas import ProposedHypothesis
from prometheus.contracts import (
    DroppedHypothesis,
    GraphDocument,
    GraphEdge,
    Hypothesis,
    Observation,
)

__all__ = [
    "accept_proposals",
    "edge_index",
    "merge_valid",
    "observation_index",
    "proposal_key",
    "to_hypotheses",
    "validate_proposal",
]


def observation_index(observations: list[Observation]) -> dict[str, Observation]:
    """Index observations by their stable id."""
    return {observation.id: observation for observation in observations}


def edge_index(graph: GraphDocument | None) -> dict[str, GraphEdge]:
    """Index graph edges by their stable id; empty in no-graph mode."""
    if graph is None:
        return {}
    return {edge.id: edge for edge in graph.edges}


def validate_proposal(
    proposal: ProposedHypothesis,
    *,
    observations: dict[str, Observation],
    edges: dict[str, GraphEdge],
    use_graph: bool,
) -> list[str]:
    """Return every reason a proposal is not acceptable; empty means valid."""
    errors: list[str] = []
    if len(proposal.chain) < 3:
        errors.append("chain needs at least three observations")
    for observation_id in proposal.chain:
        if observation_id not in observations:
            errors.append(f"unknown observation id {observation_id}")
    if len(set(proposal.chain)) != len(proposal.chain):
        errors.append("duplicate observation id in chain")

    if not use_graph:
        if proposal.edges:
            errors.append("edge ids are not allowed in observations-only mode")
        return errors

    if len(set(proposal.edges)) != len(proposal.edges):
        errors.append("duplicate edge id")
    if not proposal.edges:
        errors.append("at least one edge id is required in graph mode")
    positions = {
        observation_id: index
        for index, observation_id in enumerate(proposal.chain)
    }
    for edge_id in proposal.edges:
        edge = edges.get(edge_id)
        if edge is None:
            errors.append(f"unknown edge id {edge_id}")
            continue
        if edge.source not in positions or edge.target not in positions:
            errors.append(
                f"edge {edge_id} does not connect two observations in the chain"
            )
            continue
        if positions[edge.target] <= positions[edge.source]:
            errors.append(f"edge {edge_id} points backward in the chain")
    return errors


def accept_proposals(
    proposals: list[ProposedHypothesis],
    *,
    observations: dict[str, Observation],
    edges: dict[str, GraphEdge],
    use_graph: bool,
) -> tuple[list[ProposedHypothesis], list[DroppedHypothesis], list[str]]:
    """Split proposals into accepted and dropped, with retry feedback.

    The feedback strings are fed back to the Proposer for its one allowed
    regeneration. They deliberately name the offending ids so the model can
    repair them instead of guessing again.
    """
    accepted: list[ProposedHypothesis] = []
    dropped: list[DroppedHypothesis] = []
    feedback: list[str] = []
    for proposal in proposals:
        errors = validate_proposal(
            proposal,
            observations=observations,
            edges=edges,
            use_graph=use_graph,
        )
        if errors:
            dropped.append(
                DroppedHypothesis(
                    root_cause=proposal.root_cause,
                    summary=proposal.summary,
                    reasons=errors,
                )
            )
            feedback.append(
                f"root_cause={proposal.root_cause.value} summary={proposal.summary}: "
                + "; ".join(errors)
            )
        else:
            accepted.append(proposal)
    return accepted, dropped, feedback


def proposal_key(
    proposal: ProposedHypothesis,
) -> tuple[str, str, str, tuple[str, ...], tuple[str, ...]]:
    """Deterministic ordering key used for ids and duplicate detection."""
    return (
        proposal.root_cause.value,
        proposal.root_subsystem.value,
        proposal.summary,
        tuple(proposal.chain),
        tuple(sorted(proposal.edges)),
    )


def merge_valid(
    first: list[ProposedHypothesis],
    second: list[ProposedHypothesis],
    *,
    limit: int = 6,
) -> tuple[list[ProposedHypothesis], list[DroppedHypothesis]]:
    """Merge two valid batches, drop duplicates and enforce the size limit."""
    seen: set[tuple[str, str, str, tuple[str, ...], tuple[str, ...]]] = set()
    unique: list[ProposedHypothesis] = []
    dropped: list[DroppedHypothesis] = []
    for proposal in [*first, *second]:
        key = proposal_key(proposal)
        if key in seen:
            dropped.append(
                DroppedHypothesis(
                    root_cause=proposal.root_cause,
                    summary=proposal.summary,
                    reasons=["duplicate hypothesis after regeneration"],
                )
            )
            continue
        seen.add(key)
        unique.append(proposal)

    unique.sort(key=proposal_key)
    if len(unique) > limit:
        for proposal in unique[limit:]:
            dropped.append(
                DroppedHypothesis(
                    root_cause=proposal.root_cause,
                    summary=proposal.summary,
                    reasons=[f"more than {limit} valid hypotheses"],
                )
            )
        unique = unique[:limit]
    return unique, dropped


def to_hypotheses(proposals: list[ProposedHypothesis]) -> list[Hypothesis]:
    """Assign stable ``HYPO-0001`` ids after a deterministic sort."""
    ordered = sorted(proposals, key=proposal_key)
    return [
        Hypothesis(id=f"HYPO-{number:04d}", **proposal.model_dump())
        for number, proposal in enumerate(ordered, start=1)
    ]
