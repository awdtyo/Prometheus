from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from autopsy.pipeline import run_scenario
from autopsy.llm.client import LLMClient
from autopsy.llm.config import LLMConfig


def run_evaluation(scenarios=None, seeds=1, fake_llm=True, progress=None):
    scenarios = scenarios or ["battery_failure"]
    progress = progress or (lambda s, m, f: None)
    rows = []
    total = len(scenarios) * seeds
    i = 0
    for sid in scenarios:
        for seed in range(seeds):
            i += 1
            progress("eval", f"{sid} seed {seed}", i / total)
            llm = LLMClient(LLMConfig(fake=fake_llm))
            try:
                rr = run_scenario(sid, llm=llm)
                metrics = rr.evaluation_metrics or {}
                rows.append({"scenario": sid, "seed": seed, "status": rr.status.value, "metrics": metrics, "num_hypotheses": len(rr.hypotheses)})
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
