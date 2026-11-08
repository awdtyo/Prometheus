"""Phase 4 evaluation: does the graph recover the injected causal chain?

This module is one of the two places allowed to read ground truth. It asks the
two questions the phase prompt poses:

* are the true chain edges present (directed, and as an unordered pair)?
* do the true chain edges outscore the edges incident to the deliberate
  distractor?

Some injected links cannot be directed because the Phase 3 detector fires the
target before the source; the unordered-pair recall records those honestly
instead of silently counting them as failures.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from prometheus.graph import build_graph_run
from prometheus.sim import load_scenario, simulate, write_run

SCENARIOS = (
    "battery_voltage_drop",
    "reaction_wheel_friction",
    "heater_stuck_on",
)
SEED = 7
DISTRACTOR_TOLERANCE_S = 1200.0


def _channel(entry: dict[str, Any]) -> str:
    return f"{entry['subsystem']}.{entry['channel']}"


@pytest.fixture(scope="module")
def evaluated(tmp_path_factory: pytest.TempPathFactory) -> list[dict[str, Any]]:
    """Generate every acceptance scenario and evaluate its graph once."""
    root = tmp_path_factory.mktemp("graph-eval")
    results: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        run = simulate(load_scenario(scenario), SEED)
        run_dir = root / "generated" / f"{scenario}_{SEED}"
        truth_dir = root / "ground_truth" / f"{scenario}_{SEED}"
        write_run(run, run_dir, truth_dir)

        result = build_graph_run(
            run_dir,
            json_path=root / scenario / "graph.json",
            html_path=root / scenario / "graph.html",
        )
        truth = json.loads(
            (truth_dir / "ground_truth.json").read_text(encoding="utf-8")
        )
        by_id = {node.id: node for node in result.document.nodes}
        origin = result.ingested.timeline[0]
        edges = result.document.edges

        chain: list[dict[str, Any]] = []
        for source, target in zip(
            truth["causal_chain"], truth["causal_chain"][1:], strict=False
        ):
            source_channel = _channel(source)
            target_channel = _channel(target)
            directed = [
                edge
                for edge in edges
                if by_id[edge.source].channel == source_channel
                and by_id[edge.target].channel == target_channel
            ]
            unordered = [
                edge
                for edge in edges
                if {by_id[edge.source].channel, by_id[edge.target].channel}
                == {source_channel, target_channel}
            ]
            chain.append(
                {
                    "source": source_channel,
                    "target": target_channel,
                    "directed": max(
                        (edge.edge_score for edge in directed), default=None
                    ),
                    "unordered": max(
                        (edge.edge_score for edge in unordered), default=None
                    ),
                }
            )

        distractor = truth["distractor"]
        distractor_channel = _channel(distractor)
        distractor_nodes = [
            node
            for node in result.document.nodes
            if node.channel == distractor_channel
            and abs(
                (node.t_start - origin).total_seconds() - distractor["start_s"]
            )
            <= DISTRACTOR_TOLERANCE_S
        ]
        distractor_ids = {node.id for node in distractor_nodes}
        distractor_edges = [
            edge
            for edge in edges
            if edge.source in distractor_ids or edge.target in distractor_ids
        ]
        distractor_max = max(
            (edge.edge_score for edge in distractor_edges), default=0.0
        )

        true_scores = [
            item["unordered"]
            for item in chain
            if item["unordered"] is not None
        ]
        results.append(
            {
                "scenario": scenario,
                "edges": len(edges),
                "spec_edges": sum(edge.spec_support for edge in edges),
                "chain": chain,
                "directed_hits": sum(
                    item["directed"] is not None for item in chain
                ),
                "unordered_hits": sum(
                    item["unordered"] is not None for item in chain
                ),
                "true_max": max(true_scores),
                "distractor_channel": distractor_channel,
                "distractor_edges": len(distractor_edges),
                "distractor_max": distractor_max,
            }
        )
    return results


def test_true_chain_edges_are_present(evaluated: list[dict[str, Any]]) -> None:
    total = sum(len(item["chain"]) for item in evaluated)
    directed = sum(item["directed_hits"] for item in evaluated)
    unordered = sum(item["unordered_hits"] for item in evaluated)

    assert unordered / total >= 0.7, f"unordered recall {unordered}/{total}"
    assert directed / total >= 0.5, f"directed recall {directed}/{total}"


def test_true_edges_outscore_distractor_edges(
    evaluated: list[dict[str, Any]],
) -> None:
    for item in evaluated:
        assert item["true_max"] > item["distractor_max"], (
            f"{item['scenario']}: true max {item['true_max']:.3f} "
            f"<= distractor max {item['distractor_max']:.3f}"
        )


def test_graph_eval_report(evaluated: list[dict[str, Any]]) -> None:
    print("\nchain edge                                             directed  pair   score")
    for item in evaluated:
        print(f"\n{item['scenario']}  (edges={item['edges']}, spec={item['spec_edges']})")
        for entry in item["chain"]:
            directed = (
                f"{entry['directed']:.3f}" if entry["directed"] is not None else "MISS"
            )
            unordered = (
                f"{entry['unordered']:.3f}" if entry["unordered"] is not None else "MISS"
            )
            pair = f"{entry['source']} -> {entry['target']}"
            print(f"  {pair:<52} {directed:>8} {unordered:>6}")

    print(
        "\nscenario                   edges  directed  pair   true max  "
        "distractor                dmax   margin"
    )
    for item in evaluated:
        total = len(item["chain"])
        print(
            f"{item['scenario']:<26} {item['edges']:>5} "
            f"{item['directed_hits']}/{total:<8} {item['unordered_hits']}/{total:<4} "
            f"{item['true_max']:.3f}     {item['distractor_channel']:<22} "
            f"{item['distractor_max']:.3f}  {item['true_max'] - item['distractor_max']:+.3f}"
        )
