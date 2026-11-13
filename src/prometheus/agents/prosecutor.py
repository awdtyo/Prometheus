"""The Prosecutor agent: deterministic support retrieval plus LLM narration."""

from __future__ import annotations

from prometheus.agents.evidence import supporting_evidence
from prometheus.agents.prompts import prosecutor_prompt
from prometheus.agents.schemas import ProsecutorNarratives
from prometheus.contracts import (
    GraphDocument,
    GraphEdge,
    Hypothesis,
    Observation,
    ProsecutorReport,
)
from prometheus.llm.client import LLMClient, LLMError

__all__ = ["prosecute"]


def prosecute(
    client: LLMClient,
    *,
    hypotheses: list[Hypothesis],
    observations: list[Observation],
    graph: GraphDocument | None,
) -> tuple[dict[str, ProsecutorReport], list[str]]:
    """Retrieve support by code, then ask the model to articulate it.

    The returned report always has code-owned observation and edge ids. The
    model's prose replaces only the human-readable summary; a narrative failure
    leaves the deterministic summary in place and records a warning.
    """
    reports = {
        hypothesis.id: supporting_evidence(
            hypothesis, observations=observations, graph=graph
        )
        for hypothesis in hypotheses
    }
    warnings: list[str] = []
    if not hypotheses:
        return reports, warnings

    observations_by_id = {observation.id: observation for observation in observations}
    edges_by_id: dict[str, GraphEdge] = (
        {edge.id: edge for edge in graph.edges} if graph is not None else {}
    )
    prompt = prosecutor_prompt(
        hypotheses=hypotheses,
        reports=reports,
        observations=observations_by_id,
        edges_by_id=edges_by_id,
    )
    try:
        narratives = client.complete_json(
            prompt,
            ProsecutorNarratives,
            agent="prosecutor",
            max_tokens=900,
        )
    except LLMError as exc:
        warnings.append(f"Prosecutor narrative unavailable; using deterministic summaries: {exc}")
        return reports, warnings

    seen: set[str] = set()
    for item in narratives.items:
        report = reports.get(item.hypothesis_id)
        if report is None:
            warnings.append(
                f"Prosecutor returned narrative for unknown hypothesis {item.hypothesis_id}"
            )
            continue
        report.summary = item.summary
        seen.add(item.hypothesis_id)
    missing = [hypothesis.id for hypothesis in hypotheses if hypothesis.id not in seen]
    if missing:
        warnings.append(
            "Prosecutor returned no narrative for: " + ", ".join(missing)
        )
    return reports, warnings
