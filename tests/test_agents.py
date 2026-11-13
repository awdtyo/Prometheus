"""Tests for Phase 5: the hypothesis agents.

Every LLM interaction is scripted; no test touches the network. The pure
scoring, citation and ranking functions are tested directly, and one generated
mission exercises the full orchestration and the CLI with a fake client.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel
from typer.testing import CliRunner

import prometheus.cli as cli
from prometheus.agents.citations import validate_proposal
from prometheus.agents.evidence import score_hypothesis
from prometheus.agents.judge import rank_hypotheses
from prometheus.agents.run import investigate_run
from prometheus.agents.schemas import (
    JudgeNarratives,
    ProposalBatch,
    ProposedHypothesis,
    ProsecutorNarratives,
    SkepticNarratives,
)
from prometheus.config import Settings
from prometheus.contracts import (
    GraphDocument,
    GraphEdge,
    Hypothesis,
    HypothesisScore,
    Observation,
    ProsecutorReport,
    RootCauseLabel,
    SkepticReport,
)
from prometheus.graph import build_graph
from prometheus.ingest import ingest_run
from prometheus.llm.client import LLMError
from prometheus.observations import extract_observations
from prometheus.sim import load_scenario, simulate, write_run

SCENARIO = "battery_voltage_drop"
SEED = 7
runner = CliRunner()


@dataclass
class _Stats:
    """The subset of ``UsageStats`` the orchestrator reads."""

    calls: int = 0
    cache_hits: int = 0
    retries: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ScriptedClient:
    """Deterministic stand-in for :class:`LLMClient`.

    Responses are queued per pydantic schema, so the Proposer (which is called
    twice on regeneration) and the narrative agents are scripted independently.
    """

    def __init__(self, responses: dict[type[BaseModel], list[Any]]) -> None:
        self.responses = {schema: list(items) for schema, items in responses.items()}
        self.stats = _Stats()
        self.calls: list[tuple[str | None, type[BaseModel]]] = []

    def complete_json(
        self,
        prompt: str,
        schema: type[BaseModel],
        *,
        agent: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> BaseModel:
        self.stats.calls += 1
        self.stats.prompt_tokens += 120
        self.stats.completion_tokens += 40
        self.stats.total_tokens += 160
        self.calls.append((agent, schema))
        queue = self.responses.get(schema, [])
        if not queue:
            raise LLMError(f"no scripted response for {schema.__name__}")
        item = queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


@pytest.fixture(scope="module")
def mission(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Generate one mission, its observations and its graph once."""
    root = tmp_path_factory.mktemp("agents")
    run = simulate(load_scenario(SCENARIO), SEED)
    run_dir = root / "generated" / f"{SCENARIO}_{SEED}"
    truth_dir = root / "ground_truth" / f"{SCENARIO}_{SEED}"
    write_run(run, run_dir, truth_dir)
    ingested = ingest_run(run_dir)
    observations = extract_observations(ingested)
    graph = build_graph(ingested, observations)
    return {
        "root": root,
        "ingested": ingested,
        "observations": observations,
        "graph": graph,
    }


def _forward_edge(graph: GraphDocument) -> GraphEdge:
    """The strongest graph edge; its endpoints form a valid forward chain."""
    return sorted(graph.edges, key=lambda edge: (-edge.edge_score, edge.id))[0]


def _forward_path(graph: GraphDocument) -> tuple[list[str], list[str]]:
    """A two-edge forward path: three observations and their edge ids."""
    ordered = sorted(graph.edges, key=lambda edge: (-edge.edge_score, edge.id))
    by_source: dict[str, list[GraphEdge]] = {}
    for edge in ordered:
        by_source.setdefault(edge.source, []).append(edge)
    for first in ordered:
        for second in by_source.get(first.target, []):
            if second.target == first.source:
                continue
            return (
                [first.source, first.target, second.target],
                [first.id, second.id],
            )
    raise AssertionError("graph has no two-edge forward path")


