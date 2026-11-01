"""End-to-end pipeline tests using the fake LLM."""

from __future__ import annotations

from autopsy.llm.client import FakeLLM, LLMClient, LLMConfig
from autopsy.pipeline import run_scenario
from autopsy.schemas.results import RunResult


def _progress_events():
    events = []

    def cb(stage, message, fraction):
        events.append((stage, message, fraction))

    return cb, events


def test_run_scenario_completes_with_fake_llm():
    cb, events = _progress_events()
    result = run_scenario("battery_failure", llm=LLMClient(LLMConfig(fake=True)), progress=cb)
    assert isinstance(result, RunResult)
    assert result.status.value == "completed"
    assert len(result.hypotheses) >= 3
    scores = [h.score for h in result.hypotheses]
    assert scores == sorted(scores, reverse=True)
    assert all(0.0 <= s <= 1.0 for s in scores)
    # progress is monotonic and ends at 1.0
    fractions = [e[2] for e in events]
    assert fractions == sorted(fractions)
    assert fractions and fractions[-1] == 1.0
    # stage order matches the pipeline
    stages = [e[0] for e in events]
    assert "ingesting" in stages
    assert "graphing" in stages
    assert "completed" in stages


def test_hypotheses_have_claims_and_scores():
    result = run_scenario("battery_failure", llm=LLMClient(LLMConfig(fake=True)))
    for h in result.hypotheses:
        assert 0.0 <= h.score <= 1.0
        assert 0.0 <= h.confidence <= 1.0


def test_fake_llm_all_agent_models_validate():
    from autopsy.agents.models import (
        LabelledClaim,
        ProposerOutput,
        ProsecutorOutput,
        SkepticOutput,
    )
    from autopsy.schemas.evidence import Evidence
    from autopsy.schemas.hypotheses import Hypothesis

    models = [ProposerOutput, Hypothesis, Evidence, LabelledClaim, ProsecutorOutput, SkepticOutput]
    ctx = "NODES:\nobs:obs_001: eps:foo\nevt:evt_001: eps:bar\n"
    fake = FakeLLM()
    for model in models:
        obj = fake.complete("m", "sys", ctx, model, 1024, 0.0)
        assert isinstance(obj, model), f"{model.__name__} did not validate"


def test_demo_run_result_validates_against_schema():
    import json
    from pathlib import Path

    from autopsy.schemas.results import RunResult

    demo_dir = Path("fixtures/demo/battery_failure")
    assert (demo_dir / "run_result.json").exists()
    assert (demo_dir / "progress_events.json").exists()
    data = json.loads((demo_dir / "run_result.json").read_text())
    data.pop("_demo", None)
    result = RunResult.model_validate(data)
    assert result.status.value == "completed"
    assert len(result.hypotheses) >= 3


def test_replay_demo_returns_recorded_run():
    from autopsy.pipeline import replay_demo

    result, events, demo_meta = replay_demo("battery_failure")
    assert result.status.value == "completed"
    assert len(result.hypotheses) >= 3
    assert len(events) >= 1
    stages = [e["stage"] for e in events]
    assert "ingesting" in stages
    assert "completed" in stages
    assert stages.index("ingesting") < stages.index("completed")
    assert "mode" in demo_meta
    assert demo_meta["banner"].startswith("[replay-demo:")
