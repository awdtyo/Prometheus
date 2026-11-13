"""The Proposer agent: propose competing root-cause hypotheses."""

from __future__ import annotations

from datetime import datetime

from prometheus.agents.prompts import proposer_prompt
from prometheus.agents.schemas import ProposalBatch
from prometheus.contracts import Dependency, GraphDocument, ObservationSet
from prometheus.llm.client import LLMClient

__all__ = ["propose_hypotheses"]


def propose_hypotheses(
    client: LLMClient,
    *,
    duration_s: float,
    observations: ObservationSet,
    graph: GraphDocument | None,
    dependencies: list[Dependency],
    origin: datetime,
    feedback: list[str] | None = None,
) -> ProposalBatch:
    """Ask the Proposer for three to six hypotheses.

    The response is pydantic-validated by the client. Citation existence is a
    separate step; this function only guarantees the JSON shape and taxonomy.
    """
    prompt = proposer_prompt(
        duration_s=duration_s,
        observations=observations,
        graph=graph,
        dependencies=dependencies,
        origin=origin,
        feedback=feedback,
    )
    return client.complete_json(
        prompt,
        ProposalBatch,
        agent="proposer",
        max_tokens=2400,
    )
