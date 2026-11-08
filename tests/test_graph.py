"""Tests for Phase 4: the temporal causal graph.

Synthetic residual series pin down the timing and permutation logic without
touching the simulator. Generated missions exercise the full
ingest -> observe -> graph path, the NetworkX view, JSON round-tripping and the
CLI. Ground truth is not read here; ``test_graph_eval.py`` owns that.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

import prometheus.cli as cli
from prometheus.contracts import (
    GraphDocument,
    GraphEdge,
    Observation,
    ObservationKind,
    ObservationSource,
    Severity,
    Subsystem,
)
from prometheus.graph import (
    GraphConfig,
    ResidualSeries,
    build_graph_run,
    measure_edge,
    read_graph,
    to_networkx,
    write_graph,
)
from prometheus.ingest import ingest_run
from prometheus.observations import extract_observations
from prometheus.sim import load_scenario, simulate, write_run

SCENARIO = "battery_voltage_drop"
SEED = 7
ORIGIN = datetime(2026, 1, 1, tzinfo=UTC)

runner = CliRunner()


def _pulse_series(
    epoch_s: float,
    *,
    start_s: float = 0.0,
    stop_s: float = 12000.0,
    grid_s: float = 60.0,
) -> ResidualSeries:
    """A residual channel containing one Gaussian pulse at ``epoch_s``."""
    timestamps = np.arange(start_s, stop_s + 0.5 * grid_s, grid_s, dtype=float)
    values = np.exp(-0.5 * ((timestamps - epoch_s) / 120.0) ** 2)
    return ResidualSeries(timestamps=timestamps, values=values, grid_s=grid_s)


def _noise_series(seed: int, *, grid_s: float = 30.0) -> ResidualSeries:
    rng = np.random.default_rng(seed)
    timestamps = np.arange(0.0, 12000.0 + 0.5 * grid_s, grid_s, dtype=float)
    return ResidualSeries(
        timestamps=timestamps,
        values=rng.normal(0.0, 1.0, timestamps.size),
        grid_s=grid_s,
    )


@pytest.fixture(scope="module")
def mission(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    """Generate one mission once and build its graph once."""
    root = tmp_path_factory.mktemp("graph")
    run = simulate(load_scenario(SCENARIO), SEED)
    run_dir = root / "generated" / f"{SCENARIO}_{SEED}"
    truth_dir = root / "ground_truth" / f"{SCENARIO}_{SEED}"
    write_run(run, run_dir, truth_dir)
    ingested = ingest_run(run_dir)
    observations = extract_observations(ingested)
    result = build_graph_run(
        run_dir,
        observations=observations,
        json_path=root / "graph.json",
        html_path=root / "graph.html",
    )
    return {
        "run_dir": run_dir,
        "root": root,
        "ingested": ingested,
        "observations": observations,
        "result": result,
    }


def test_lag_recovered_from_delayed_pulse() -> None:
    # Source pulse at 5000 s, target pulse 300 s later. The target window is
    # cut 600 s after the source onset, so onset lag alone overestimates by
    # 300 s; cross-correlation must correct it back to the physical 300 s.
    source = _pulse_series(5000.0)
    target = _pulse_series(5300.0)
    evidence = measure_edge(
        source,
        target,
        source_onset_epoch_s=5000.0,
        target_onset_epoch_s=5600.0,
        rng=np.random.default_rng(11),
        permutations=50,
    )

    assert evidence.onset_lag_s == pytest.approx(600.0)
    assert evidence.xcorr_lag_s is not None
    assert evidence.xcorr_lag_s == pytest.approx(-300.0, abs=60.0)
    assert evidence.lag_estimate_s == pytest.approx(300.0, abs=60.0)
    assert evidence.correlation > 0.95
    assert evidence.lag_min_s <= evidence.lag_estimate_s <= evidence.lag_max_s


def test_permutation_test_keeps_noise_unsupported() -> None:
    # Independent noise with no shared shape. The best-of-many-shift statistic
    # is corrected by the permutation test, so most pairs must stay weak.
    supports: list[float] = []
    p_values: list[float] = []
    for seed in range(6):
        evidence = measure_edge(
            _noise_series(seed),
            _noise_series(seed + 100),
            source_onset_epoch_s=4000.0,
            target_onset_epoch_s=4300.0,
            rng=np.random.default_rng(500 + seed),
            permutations=100,
        )
        supports.append(evidence.statistical_support)
        p_values.append(evidence.p_value)

    assert float(np.mean(supports)) < 0.35
    assert max(supports) < 0.55
    assert sum(p_value > 0.05 for p_value in p_values) >= 5


def test_temporal_ordering_is_enforced_in_built_graph(
    mission: dict[str, object],
) -> None:
    result = mission["result"]
    by_id = {node.id: node for node in result.document.nodes}
    assert result.document.edges, "expected at least one edge"

    for edge in result.document.edges:
        assert by_id[edge.target].t_start > by_id[edge.source].t_start


def test_graph_document_rejects_backward_edge() -> None:
    early = Observation(
        id="OBS-0001",
        subsystem=Subsystem.POWER,
        channel="power.bus_voltage_v",
        t_start=ORIGIN,
        t_end=ORIGIN + timedelta(seconds=60),
        kind=ObservationKind.STEP,
        magnitude=-3.0,
        severity=Severity.WARNING,
        confidence=0.9,
        source=ObservationSource.TELEMETRY,
    )
    late = Observation(
        id="OBS-0002",
        subsystem=Subsystem.COMMS,
        channel="comms.tx_power_dbw",
        t_start=ORIGIN + timedelta(seconds=300),
        t_end=ORIGIN + timedelta(seconds=360),
        kind=ObservationKind.STEP,
        magnitude=-2.0,
        severity=Severity.WARNING,
        confidence=0.9,
        source=ObservationSource.TELEMETRY,
    )
    backward = GraphEdge(
        id="EDGE-0001",
        source="OBS-0002",
        target="OBS-0001",
        spec_support=True,
        onset_lag_s=-300.0,
        lag_estimate_s=300.0,
        lag_min_s=0.0,
        lag_max_s=600.0,
        correlation=0.5,
        p_value=0.01,
        statistical_support=0.5,
        lag_agreement=1.0,
        edge_score=0.5,
    )

    with pytest.raises(ValidationError, match="temporal ordering"):
        GraphDocument(
            scenario=SCENARIO,
            nodes=[early, late],
            edges=[backward],
        )


def test_graph_has_stable_edge_ids_and_spec_flags(
    mission: dict[str, object],
) -> None:
    document = mission["result"].document

    assert [edge.id for edge in document.edges] == [
        f"EDGE-{number:04d}" for number in range(1, len(document.edges) + 1)
    ]
    assert [(edge.source, edge.target) for edge in document.edges] == sorted(
        (edge.source, edge.target) for edge in document.edges
    )
    for edge in document.edges:
        if edge.spec_support:
            assert edge.mechanism
        else:
            assert edge.mechanism == ""
        assert 0.0 <= edge.edge_score <= 1.0


def test_event_observations_are_isolated_nodes(
    mission: dict[str, object],
) -> None:
    document = mission["result"].document
    events = {node.id for node in document.nodes if node.channel is None}
    incident = {
        endpoint
        for edge in document.edges
        for endpoint in (edge.source, edge.target)
    }

    assert events
    assert events.isdisjoint(incident)


def test_json_round_trip(mission: dict[str, object], tmp_path) -> None:
    document = mission["result"].document
    path = write_graph(document, tmp_path / "nested" / "graph.json")
    restored = read_graph(path)

    assert restored == document
    assert restored.model_dump(mode="json") == document.model_dump(mode="json")


def test_networkx_view_matches_document(mission: dict[str, object]) -> None:
    document = mission["result"].document
    graph = to_networkx(document)

    assert graph.is_directed()
    assert graph.number_of_nodes() == len(document.nodes)
    assert graph.number_of_edges() == len(document.edges)
    for edge in document.edges:
        assert graph.has_edge(edge.source, edge.target)
        assert graph[edge.source][edge.target]["edge_score"] == edge.edge_score


def test_cli_writes_json_and_html(
    mission: dict[str, object], tmp_path
) -> None:
    run_dir = mission["run_dir"]
    json_path = tmp_path / "cli" / "graph.json"
    html_path = tmp_path / "cli" / "graph.html"

    result = runner.invoke(
        cli.app,
        [
            "graph",
            str(run_dir),
            "--out",
            str(json_path),
            "--html",
            str(html_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert json_path.exists()
    assert html_path.exists()
    assert "edges:" in result.output
    assert "<svg" in html_path.read_text(encoding="utf-8")
    assert read_graph(json_path).scenario == SCENARIO


def test_weak_edges_are_pruned(mission: dict[str, object]) -> None:
    document = mission["result"].document
    config = GraphConfig()

    for edge in document.edges:
        assert edge.edge_score >= config.min_edge_score
        assert (
            edge.p_value <= config.max_p_value
            or (edge.spec_support and edge.edge_score >= config.min_spec_score)
        )