def _outside(graph: GraphDocument, exclude: set[str], count: int = 1) -> list[str]:
    """Observation ids not in ``exclude``, for building invalid chains."""
    return [
        node.id for node in graph.nodes if node.id not in exclude
    ][:count]


def _proposal(
    root_cause: RootCauseLabel,
    chain: list[str],
    edges: list[str],
    *,
    subsystem: str = "power",
    summary: str | None = None,
) -> ProposedHypothesis:
    return ProposedHypothesis(
        root_cause=root_cause,
        root_subsystem=subsystem,  # type: ignore[arg-type]
        summary=summary or f"{root_cause.value} explains the chain",
        chain=chain,
        edges=edges,
        rationale="The cited observations and edges form a plausible mechanism.",
    )


def _valid_batch(mission: dict[str, Any]) -> ProposalBatch:
    graph: GraphDocument = mission["graph"]
    chain, edge_ids = _forward_path(graph)
    subsystem = {node.id: node for node in graph.nodes}[chain[0]].subsystem.value
    return ProposalBatch(
        hypotheses=[
            _proposal(
                RootCauseLabel.BATTERY_DEGRADATION,
                chain,
                edge_ids,
                subsystem=subsystem,
            ),
            _proposal(
                RootCauseLabel.POWER_DISTRIBUTION_FAULT,
                chain,
                edge_ids,
                subsystem=subsystem,
            ),
            _proposal(
                RootCauseLabel.LOAD_SHED,
                chain,
                edge_ids,
                subsystem=subsystem,
            ),
        ]
    )


def _hypothesis(
    identifier: str,
    *,
    chain: list[str],
    edges: list[str],
    root_subsystem: str,
) -> Hypothesis:
    return Hypothesis(
        id=identifier,
        root_cause=RootCauseLabel.BATTERY_DEGRADATION,
        root_subsystem=root_subsystem,  # type: ignore[arg-type]
        summary="battery degradation explains the chain",
        chain=chain,
        edges=edges,
        rationale="Sustained bus voltage sag with downstream thermal and pointing effects.",
    )


def _score(
    hypothesis: Hypothesis,
    *,
    mission: dict[str, Any],
    graph: GraphDocument | None,
    penalty: float,
) -> HypothesisScore:
    observations: list[Observation] = mission["observations"].observations
    edges = {edge.id: edge for edge in (graph.edges if graph is not None else [])}
    return score_hypothesis(
        hypothesis,
        observations=observations,
        graph=graph,
        edges=edges,
        skeptic=SkepticReport(penalty=penalty),
    )


def test_invented_observation_id_is_rejected_then_regenerated(
    mission: dict[str, Any], tmp_path: Path
) -> None:
    graph: GraphDocument = mission["graph"]
    chain, edge_ids = _forward_path(graph)
    subsystem = {node.id: node for node in graph.nodes}[chain[0]].subsystem.value
    bad = _proposal(
        RootCauseLabel.SENSOR_FAULT,
        ["OBS-9999", *chain[1:]],
        [],
        subsystem=subsystem,
    )
    first = ProposalBatch(
        hypotheses=[
            _proposal(
                RootCauseLabel.BATTERY_DEGRADATION,
                chain,
                edge_ids,
                subsystem=subsystem,
            ),
            bad,
            _proposal(
                RootCauseLabel.LOAD_SHED,
                chain,
                edge_ids,
                subsystem=subsystem,
            ),
        ]
    )
    client = ScriptedClient(
        {
            ProposalBatch: [first, _valid_batch(mission)],
            ProsecutorNarratives: [ProsecutorNarratives(items=[])],
            SkepticNarratives: [SkepticNarratives(items=[])],
            JudgeNarratives: [JudgeNarratives(items=[])],
        }
    )

    result = investigate_run(
        mission["ingested"].run_dir,
        client=client,  # type: ignore[arg-type]
        observations=mission["observations"],
        graph=graph,
        output_path=tmp_path / "hypotheses.json",
    )

    proposer_calls = [agent for agent, schema in client.calls if schema is ProposalBatch]
    assert len(proposer_calls) == 2
    assert result.document.hypotheses
    assert all(item.hypothesis.id.startswith("HYPO-") for item in result.document.hypotheses)
    invented = [
        dropped
        for dropped in result.document.dropped
        if any("OBS-9999" in reason for reason in dropped.reasons)
    ]
    assert invented, "the invented observation id must be recorded as a dropped proposal"
    assert all(
        "OBS-9999" not in item.hypothesis.chain for item in result.document.hypotheses
    )


