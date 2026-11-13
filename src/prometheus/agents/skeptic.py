"""The Skeptic agent: deterministic contradictions plus LLM alternatives."""

from __future__ import annotations

from prometheus.agents.evidence import detect_contradictions
from prometheus.agents.prompts import skeptic_prompt
from prometheus.agents.schemas import SkepticNarratives
from prometheus.contracts import (
    Dependency,
    GraphDocument,
    Hypothesis,
    Observation,
    SkepticReport,
)
from prometheus.llm.client import LLMClient, LLMError

__all__ = ["critique"]


def critique(
    client: LLMClient,
    *,
    hypotheses: list[Hypothesis],
    observations: list[Observation],
    graph: GraphDocument | None,
    dependencies: list[Dependency],
) -> tuple[dict[str, SkepticReport], list[str]]:
    """Run the fixed contradiction checks, then ask for alternatives.

    The penalty is computed by :func:`detect_contradictions` and is never
    touched by the model. The LLM's alternatives are advisory prose for the
    report; a narrative failure leaves the deterministic report intact.
    """
    reports = {
        hypothesis.id: detect_contradictions(
            hypothesis,
            observations=observations,
            graph=graph,
            dependencies=dependencies,
        )
        for hypothesis in hypotheses
    }
    warnings: list[str] = []
    if not hypotheses:
        return reports, warnings

    observations_by_id = {observation.id: observation for observation in observations}
    prompt = skeptic_prompt(
        hypotheses=hypotheses,
        reports=reports,
        observations=observations_by_id,
    )
    try:
        narratives = client.complete_json(
            prompt,
            SkepticNarratives,
            agent="skeptic",
            max_tokens=900,
        )
    except LLMError as exc:
        warnings.append(f"Skeptic narrative unavailable; deterministic penalties kept: {exc}")
        return reports, warnings

    seen: set[str] = set()
    for item in narratives.items:
        report = reports.get(item.hypothesis_id)
        if report is None:
            warnings.append(
                f"Skeptic returned narrative for unknown hypothesis {item.hypothesis_id}"
            )
            continue
        report.alternatives = item.alternatives
        report.summary = item.summary
        seen.add(item.hypothesis_id)
    missing = [hypothesis.id for hypothesis in hypotheses if hypothesis.id not in seen]
    if missing:
        warnings.append("Skeptic returned no narrative for: " + ", ".join(missing))
    return reports, warnings
