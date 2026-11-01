"""Evaluation harness: metrics, baselines, and the evaluate CLI.

Metrics are computed per (scenario, seed) and populated into
``RunResult.evaluation_metrics`` using the 12-field ``EvaluationMetrics`` shape
from docs/api-contract.md. Ground truth is loaded only here (evaluation side of
the boundary) and never passed to hypothesis agents.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autopsy.agents.models import ProposerOutput
from autopsy.analysis.scoring import ScoringConfig, score_hypotheses
from autopsy.graph.builder import build_graph
from autopsy.ingest.loaders import (
    load_ground_truth,
    load_investigation_inputs,
    load_subsystem_specs,
)
from autopsy.llm.client import LLMClient, LLMConfig, complete_json
from autopsy.llm.config import ModelName
from autopsy.observations.extractor import extract_observations

GROUND_TRUTH_DIR = Path("fixtures/expected")
EVAL_DIR = Path("data/eval")

# The 12 EvaluationMetrics fields from docs/api-contract.md.
METRIC_KEYS = (
    "root_cause_accuracy",
    "fault_localization_accuracy",
    "causal_chain_accuracy",
    "evidence_coverage",
    "temporal_ordering_accuracy",
    "contradiction_handling",
    "unsupported_claim_rate",
    "runtime_seconds",
    "evidence_weight",
    "consistency_weight",
    "coverage_weight",
    "contradiction_penalty",
)


def _iso(dt) -> str:
    if isinstance(dt, datetime):
        return dt.astimezone(UTC).isoformat()
    return str(dt)


def _subsystem_of_node(node_id: str, observations, events) -> str | None:
    for o in observations:
        if o.observation_id == node_id:
            return o.subsystem
    for e in events:
        if e.event_id == node_id:
            return e.subsystem
    if node_id.startswith("obs:"):
        return node_id.split(":", 1)[1].split("_")[0] if "_" in node_id else None
    if node_id.startswith("evt:"):
        return node_id.split(":", 1)[1].split("_")[0] if "_" in node_id else None
    return None


def _chain_references_subsystem(chain, target: str, observations, events) -> bool:
    target = target.lower()
    text = " ".join(chain).lower()
    if target in text:
        return True
    for node in chain:
        sub = _subsystem_of_node(node, observations, events)
        if sub and sub.lower() == target:
            return True
    return False


def _causal_chain_accuracy(leading, ground_truth, observations, events) -> float:
    if not ground_truth or not leading.causal_chain:
        return 0.0
    steps = ground_truth.expected_causal_sequence
    if not steps:
        return 0.0
    recovered = 0
    for step in steps:
        text = " ".join(leading.causal_chain).lower()
        if step.subsystem.lower() in text:
            recovered += 1
        else:
            for node in leading.causal_chain:
                sub = _subsystem_of_node(node, observations, events)
                if sub and sub.lower() == step.subsystem.lower():
                    recovered += 1
                    break
    return recovered / len(steps)


def _temporal_ordering(leading, observations, events) -> float:
    if len(leading.causal_chain) < 2:
        return 1.0
    ts_by_id = {}
    for o in observations:
        ts_by_id[o.observation_id] = o.timestamp
    for e in events:
        ts_by_id[e.event_id] = e.timestamp
    times = []
    for node in leading.causal_chain:
        t = ts_by_id.get(node)
        if t is not None:
            times.append(t)
    if len(times) < 2:
        return 1.0
    return 1.0 if all(b >= a for a, b in zip(times, times[1:], strict=False)) else 0.0


def compute_metrics(
    scenario_id: str,
    hypotheses,
    evidence,
    ground_truth,
    observations,
    events,
    config: ScoringConfig,
    runtime_seconds: float,
    chain_score_detail: dict[str, Any] | None = None,
) -> dict[str, float]:
    chain_score_detail = chain_score_detail or {}
    leading = hypotheses[0] if hypotheses else None
    target = (
        ground_truth.injected_fault.target_subsystem if ground_truth else None
    )

    root_cause = 0.0
    fault_loc = 0.0
    if leading is not None and target:
        if _chain_references_subsystem(leading.causal_chain, target, observations, events):
            root_cause = 1.0
        if any(
            _chain_references_subsystem(h.causal_chain, target, observations, events)
            for h in hypotheses
        ):
            fault_loc = 1.0

    chain_acc = (
        _causal_chain_accuracy(leading, ground_truth, observations, events)
        if leading is not None
        else 0.0
    )
    temporal = _temporal_ordering(leading, observations, events) if leading is not None else 0.0

    # evidence coverage from scoring: fraction of observations explained
    coverage = chain_score_detail.get("coverage", 0.0)

    # contradiction handling: share of verified evidence that is not contradictory
    total_ev = max(1, len(evidence))
    contra = sum(
        1
        for h in hypotheses
        for eid in h.contradiction_ids
        if any(e.evidence_id == eid for e in evidence)
    )
    contradiction_handling = max(0.0, 1.0 - (contra / total_ev))

    # unsupported claim rate: share of chain links without a graph edge
    unsupported = chain_score_detail.get("unsupported_links", 0)
    links = max(1, chain_score_detail.get("chain_links", 1))
    unsupported_rate = unsupported / links

    return {
        "root_cause_accuracy": root_cause,
        "fault_localization_accuracy": fault_loc,
        "causal_chain_accuracy": chain_acc,
        "evidence_coverage": coverage,
        "temporal_ordering_accuracy": temporal,
        "contradiction_handling": contradiction_handling,
        "unsupported_claim_rate": round(unsupported_rate, 4),
        "runtime_seconds": round(runtime_seconds, 4),
        "evidence_weight": config.w_evidence,
        "consistency_weight": config.w_edge_conf,
        "coverage_weight": config.w_explained,
        "contradiction_penalty": config.penalty_contradiction,
    }


def _chain_score_detail(hypothesis, graph, observations) -> dict[str, Any]:
    if hypothesis is None:
        return {"coverage": 0.0, "unsupported_links": 0, "chain_links": 0}
    explained = set()
    chain_text = " ".join(hypothesis.causal_chain).lower()
    for o in observations:
        if o.subsystem.lower() in chain_text or o.observation_id in chain_text:
            explained.add(o.observation_id)
    coverage = len(explained) / max(1, len(observations))
    edge_map = {(e.source, e.target): e for e in graph.edges}
    unsupported = 0
    links = max(1, len(hypothesis.causal_chain) - 1)
    for i in range(len(hypothesis.causal_chain) - 1):
        if edge_map.get((hypothesis.causal_chain[i], hypothesis.causal_chain[i + 1])) is None:
            unsupported += 1
    return {"coverage": coverage, "unsupported_links": unsupported, "chain_links": links}


def _run_with_llm(scenario_id, llm, config):
    inputs = load_investigation_inputs(f"configs/scenarios/{scenario_id}.yaml")
    specs = load_subsystem_specs("configs/subsystems")
    graph = build_graph(
        extract_observations(inputs),
        inputs.events,
        inputs.telemetry,
        specs,
    )
    observations = extract_observations(inputs)
    start = time.perf_counter()
    hypotheses, evidence = None, []
    if llm is not None:
        from autopsy.agents.orchestrator import AgentConfig, generate_hypotheses

        hypotheses, evidence = generate_hypotheses(
            graph, observations, inputs.events, specs, llm, config=AgentConfig(), progress=None
        )
    scored = score_hypotheses(
        hypotheses or [], evidence, graph, observations, config=config, events=inputs.events
    )
    elapsed = time.perf_counter() - start
    return scored, elapsed, graph, observations, inputs.events


def _earliest_anomaly(scenario_id, graph, observations, events):
    if not observations:
        return [], []
    earliest = min(observations, key=lambda o: o.timestamp)
    from autopsy.schemas.hypotheses import Hypothesis

    hyp = Hypothesis(
        hypothesis_id="base_earliest_00",
        title="Earliest anomaly baseline",
        summary=f"Blame the subsystem of the earliest observation ({earliest.subsystem}).",
        causal_chain=[f"{earliest.subsystem}:{earliest.observation_id}"],
        evidence_ids=[earliest.observation_id],
        contradiction_ids=[],
        assumptions=["Earliest abnormal observation is the root cause."],
        confidence=0.5,
        score=0.0,
    )
    return [hyp], []


def _single_llm(scenario_id, llm, specs, config):
    inputs = load_investigation_inputs(f"configs/scenarios/{scenario_id}.yaml")
    observations = extract_observations(inputs)
    summary = (
        f"Scenario {scenario_id}. "
        f"{len(observations)} observations. "
        f"Earliest: {observations[0].observation_id if observations else 'none'} "
        f"at {_iso(observations[0].timestamp) if observations else ''}."
    )
    out = complete_json(
        model=ModelName.REASONING,
        system="You are a root-cause analyst. Propose hypotheses.",
        user=summary,
        response_model=ProposerOutput,
        config=LLMConfig(fake=True),
    )
    return out.hypotheses, []


def run_evaluation(
    scenarios=None,
    seeds=1,
    fake_llm=True,
    progress=None,
    no_llm_baseline=False,
    mode="fake",
):
    scenarios = scenarios or _discover_scenarios()
    progress = progress or (lambda s, m, f: None)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    config = ScoringConfig()
    base_cfg = LLMConfig.from_env()
    rows = []
    total = len(scenarios) * seeds * (3 if not no_llm_baseline else 1)
    i = 0

    for sid in scenarios:
        ground_truth = None
        gt_path = GROUND_TRUTH_DIR / f"{sid}_ground_truth.json"
        if gt_path.exists():
            ground_truth = load_ground_truth(gt_path)
        inputs = load_investigation_inputs(f"configs/scenarios/{sid}.yaml")
        specs = load_subsystem_specs("configs/subsystems")
        observations = extract_observations(inputs)
        graph = build_graph(
            observations, inputs.events, inputs.telemetry, specs
        )
        events = inputs.events

        variants = [("pipeline", True)]
        if not no_llm_baseline:
            variants += [("earliest_anomaly", False), ("single_llm", True), ("no_spec", True)]

        for name, use_llm in variants:
            for seed in range(seeds):
                i += 1
                progress("eval", f"{sid}/{name} seed {seed}", i / total)
                if use_llm:
                    if fake_llm:
                        llm_cfg = LLMConfig(
                            api_key=None,
                            fake=True,
                            cache_dir=base_cfg.cache_dir,
                            requests_per_minute=base_cfg.requests_per_minute,
                            tokens_per_minute=base_cfg.tokens_per_minute,
                            tokens_per_day=base_cfg.tokens_per_day,
                        )
                    else:
                        llm_cfg = base_cfg  # from_env already reads GROQ_API_KEY
                    llm = LLMClient(llm_cfg)
                else:
                    llm = None
                try:
                    if name == "pipeline" or name == "no_spec":
                        scored, elapsed, g, obs, evs = _run_with_llm(
                            sid, llm, config
                        )
                    elif name == "earliest_anomaly":
                        hyps, evs = _earliest_anomaly(sid, graph, observations, events)
                        scored = score_hypotheses(
                            hyps, evs, graph, observations, config=config, events=events
                        )
                        elapsed = 0.0
                        g = graph
                    elif name == "single_llm":
                        hyps, evs = _single_llm(sid, llm, specs, config)
                        scored = score_hypotheses(
                            hyps, evs, graph, observations, config=config, events=events
                        )
                        elapsed = 0.0
                        g = graph
                    else:
                        continue
                except Exception as exc:
                    rows.append({
                        "scenario": sid, "variant": name, "seed": seed,
                        "status": "error", "error": str(exc),
                    })
                    continue

                leading = scored.hypotheses[0] if scored.hypotheses else None
                detail = _chain_score_detail(leading, g, observations)
                metrics = compute_metrics(
                    sid,
                    scored.hypotheses,
                    scored.evidence,
                    ground_truth,
                    observations,
                    events,
                    config,
                    elapsed,
                    detail,
                )
                rows.append({
                    "scenario": sid, "variant": name, "seed": seed,
                    "status": "completed", "metrics": metrics,
                    "num_hypotheses": len(scored.hypotheses),
                })

    out = EVAL_DIR / "partial.json"
    out.write_text(json.dumps(rows, indent=2))
    aggregates = _aggregate(rows)
    report = {
        "mode": mode,
        "rows": rows,
        "aggregates": aggregates,
    }
    results_path = EVAL_DIR / f"results.{mode}.json"
    results_path.write_text(json.dumps(report, indent=2))
    return report


def _aggregate(rows):
    by_scenario_variant = {}
    for r in rows:
        if r.get("status") != "completed":
            continue
        key = (r["scenario"], r["variant"])
        by_scenario_variant.setdefault(key, []).append(r["metrics"])
    out = {}
    for key, metric_list in by_scenario_variant.items():
        agg = {}
        for k in METRIC_KEYS:
            vals = [m[k] for m in metric_list if k in m]
            agg[k] = round(sum(vals) / len(vals), 4) if vals else 0.0
        out[f"{key[0]}::{key[1]}"] = agg
    return out


def _discover_scenarios():
    return sorted(p.stem for p in Path("configs/scenarios").glob("*.yaml"))


def print_table(report):
    print(
        f"{'scenario':<22} {'variant':<18} {'root_cause':<10} {'fault_loc':<10} {'chain_acc':<10} "
        f"{'cov':<8} {'temp':<8} {'unsupported':<12} {'runtime':<8}"
    )
    for r in report["rows"]:
        if r.get("status") != "completed":
            continue
        m = r["metrics"]
        print(
            f"{r['scenario']:<22} {r['variant']:<18} {m['root_cause_accuracy']:<10.2f} "
            f"{m['fault_localization_accuracy']:<10.2f} {m['causal_chain_accuracy']:<10.2f} "
            f"{m['evidence_coverage']:<8.2f} {m['temporal_ordering_accuracy']:<8.2f} "
            f"{m['unsupported_claim_rate']:<12.4f} {m['runtime_seconds']:<8.4f}"
        )


def main():
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