def test_regeneration_is_limited_to_one(
    mission: dict[str, Any], tmp_path: Path
) -> None:
    graph: GraphDocument = mission["graph"]
    chain, edge_ids = _forward_path(graph)
    subsystem = {node.id: node for node in graph.nodes}[chain[0]].subsystem.value
    batch = ProposalBatch(
        hypotheses=[
            _proposal(
                RootCauseLabel.SENSOR_FAULT,
                ["OBS-9999", "OBS-9998", "OBS-9997"],
                [],
                subsystem=subsystem,
            ),
            _proposal(
                RootCauseLabel.TRANSMITTER_FAULT,
                [chain[0], "OBS-9998", chain[2]],
                [edge_ids[0]],
                subsystem=subsystem,
            ),
            _proposal(
                RootCauseLabel.UNKNOWN,
                ["OBS-9998", "OBS-9997", "OBS-9996"],
                [],
                subsystem=subsystem,
            ),
        ]
    )
    client = ScriptedClient({ProposalBatch: [batch, batch]})

    result = investigate_run(
        mission["ingested"].run_dir,
        client=client,  # type: ignore[arg-type]
        observations=mission["observations"],
        graph=graph,
        output_path=tmp_path / "hypotheses.json",
    )

    assert [schema for _, schema in client.calls].count(ProposalBatch) == 2
    assert result.document.hypotheses == []
    assert len(result.document.dropped) >= 4
    assert any("No hypothesis survived" in warning for warning in result.document.warnings)


def test_edge_must_connect_two_chain_observations(mission: dict[str, Any]) -> None:
    graph: GraphDocument = mission["graph"]
    edge = _forward_edge(graph)
    outside = _outside(graph, {edge.source, edge.target}, 2)
    proposal = _proposal(
        RootCauseLabel.BATTERY_DEGRADATION,
        [edge.source, *outside],
        [edge.id],
    )
    edges = {item.id: item for item in graph.edges}

    errors = validate_proposal(
        proposal,
        observations={node.id: node for node in graph.nodes},
        edges=edges,
        use_graph=True,
    )

    assert any("does not connect two observations in the chain" in error for error in errors)


def test_edge_must_not_point_backward(mission: dict[str, Any]) -> None:
    graph: GraphDocument = mission["graph"]
    edge = _forward_edge(graph)
    outside = _outside(graph, {edge.source, edge.target}, 1)
    proposal = _proposal(
        RootCauseLabel.BATTERY_DEGRADATION,
        [edge.target, edge.source, *outside],
        [edge.id],
    )
    edges = {item.id: item for item in graph.edges}

    errors = validate_proposal(
        proposal,
        observations={node.id: node for node in graph.nodes},
        edges=edges,
        use_graph=True,
    )

    assert any("points backward in the chain" in error for error in errors)


def test_duplicate_edge_id_is_rejected(mission: dict[str, Any]) -> None:
    graph: GraphDocument = mission["graph"]
    edge = _forward_edge(graph)
    outside = _outside(graph, {edge.source, edge.target}, 1)
    proposal = _proposal(
        RootCauseLabel.BATTERY_DEGRADATION,
        [edge.source, *outside, edge.target],
        [edge.id, edge.id],
    )
    edges = {item.id: item for item in graph.edges}

    errors = validate_proposal(
        proposal,
        observations={node.id: node for node in graph.nodes},
        edges=edges,
        use_graph=True,
    )

    assert "duplicate edge id" in errors


