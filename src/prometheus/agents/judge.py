"""The Judge agent: code-computed scores and ranks, LLM-written rationale only."""

from __future__ import annotations

from prometheus.agents.evidence import score_hypothesis
from prometheus.agents.prompts import judge_prompt
from prometheus.agents.schemas import JudgeNarratives
from prometheus.contracts import (
    GraphDocument,
    GraphEdge,
    Hypothesis,
    HypothesisScore,
    Observation,
    ProsecutorReport,
    RankedHypothesis,
    SkepticReport,
)
from prometheus.llm.client import LLMClient, LLMError

__all__ = ["judge_hypotheses", "rank_hypotheses"]


def rank_hypotheses(
    hypotheses: list[Hypothesis],
    *,
    scores: dict[str, HypothesisScore],
    prosecutor_reports: dict[str, ProsecutorReport],
    skeptic_reports: dict[str, SkepticReport],
    rationales: dict[str, str] | None = None,
) -> list[RankedHypothesis]:
    """Sort by score, assign contiguous ranks and compute inter-rank margins.

    Ties break on hypothesis id, so the ordering is stable and reproducible.
    """
    rationales = rationales or {}
    ordered = sorted(
        hypotheses,
        key=lambda hypothesis: (-scores[hypothesis.id].total, hypothesis.id),
    )
    ranked: list[RankedHypothesis] = []
    for index, hypothesis in enumerate(ordered):
        next_score = (
            scores[ordered[index + 1].id].total if index + 1 < len(ordered) else None
        )
        margin = (
            0.0
            if next_score is None
            else max(0.0, scores[hypothesis.id].total - next_score)
        )
        ranked.append(
            RankedHypothesis(
                hypothesis=hypothesis,
                score=scores[hypothesis.id],
                prosecutor=prosecutor_reports[hypothesis.id],
                skeptic=skeptic_reports[hypothesis.id],
                judge_rationale=rationales.get(
                    hypothesis.id, hypothesis.rationale
                ),
                rank=index + 1,
                margin_to_next=margin,
            )
        )
    return ranked


def judge_hypotheses(
    client: LLMClient,
    *,
    hypotheses: list[Hypothesis],
    observations: list[Observation],
    graph: GraphDocument | None,
    prosecutor_reports: dict[str, ProsecutorReport],
    skeptic_reports: dict[str, SkepticReport],
) -> tuple[list[RankedHypothesis], list[str]]:
    """Score every hypothesis in code, then ask the model for rationales.

    Scores are computed before the LLM call and are never read back from it.
    The model's only output field is prose, and ranking is recomputed by the
    same pure function afterwards.
    """
    warnings: list[str] = []
    if not hypotheses:
        return [], warnings

    edges_by_id: dict[str, GraphEdge] = (
        {edge.id: edge for edge in graph.edges} if graph is not None else {}
    )
    scores = {
        hypothesis.id: score_hypothesis(
            hypothesis,
            observations=observations,
            graph=graph,
            edges=edges_by_id,
            skeptic=skeptic_reports[hypothesis.id],
        )
        for hypothesis in hypotheses
    }
    fallback = {hypothesis.id: hypothesis.rationale for hypothesis in hypotheses}
    provisional = rank_hypotheses(
        hypotheses,
        scores=scores,
        prosecutor_reports=prosecutor_reports,
        skeptic_reports=skeptic_reports,
        rationales=fallback,
    )

    observations_by_id = {observation.id: observation for observation in observations}
    prompt = judge_prompt(ranked=provisional, observations=observations_by_id)
    try:
        narratives = client.complete_json(
            prompt,
            JudgeNarratives,
            agent="judge",
            max_tokens=900,
        )
    except LLMError as exc:
        warnings.append(f"Judge narrative unavailable; using proposer rationales: {exc}")
        return provisional, warnings

    rationales = dict(fallback)
    seen: set[str] = set()
    for item in narratives.items:
        if item.hypothesis_id not in scores:
            warnings.append(
                f"Judge returned rationale for unknown hypothesis {item.hypothesis_id}"
            )
            continue
        rationales[item.hypothesis_id] = item.rationale
        seen.add(item.hypothesis_id)
    missing = [hypothesis.id for hypothesis in hypotheses if hypothesis.id not in seen]
    if missing:
        warnings.append(
            "Judge returned no rationale for: " + ", ".join(missing)
        )

    ranked = rank_hypotheses(
        hypotheses,
        scores=scores,
        prosecutor_reports=prosecutor_reports,
        skeptic_reports=skeptic_reports,
        rationales=rationales,
    )
    return ranked, warnings
