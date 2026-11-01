from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from autopsy.agents.orchestrator import generate_hypotheses
from autopsy.analysis.scoring import score_hypotheses
from autopsy.graph.builder import build_graph
from autopsy.ingest.loaders import load_investigation_inputs
from autopsy.llm.client import LLMClient
from autopsy.observations.extractor import extract_observations
from autopsy.schemas.enums import RunStatus
from autopsy.schemas.results import RunResult, RunTimestamps


class PipelineError(Exception):
    def __init__(self, stage: str, message: str):
        self.stage = stage
        super().__init__(f"[{stage}] {message}")


ProgressCb = Callable[[str, str, float], None]


def run_investigation(inputs, config=None, llm=None, progress=None, use_cache=True):
    config = config
    progress = progress or (lambda s, m, f: None)
    created = datetime.now(UTC)
    run_id = str(uuid.uuid4())
    scenario_id = getattr(inputs, "scenario_id", "unknown")

    def emit(stage, msg, frac):
        progress(stage, msg, frac)

    # Stage 1: ingest
    emit("ingesting", "Ingesting inputs", 0.05)
    try:
        observations = extract_observations(inputs)
    except Exception as e:
        raise PipelineError("ingesting", str(e)) from e

    # Stage 2: graph
    emit("graphing", "Building graph", 0.2)
    specs = {}
    try:
        # try load specs from configs if present
        from pathlib import Path
        if Path("configs/subsystems").exists():
            from autopsy.ingest.loaders import load_subsystem_specs
            specs = load_subsystem_specs("configs/subsystems")
    except Exception:
        specs = {}
    try:
        graph = build_graph(observations, inputs.events, inputs.telemetry, specs)
    except Exception as e:
        raise PipelineError("graphing", str(e)) from e

    # Stage 3: agents (LLM)
    emit("analyzing", "Running agents", 0.4)
    hyps = []
    evs = []
    llm_failed = False
    try:
        client = llm if llm is not None else LLMClient()
        hyps, evs = generate_hypotheses(graph, observations, inputs.events, specs, client)
    except Exception as e:
        llm_failed = True
        llm_err = str(e)

    # Stage 4: score (if hypotheses)
    emit("scoring", "Scoring", 0.8)
    if hyps:
        try:
            result_scored = score_hypotheses(hyps, evs, graph, observations, events=inputs.events)
            hyps = result_scored.hypotheses
            evs = result_scored.evidence
        except Exception as e:
            raise PipelineError("scoring", str(e)) from e

    completed = datetime.now(UTC)
    if llm_failed:
        status = RunStatus.FAILED
        # degraded: return graph+observations, hypotheses empty
        rr = RunResult(
            run_id=run_id,
            scenario_id=scenario_id,
            status=status,
            observations=observations,
            graph=graph,
            hypotheses=[],
            timestamps=RunTimestamps(
                created_at=created,
                started_at=created,
                completed_at=completed,
            ),
        )
        # attach warning via investigation_report
        rr.investigation_report = (
            f"LLM stage failed: {llm_err}; degraded result with graph and observations."
        )
        emit(
            "failed", "LLM stage failed; degraded", 1.0
        )
        return rr

    rr = RunResult(
        run_id=run_id,
        scenario_id=scenario_id,
        status=RunStatus.COMPLETED,
        observations=observations,
        graph=graph,
        hypotheses=hyps,
        timestamps=RunTimestamps(created_at=created, started_at=created, completed_at=completed),
    )
    emit("completed", "Complete", 1.0)
    return rr


def run_scenario(scenario_id, config=None, llm=None, progress=None, use_cache=True):
    inputs = load_investigation_inputs(f"configs/scenarios/{scenario_id}.yaml")
    return run_investigation(inputs, config=config, llm=llm, progress=progress, use_cache=use_cache)


def replay_demo(scenario_id: str):
    """Replay a recorded demo run without the LLM (offline-safe)."""
    from autopsy.schemas.results import RunResult

    demo_dir = Path("fixtures/demo") / scenario_id
    run_path = demo_dir / "run_result.json"
    events_path = demo_dir / "progress_events.json"
    if not run_path.exists():
        raise FileNotFoundError(f"No recorded demo run for scenario {scenario_id!r} at {run_path}")
    data = json.loads(run_path.read_text())
    # strip the demo metadata marker before validation
    data.pop("_demo", None)
    result = RunResult.model_validate(data)
    events = []
    if events_path.exists():
        events = json.loads(events_path.read_text())
    return result, events


def main():
    parser = argparse.ArgumentParser(prog="autopsy")
    sub = parser.add_subparsers(dest="cmd")
    runp = sub.add_parser("run")
    runp.add_argument("scenario_id")
    runp.add_argument("--fake-llm", action="store_true")
    runp.add_argument("--no-cache", action="store_true")
    runp.add_argument("--json", dest="json_out", default=None)
    runp.add_argument("--replay-demo", action="store_true")
    args = parser.parse_args()
    if args.cmd != "run":
        parser.print_help()
        sys.exit(1)
    from autopsy.llm.config import LLMConfig
    try:
        if args.replay_demo:
            rr, events = replay_demo(args.scenario_id)
            print(f"Replaying demo for {args.scenario_id} ({len(events)} progress events)")
            for ev in events:
                print(f"  [{ev['fraction']:.0f}%] {ev['stage']}: {ev['message']}")
        else:
            llm = LLMClient(LLMConfig(fake=args.fake_llm))
            rr = run_scenario(args.scenario_id, llm=llm, use_cache=not args.no_cache)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    if args.json_out:
        Path(args.json_out).write_text(rr.model_dump_json(indent=2))
    # readable report
    print(f"Run {rr.run_id} status={rr.status}")
    print(f"Observations: {len(rr.observations)}")
    if rr.hypotheses:
        h = rr.hypotheses[0]
        print(f"Leading: {h.title} (score={h.score:.2f})")
        for step in h.causal_chain:
            print(f"  - {step}")
    print("Alternatives:")
    for h in rr.hypotheses[1:]:
        print(f"  {h.title}: {h.score:.2f} {h.assumptions}")
    sys.exit(0)


if __name__ == "__main__":
    main()