def test_judge_scores_are_reproducible(mission: dict[str, Any]) -> None:
    graph: GraphDocument = mission["graph"]
    edge = _forward_edge(graph)
    subsystem = {node.id: node for node in graph.nodes}[edge.source].subsystem.value
    hypothesis = _hypothesis(
        "HYPO-0001",
        chain=[edge.source, edge.target],
        edges=[edge.id],
        root_subsystem=subsystem,
    )

    first = _score(hypothesis, mission=mission, graph=graph, penalty=0.2)
    second = _score(hypothesis, mission=mission, graph=graph, penalty=0.2)

    assert first == second
    assert first.total == pytest.approx(
        0.30 * first.temporal_consistency
        + 0.20 * first.spec_consistency
        + 0.25 * first.statistical_support
        + 0.25 * first.observation_coverage
        - 0.30 * first.contradiction_penalty
    )


def test_skeptic_penalty_lowers_the_total(mission: dict[str, Any]) -> None:
    graph: GraphDocument = mission["graph"]
    edge = _forward_edge(graph)
    subsystem = {node.id: node for node in graph.nodes}[edge.source].subsystem.value
    hypothesis = _hypothesis(
        "HYPO-0001",
        chain=[edge.source, edge.target],
        edges=[edge.id],
        root_subsystem=subsystem,
    )

    clean = _score(hypothesis, mission=mission, graph=graph, penalty=0.0)
    challenged = _score(hypothesis, mission=mission, graph=graph, penalty=0.8)

    assert challenged.total < clean.total
    assert challenged.total == pytest.approx(clean.total - 0.30 * 0.8)


def test_ranking_is_stable_for_tied_scores(mission: dict[str, Any]) -> None:
    graph: GraphDocument = mission["graph"]
    edge = _forward_edge(graph)
    subsystem = {node.id: node for node in graph.nodes}[edge.source].subsystem.value
    hypotheses = [
        _hypothesis(
            f"HYPO-000{index}",
            chain=[edge.source, edge.target],
            edges=[edge.id],
            root_subsystem=subsystem,
        )
        for index in (1, 2)
    ]
    score = HypothesisScore(
        temporal_consistency=0.5,
        spec_consistency=0.5,
        statistical_support=0.5,
        observation_coverage=0.5,
        contradiction_penalty=0.0,
        total=0.5,
    )
    scores = {item.id: score for item in hypotheses}
    prosecutor = {item.id: ProsecutorReport() for item in hypotheses}
    skeptic = {item.id: SkepticReport() for item in hypotheses}

    forward = rank_hypotheses(
        hypotheses,
        scores=scores,
        prosecutor_reports=prosecutor,
        skeptic_reports=skeptic,
    )
    backward = rank_hypotheses(
        list(reversed(hypotheses)),
        scores=scores,
        prosecutor_reports=prosecutor,
        skeptic_reports=skeptic,
    )

    assert [item.hypothesis.id for item in forward] == ["HYPO-0001", "HYPO-0002"]
    assert [item.hypothesis.id for item in backward] == ["HYPO-0001", "HYPO-0002"]
    assert [item.rank for item in forward] == [1, 2]
    assert [item.margin_to_next for item in forward] == [0.0, 0.0]


