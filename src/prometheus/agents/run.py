"""Orchestrate the Phase 5 hypothesis agents for one mission.

Flow: Proposer -> citation validator (one regeneration) -> Prosecutor ->
Skeptic -> Judge. The stage reads the mission directory and writes
``hypotheses.json``. Ground truth is never opened.

The orchestration also snapshots the client counters around each agent so the
artifact and the CLI can report calls and tokens per agent without asking the
LLM for anything.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from prometheus.agents.citations import (
    accept_proposals,
    edge_index,
    merge_valid,
    observation_index,
    to_hypotheses,
)
from prometheus.agents.judge import judge_hypotheses
from prometheus.agents.proposer import propose_hypotheses
from prometheus.agents.prosecutor import prosecute
from prometheus.agents.schemas import ProposedHypothesis
from prometheus.agents.skeptic import critique
from prometheus.contracts import (
    AgentUsage,
    Dependency,
    DroppedHypothesis,
    GraphDocument,
    GraphEdge,
    InvestigationDocument,
    LLMUsage,
    Observation,
    ObservationSet,
    RankedHypothesis,
)
from prometheus.graph import build_graph
from prometheus.ingest import IngestedRun, ingest_run
from prometheus.llm.client import LLMClient
from prometheus.observations import extract_observations

__all__ = [
    "InvestigationResult",
    "investigate_run",
    "write_investigation",
]

_DEFAULT_FILENAME = "hypotheses.json"


@dataclass(frozen=True)
class InvestigationResult:
    """An investigation and the artifact it wrote."""

    ingested: IngestedRun
    observations: ObservationSet
    graph: GraphDocument | None
    document: InvestigationDocument
    output_path: Path

    @property
    def top(self) -> RankedHypothesis | None:
        """The highest-ranked hypothesis, if any survived validation."""
        return self.document.hypotheses[0] if self.document.hypotheses else None


def _usage(client: LLMClient) -> LLMUsage:
    stats = client.stats
    return LLMUsage(
        calls=int(getattr(stats, "calls", 0)),
        cache_hits=int(getattr(stats, "cache_hits", 0)),
        retries=int(getattr(stats, "retries", 0)),
        prompt_tokens=int(getattr(stats, "prompt_tokens", 0)),
        completion_tokens=int(getattr(stats, "completion_tokens", 0)),
        total_tokens=int(getattr(stats, "total_tokens", 0)),
    )


def _delta(before: LLMUsage, after: LLMUsage) -> LLMUsage:
    return LLMUsage(
        calls=max(0, after.calls - before.calls),
        cache_hits=max(0, after.cache_hits - before.cache_hits),
        retries=max(0, after.retries - before.retries),
        prompt_tokens=max(0, after.prompt_tokens - before.prompt_tokens),
        completion_tokens=max(0, after.completion_tokens - before.completion_tokens),
        total_tokens=max(0, after.total_tokens - before.total_tokens),
    )


def write_investigation(document: InvestigationDocument, path: str | Path) -> Path:
    """Write an investigation document as deterministic JSON."""
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = document.model_dump(mode="json")
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def _agent_snapshot(client: LLMClient) -> LLMUsage:
    return _usage(client)


def _resolve_hypotheses(
    client: LLMClient,
    *,
    duration_s: float,
    observations: ObservationSet,
    graph: GraphDocument | None,
    dependencies: list[Dependency],
    origin: datetime,
    observation_index_by_id: dict[str, Observation],
    edge_index_by_id: dict[str, GraphEdge],
) -> tuple[list[ProposedHypothesis], list[DroppedHypothesis], list[str]]:
    """Run the Proposer, validate citations and allow exactly one regeneration."""
    warnings: list[str] = []
    batch = propose_hypotheses(
        client,
        duration_s=duration_s,
        observations=observations,
        graph=graph,
        dependencies=dependencies,
        origin=origin,
    )
    accepted, dropped, feedback = accept_proposals(
        batch.hypotheses,
        observations=observation_index_by_id,
        edges=edge_index_by_id,
        use_graph=graph is not None,
    )
    if feedback:
        retry = propose_hypotheses(
            client,
            duration_s=duration_s,
            observations=observations,
            graph=graph,
            dependencies=dependencies,
            origin=origin,
            feedback=feedback,
        )
        retry_accepted, retry_dropped, retry_feedback = accept_proposals(
            retry.hypotheses,
            observations=observation_index_by_id,
            edges=edge_index_by_id,
            use_graph=graph is not None,
        )
        merged, duplicates = merge_valid(accepted, retry_accepted)
        accepted = merged
        dropped.extend(retry_dropped)
        dropped.extend(duplicates)
        if retry_feedback:
            warnings.append(
                "Citation validation still failed after one regeneration; "
                "the remaining invalid proposals were dropped."
            )
    else:
        merged, duplicates = merge_valid(accepted, [])
        accepted = merged
        dropped.extend(duplicates)
    return accepted, dropped, warnings


def investigate_run(
    run_dir: str | Path,
    *,
    use_graph: bool = True,
    client: LLMClient | None = None,
    observations: ObservationSet | None = None,
    graph: GraphDocument | None = None,
    output_path: str | Path | None = None,
) -> InvestigationResult:
    """Run the full hypothesis pipeline and write ``hypotheses.json``.

    Args:
        run_dir: Mission directory.
        use_graph: ``False`` is the ``--no-graph`` ablation: the Proposer sees
            observations only and every hypothesis must have ``edges=[]``.
        client: Optional pre-built LLM client; tests inject a fake.
        observations: Optional precomputed observations.
        graph: Optional precomputed graph, used only when ``use_graph`` is true.
        output_path: Optional output path; defaults to ``<run_dir>/hypotheses.json``.
    """
    ingested = ingest_run(run_dir)
    observation_set = observations or extract_observations(ingested)
    graph_document = graph if (use_graph and graph is not None) else None
    if use_graph and graph_document is None:
        graph_document = build_graph(ingested, observation_set)

    client = client or LLMClient()
    origin = ingested.timeline[0]
    observation_list = observation_set.observations
    observations_by_id = observation_index(observation_list)
    edges_by_id = edge_index(graph_document)

    usage_start = _agent_snapshot(client)
    agents: list[AgentUsage] = []
    warnings: list[str] = []

    proposer_before = _agent_snapshot(client)
    try:
        accepted, dropped, proposer_warnings = _resolve_hypotheses(
            client,
            duration_s=ingested.spec.duration_s,
            observations=observation_set,
            graph=graph_document,
            dependencies=ingested.spec.dependencies,
            origin=origin,
            observation_index_by_id=observations_by_id,
            edge_index_by_id=edges_by_id,
        )
    finally:
        agents.append(
            AgentUsage(
                agent="proposer",
                usage=_delta(proposer_before, _agent_snapshot(client)),
            )
        )
    warnings.extend(proposer_warnings)

    hypotheses = to_hypotheses(accepted)
    if not hypotheses:
        warnings.append("No hypothesis survived citation validation.")
        document = InvestigationDocument(
            scenario=ingested.spec.scenario,
            seed=ingested.spec.seed,
            mission=ingested.spec.mission,
            use_graph=use_graph,
            graph_nodes=(
                0 if graph_document is None else len(graph_document.nodes)
            ),
            graph_edges=0 if graph_document is None else len(graph_document.edges),
            hypotheses=[],
            dropped=dropped,
            warnings=warnings,
            agents=agents,
            total_usage=_delta(usage_start, _agent_snapshot(client)),
        )
        target = (
            Path(output_path).expanduser()
            if output_path is not None
            else ingested.run_dir / _DEFAULT_FILENAME
        )
        written = write_investigation(document, target)
        return InvestigationResult(
            ingested=ingested,
            observations=observation_set,
            graph=graph_document,
            document=document,
            output_path=written,
        )

    prosecutor_before = _agent_snapshot(client)
    prosecutor_reports, prosecutor_warnings = prosecute(
        client,
        hypotheses=hypotheses,
        observations=observation_list,
        graph=graph_document,
    )
    agents.append(
        AgentUsage(
            agent="prosecutor",
            usage=_delta(prosecutor_before, _agent_snapshot(client)),
        )
    )
    warnings.extend(prosecutor_warnings)

    skeptic_before = _agent_snapshot(client)
    skeptic_reports, skeptic_warnings = critique(
        client,
        hypotheses=hypotheses,
        observations=observation_list,
        graph=graph_document,
        dependencies=ingested.spec.dependencies,
    )
    agents.append(
        AgentUsage(
            agent="skeptic",
            usage=_delta(skeptic_before, _agent_snapshot(client)),
        )
    )
    warnings.extend(skeptic_warnings)

    judge_before = _agent_snapshot(client)
    ranked, judge_warnings = judge_hypotheses(
        client,
        hypotheses=hypotheses,
        observations=observation_list,
        graph=graph_document,
        prosecutor_reports=prosecutor_reports,
        skeptic_reports=skeptic_reports,
    )
    agents.append(
        AgentUsage(
            agent="judge",
            usage=_delta(judge_before, _agent_snapshot(client)),
        )
    )
    warnings.extend(judge_warnings)

    document = InvestigationDocument(
        scenario=ingested.spec.scenario,
        seed=ingested.spec.seed,
        mission=ingested.spec.mission,
        use_graph=use_graph,
        graph_nodes=(
            0 if graph_document is None else len(graph_document.nodes)
        ),
        graph_edges=0 if graph_document is None else len(graph_document.edges),
        hypotheses=ranked,
        dropped=dropped,
        warnings=warnings,
        agents=agents,
        total_usage=_delta(usage_start, _agent_snapshot(client)),
    )
    target = (
        Path(output_path).expanduser()
        if output_path is not None
        else ingested.run_dir / _DEFAULT_FILENAME
    )
    written = write_investigation(document, target)
    return InvestigationResult(
        ingested=ingested,
        observations=observation_set,
        graph=graph_document,
        document=document,
        output_path=written,
    )
