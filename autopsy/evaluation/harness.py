"""Evaluation harness: metrics, baselines, and the evaluate CLI.

The harness runs the autopsy pipeline (or a cheap baseline) for each
(scenario, seed, variant), computes the twelve ``EvaluationMetrics`` fields
documented in ``docs/api-contact.md`` via :mod:`autopsy.evaluation.metrics`,
and writes mode-labelled results under ``data/eval/``.

Ground truth (``fixtures/expected/*_ground_truth.json``) is read *only* here,
on the evaluation side of the boundary. It is never passed to hypothesis
agents.
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autopsy.analysis.scoring import ScoringConfig
from autopsy.evaluation.metrics import METRIC_KEYS, compute_evaluation_metrics
from autopsy.graph.builder import build_graph
from autopsy.ingest.loaders import (
    load_ground_truth,
    load_investigation_inputs,
    load_subsystem_specs,
)
from autopsy.llm.client import LLMClient, LLMConfig
from autopsy.observations.extractor import extract_observations
from autopsy.schemas.events import MissionEvent
from autopsy.schemas.evidence import Evidence
from autopsy.schemas.graph import Graph
from autopsy.schemas.hypotheses import Hypothesis
from autopsy.schemas.observations import Observation

GROUND_TRUTH_DIR = Path("fixtures/expected")
EVAL_DIR = Path("data/eval")


def _iso(dt: Any) -> str:
    if isinstance(dt, datetime):
        return dt.astimezone(UTC).isoformat()
    return str(dt)


def _earliest_anomaly_hypothesis(
    observations: list[Observation],
) -> Hypothesis:
    """Cheap baseline: blame the subsystem of the earliest observation."""
    if not observations:
        return Hypothesis(
            hypothesis_id="base_earliest_00",
            title="Earliest anomaly baseline",
            summary="No observations available.",
            causal_chain=[],
            evidence_ids=[],
            contradiction_ids=[],
            assumptions=[],
            confidence=0.0,
            score=0.0,
        )
    earliest = min(observations, key=lambda o: o.timestamp)
    return Hypothesis(
        hypothesis_id="base_earliest_00",
        title="Earliest anomaly baseline",
        summary=(
            f"Blame the subsystem of the earliest observation ({earliest.subsystem})."
        ),
        causal_chain=[f"obs:{earliest.observation_id}"],
        evidence_ids=[earliest.observation_id],
        contradiction_ids=[],
        assumptions=["Earliest abnormal observation is the root cause."],
        confidence=0.5,
        score=0.0,
    )


def _build_config(fake_llm: bool) -> LLMConfig:
    base = LLMConfig.from_env()
    if fake_llm:
        return LLMConfig(
            api_key=None,
            fake=True,
            cache_dir=base.cache_dir,
            requests_per_minute=base.requests_per_minute,
            tokens_per_minute=base.tokens_per_minute,
            tokens_per_day=base.tokens_per_day,
        )
    return base


def _run_pipeline(
    scenario_id: str,
    llm: LLMClient,
) -> tuple[list[Hypothesis], list[Evidence], Graph, list[Observation], list[MissionEvent]]:
    inputs = load_investigation_inputs(f"configs/scenarios/{scenario_id}.yaml")
    specs = load_subsystem_specs("configs/subsystems")
    observations = extract_observations(inputs)
    graph = build_graph(
        observations, inputs.events, inputs.telemetry, specs
    )
    hypotheses, evidence = [], []
    if llm is not None:
        from autopsy.agents.orchestrator import AgentConfig, generate_hypotheses

        hypotheses, evidence = generate_hypotheses(
            graph, observations, inputs.events, specs, llm, config=AgentConfig()
        )
    return hypotheses, evidence, graph, observations, inputs.events


def _score_row(
    scenario_id: str,
    variant: str,
    seed: int,
    status: str,
    hypotheses: list[Hypothesis],
    evidence: list[Evidence],
    graph: Graph,
    observations: list[Observation],
    events: list[MissionEvent],
    ground_truth: Any,
    runtime_seconds: float,
    config: ScoringConfig,
) -> dict[str, Any]:
    metrics = compute_evaluation_metrics(
        hypotheses,
        evidence,
        graph,
        observations,
        events,
        ground_truth,
        runtime_seconds,
        config,
    )
    return {
        "scenario": scenario_id,
        "variant": variant,
        "seed": seed,
        "status": status,
        "metrics": metrics,
        "num_hypotheses": len(hypotheses),
    }


def run_evaluation(
    scenarios: list[str] | None = None,
    seeds: int = 1,
    fake_llm: bool = True,
    progress: Callable[[str, str, float], None] | None = None,
    no_llm_baseline: bool = False,
    mode: str = "fake",
) -> dict[str, Any]:
    scenarios = scenarios or ["battery_failure"]
    progress = progress or (lambda s, m, f: None)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    config = ScoringConfig()
    llm_cfg = _build_config(fake_llm)
    rows: list[dict[str, Any]] = []
    total = len(scenarios) * seeds * (2 if not no_llm_baseline else 1)
    i = 0

    for sid in scenarios:
        inputs = load_investigation_inputs(f"configs/scenarios/{sid}.yaml")
        observations = extract_observations(inputs)
        events = inputs.events
        graph = build_graph(
            observations, events, inputs.telemetry, load_subsystem_specs("configs/subsystems")
        )
        gt_path = GROUND_TRUTH_DIR / f"{sid}_ground_truth.json"
        ground_truth = load_ground_truth(gt_path) if gt_path.exists() else None

        variants: list[tuple[str, bool]] = [("pipeline", True)]
        if not no_llm_baseline:
            variants.append(("earliest_anomaly", False))

        for name, use_llm in variants:
            for seed in range(seeds):
                i += 1
                progress("eval", f"{sid}/{name} seed {seed}", i / total)
                llm = LLMClient(llm_cfg) if use_llm else None
                try:
                    if name == "pipeline":
                        t0 = time.perf_counter()
                        hyps, evs, g, obs, evts = _run_pipeline(sid, llm)
                        dt = time.perf_counter() - t0
                        row = _score_row(
                            sid, "pipeline", seed, "completed", hyps, evs, g, obs, evts,
                            ground_truth, dt, config,
                        )
                    elif name == "earliest_anomaly":
                        hyp = _earliest_anomaly_hypothesis(observations)
                        t0 = time.perf_counter()
                        row = _score_row(
                            sid, "earliest_anomaly", seed, "completed",
                            [hyp], [], graph, observations, events,
                            ground_truth, time.perf_counter() - t0, config,
                        )
                    else:
                        continue
                except Exception as exc:  # noqa: BLE001
                    rows.append(
                        {
                            "scenario": sid,
                            "variant": name,
                            "seed": seed,
                            "status": "error",
                            "error": str(exc),
                        }
                    )
                    continue
                rows.append(row)

    report: dict[str, Any] = {"mode": mode, "rows": rows, "aggregates": _aggregate(rows)}
    results_path = EVAL_DIR / f"results.{mode}.json"
    results_path.write_text(json.dumps(report, indent=2))
    return report


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, float]]] = {}
    for row in rows:
        if row.get("status") != "completed":
            continue
        key = (row["scenario"], row["variant"])
        grouped.setdefault(key, []).append(row["metrics"])
    out: dict[str, Any] = {}
    for key, metric_list in grouped.items():
        agg: dict[str, float] = {}
        for key_name in METRIC_KEYS:
            values = [m[key_name] for m in metric_list if key_name in m]
            agg[key_name] = round(sum(values) / len(values), 4) if values else 0.0
        out[f"{key[0]}::{key[1]}"] = agg
    return out


def print_table(report: dict[str, Any]) -> None:
    print(
        f"{'scenario':<22} {'variant':<18} {'root_cause':<10} {'fault_loc':<10} "
        f"{'chain_acc':<10} {'cov':<8} {'temp':<8} {'unsupported':<12} {'runtime':<8}"
    )
    for row in report["rows"]:
        if row.get("status") != "completed":
            continue
        m = row["metrics"]
        print(
            f"{row['scenario']:<22} {row['variant']:<18} "
            f"{m['root_cause_accuracy']:<10.2f} "
            f"{m['fault_localization_accuracy']:<10.2f} "
            f"{m['causal_chain_accuracy']:<10.2f} "
            f"{m['evidence_coverage']:<8.2f} "
            f"{m['temporal_ordering_accuracy']:<8.2f} "
            f"{m['unsupported_claim_rate']:<12.4f} "
            f"{m['runtime_seconds']:<8.4f}"
        )


def main() -> None:
    ap = argparse.ArgumentParser(prog="autopsy-evaluate")
    ap.add_argument("--scenarios", nargs="*", default=None)
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--no-llm-baseline", action="store_true")
    ap.add_argument("--fake-llm", action="store_true", default=True)
    ap.add_argument("--real-llm", action="store_true", default=False)
    ap.add_argument("--json-out", dest="json_out", default=None)
    args = ap.parse_args()
    mode = "real" if args.real_llm else "fake"
    fake_llm = args.fake_llm and not args.real_llm
    report = run_evaluation(
        scenarios=args.scenarios,
        seeds=args.seeds,
        fake_llm=fake_llm,
        no_llm_baseline=args.no_llm_baseline,
        mode=mode,
    )
    print_table(report)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2))
    print(f"\nSaved detailed results to {EVAL_DIR / f'results.{mode}.json'}")


if __name__ == "__main__":
    main()