def test_no_graph_mode_accepts_only_observation_chains(
    mission: dict[str, Any], tmp_path: Path
) -> None:
    observations = mission["observations"].observations
    proposals = ProposalBatch(
        hypotheses=[
            _proposal(
                RootCauseLabel.BATTERY_DEGRADATION,
                [observations[8].id, observations[9].id, observations[10].id],
                [],
            ),
            _proposal(
                RootCauseLabel.THERMAL_CONTROL_FAILURE,
                [observations[9].id, observations[10].id, observations[11].id],
                [],
            ),
            _proposal(
                RootCauseLabel.SENSOR_FAULT,
                [observations[10].id, observations[11].id, observations[12].id],
                [],
            ),
        ]
    )
    client = ScriptedClient(
        {
            ProposalBatch: [proposals],
            ProsecutorNarratives: [ProsecutorNarratives(items=[])],
            SkepticNarratives: [SkepticNarratives(items=[])],
            JudgeNarratives: [JudgeNarratives(items=[])],
        }
    )

    result = investigate_run(
        mission["ingested"].run_dir,
        use_graph=False,
        client=client,  # type: ignore[arg-type]
        observations=mission["observations"],
        output_path=tmp_path / "hypotheses.json",
    )

    assert result.document.use_graph is False
    assert result.document.graph_edges == 0
    assert result.document.hypotheses
    assert all(item.hypothesis.edges == [] for item in result.document.hypotheses)
    assert all(
        item.score.spec_consistency == 0.5
        and item.score.statistical_support == 0.5
        for item in result.document.hypotheses
    )


def test_graph_mode_records_usage_per_agent(
    mission: dict[str, Any], tmp_path: Path
) -> None:
    graph: GraphDocument = mission["graph"]
    client = ScriptedClient(
        {
            ProposalBatch: [_valid_batch(mission)],
            ProsecutorNarratives: [ProsecutorNarratives(items=[])],
            SkepticNarratives: [SkepticNarratives(items=[])],
            JudgeNarratives: [JudgeNarratives(items=[])],
        }
    )

    result = investigate_run(
        mission["ingested"].run_dir,
        client=client,  # type: ignore[arg-type]
        observations=mission["observations"],
        graph=graph,
        output_path=tmp_path / "hypotheses.json",
    )

    document = result.document
    assert document.use_graph is True
    assert document.graph_edges == len(graph.edges)
    assert [agent.agent for agent in document.agents] == [
        "proposer",
        "prosecutor",
        "skeptic",
        "judge",
    ]
    assert document.total_usage.calls == 4
    assert document.total_usage.total_tokens == 640
    assert all(agent.usage.calls == 1 for agent in document.agents)
    assert [item.rank for item in document.hypotheses] == list(
        range(1, len(document.hypotheses) + 1)
    )
    assert (tmp_path / "hypotheses.json").exists()


def test_cli_investigate_writes_hypotheses_json(
    mission: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observations = mission["observations"].observations
    proposals = ProposalBatch(
        hypotheses=[
            _proposal(
                RootCauseLabel.BATTERY_DEGRADATION,
                [observations[8].id, observations[9].id, observations[10].id],
                [],
            ),
            _proposal(
                RootCauseLabel.THERMAL_CONTROL_FAILURE,
                [observations[9].id, observations[10].id, observations[11].id],
                [],
            ),
            _proposal(
                RootCauseLabel.SENSOR_FAULT,
                [observations[10].id, observations[11].id, observations[12].id],
                [],
            ),
        ]
    )
    client = ScriptedClient(
        {
            ProposalBatch: [proposals],
            ProsecutorNarratives: [ProsecutorNarratives(items=[])],
            SkepticNarratives: [SkepticNarratives(items=[])],
            JudgeNarratives: [JudgeNarratives(items=[])],
        }
    )
    settings = Settings(
        groq_api_key="test-key",
        groq_model="test-main",
        cache_dir=tmp_path / "cache",
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "LLMClient", lambda **_: client)

    out = tmp_path / "cli-hypotheses.json"
    result = runner.invoke(
        cli.app,
        [
            "investigate",
            str(mission["ingested"].run_dir),
            "--no-graph",
            "--out",
            str(out),
        ],
    )

    assert result.exit_code == 0, result.output
    assert out.exists()
    assert "hypotheses:" in result.output
    assert "total_tokens" in result.output
