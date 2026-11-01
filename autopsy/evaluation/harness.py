from __future__ import annotations

import json
import time
from pathlib import Path

from autopsy.graph.builder import build_graph
from autopsy.ingest.loaders import (
    load_ground_truth,
    load_investigation_inputs,
    load_subsystem_specs,
)
from autopsy.llm.client import LLMClient
from autopsy.llm.config import LLMConfig
from autopsy.observations.extractor import extract_observations
from autopsy.pipeline import run_scenario


def _subsystem_of_node(node_id, observations, events):
    for o in observations:
        if o.observation_id == node_id:
            return o.subsystem
    for e in events:
        if e.event_id == node_id:
            return e.subsystem
    return None


def _chain_references_subsystem(chain, target, observations, events):
    target = target.lower()
    text = " ".join(chain).lower()
    if target in text:
        return True
    for node in chain:
        sub = _subsystem_of_node(node, observations, events)
        if sub and sub.lower() == target:
            return True
    return False


def _causal_chain_accuracy(leading, ground_truth, observations, events):
    if not ground_truth or not leading or not leading.causal_chain:
        return 0.0
    steps = getattr(ground_truth, "expected_causal_sequence", []) or []
    if not steps:
        return 0.0
    recovered = 0
    for step in steps:
        sub = getattr(step, "subsystem", None)
        if sub is None:
            continue
        text = " ".join(leading.causal_chain).lower()
        if sub.lower() in text:
            recovered += 1
            continue
        for node in leading.causal_chain:
            node_sub = _subsystem_of_node(node, observations, events)
            if node_sub and node_sub.lower() == sub.lower():
                recovered += 1
                break
    return recovered / len(steps)


def _temporal_ordering(leading, observations, events):
    if len(leading.causal_chain) < 2:
        return 1.0
    ts_by_id = {}
    for o in observations:
        ts_by_id[o.observation_id] = o.timestamp
    for e in events:
        ts_by_id[e.event_id] = e.timestamp
    times = [ts_by_id.get(n) for n in leading.causal_chain]
    times = [t for t in times if t is not None]
    if len(times) < 2:
        return 1.0
    return 1.0 if all(b >= a for a, b in zip(times, times[1:], strict=False)) else 0.0


def run_evaluation(scenarios=None, seeds=1, fake_llm=True, progress=None):
    scenarios = scenarios or ["battery_failure"]
    progress = progress or (lambda s, m, f: None)
    rows = []
    total = len(scenarios) * seeds
    i = 0
    for sid in scenarios:
        inputs = load_investigation_inputs(f"configs/scenarios/{sid}.yaml")
        specs = load_subsystem_specs("configs/subsystems")
        observations = extract_observations(inputs)
        events = inputs.events
        graph = build_graph(observations, events, inputs.telemetry, specs)
        gt_path = Path("fixtures/expected") / f"{sid}_ground_truth.json"
        ground_truth = load_ground_truth(gt_path) if gt_path.exists() else None
        for seed in range(seeds):
            i += 1
            progress("eval", f"{sid} seed {seed}", i / total)
            config = LLMConfig.from_env()
            if fake_llm:
                config = LLMConfig(
                    api_key=None,
                    fake=True,
                    cache_dir=config.cache_dir,
                    requests_per_minute=config.requests_per_minute,
                    tokens_per_minute=config.tokens_per_minute,
                    tokens_per_day=config.tokens_per_day,
                )
            llm = LLMClient(config)
            try:
                t0 = time.perf_counter()
                rr = run_scenario(sid, llm=llm)
                dt = time.perf_counter() - t0
                leading = rr.hypotheses[0] if rr.hypotheses else None
                target = (
                    ground_truth.injected_fault.target_subsystem if ground_truth else None
                )
                root_cause = 0.0
                fault_loc = 0.0
                if leading is not None and target:
                    if _chain_references_subsystem(
                        leading.causal_chain, target, observations, events
                    ):
                        root_cause = 1.0
                    if any(
                        _chain_references_subsystem(h.causal_chain, target, observations, events)
                        for h in rr.hypotheses
                    ):
                        fault_loc = 1.0
                chain_acc = (
                    _causal_chain_accuracy(leading, ground_truth, observations, events)
                    if leading is not None
                    else 0.0
                )
                if leading is not None:
                    temporal = _temporal_ordering(leading, observations, events)
                else:
                    temporal = 0.0
                explained = set()
                if leading is not None:
                    joined = " ".join(leading.causal_chain)
                    chain_text = joined.lower()
                    for o in observations:
                        sub_match = o.subsystem.lower() in chain_text
                        id_match = o.observation_id in chain_text
                        if sub_match or id_match:
                            explained.add(o.observation_id)
                coverage = len(explained) / max(1, len(observations))
                edge_map = {(e.source, e.target): e for e in graph.edges}
                unsupported = 0
                links = max(1, len(leading.causal_chain) - 1) if leading else 1
                if leading:
                    for i in range(len(leading.causal_chain) - 1):
                        if edge_map.get(
                            (leading.causal_chain[i], leading.causal_chain[i + 1])
                        ) is None:
                            unsupported += 1
                metrics = {
                    "root_cause_accuracy": root_cause,
                    "fault_localization_accuracy": fault_loc,
                    "causal_chain_accuracy": chain_acc,
                    "evidence_coverage": round(coverage, 4),
                    "temporal_ordering_accuracy": temporal,
                    "unsupported_claim_rate": round(unsupported / links, 4),
                    "runtime_seconds": round(dt, 4),
                }
                rows.append(
                    {
                        "scenario": sid,
                        "seed": seed,
                        "status": rr.status.value,
                        "metrics": metrics,
                        "num_hypotheses": len(rr.hypotheses),
                    }
                )
            except Exception as e:
                rows.append({"scenario": sid, "seed": seed, "status": "error", "error": str(e)})
    # partial save
    out = Path("data/eval/partial.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=2))
    return {"rows": rows, "aggregates": {}}


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="autopsy-evaluate")
    ap.add_argument("--scenarios", nargs="*", default=["battery_failure"])
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--no-llm-baseline", action="store_true")
    ap.add_argument("--fake-llm", action="store_true")
    args = ap.parse_args()
    res = run_evaluation(scenarios=args.scenarios, seeds=args.seeds, fake_llm=args.fake_llm)
    print(json.dumps(res, indent=2)[:2000])

if __name__ == "__main__":
    main()
