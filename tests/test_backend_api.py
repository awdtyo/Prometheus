"""API-level tests for the real (autopsy-backed) investigation service.

These use ``AutopsyInvestigationService`` (the real service, not the mock) with
a fake LLM so the run is deterministic and offline-safe. They assert that the
service's hypotheses match what ``python -m autopsy run <scenario> --fake-llm``
produces (same pipeline, same inputs).
"""

from __future__ import annotations

import time

from autopsy.llm.client import LLMClient, LLMConfig
from autopsy.pipeline import run_scenario
from backend.db.database import init_db
from backend.services.autopsy_service import AutopsyInvestigationService
from backend.settings import Settings


def _service(tmp_path):
    settings = Settings(database_path=tmp_path / "service.db")
    init_db(settings.database_path)
    return AutopsyInvestigationService(
        settings.database_path,
        llm=LLMClient(LLMConfig(fake=True)),
    )


def test_real_service_fake_llm_matches_cli(tmp_path):
    svc = _service(tmp_path)

    from backend.schemas.investigation import InvestigationCreate

    created = svc.create(
        InvestigationCreate(
            scenario_id="battery_failure", title="t", fault_type="power_degradation"
        )
    )
    inv_id = created.id

    # Poll until the background pipeline thread finishes.
    completed = None
    for _ in range(100):
        got = svc.get(inv_id)
        if got.status.value in ("completed", "failed"):
            completed = got
            break
        time.sleep(0.1)
    assert completed is not None
    assert completed.status.value == "completed"
    assert completed.progress == 100

    hyps = svc.hypotheses(inv_id).hypotheses
    assert len(hyps) == 3

    # The same pipeline via the CLI entry point produces identical ids/scores.
    cli = run_scenario("battery_failure", llm=LLMClient(LLMConfig(fake=True)))
    cli_hyps = sorted(cli.hypotheses, key=lambda h: h.score, reverse=True)
    assert len(cli_hyps) == len(hyps)
    for svc_h, cli_h in zip(hyps, cli_hyps, strict=False):
        assert svc_h.hypothesis_id == cli_h.hypothesis_id
        assert svc_h.score == cli_h.score
        assert svc_h.causal_chain == cli_h.causal_chain

    # Scores must be non-zero and vary across hypotheses (a comparison of two
    # zeros is not a valid equality test).
    scores = [h.score for h in hyps]
    assert all(s > 0.0 for s in scores), f"scores must be non-zero, got {scores}"
    assert len({round(s, 4) for s in scores}) > 1, f"scores must vary, got {scores}"


def test_real_service_stream_progress_emits_events(tmp_path):
    svc = _service(tmp_path)
    from backend.schemas.investigation import InvestigationCreate

    created = svc.create(
        InvestigationCreate(
            scenario_id="battery_failure", title="t", fault_type="power_degradation"
        )
    )
    inv_id = created.id

    # Wait for completion so the progress buffer is fully populated.
    for _ in range(100):
        got = svc.get(inv_id)
        if got.status.value in ("completed", "failed"):
            break
        time.sleep(0.1)

    events = list(svc.stream_progress(inv_id))
    assert len(events) >= 1
    assert events[0].stage == "ingesting"
    assert any(e.stage == "completed" for e in events)
    assert events[-1].stage == "completed"
    assert events[-1].progress == 100
