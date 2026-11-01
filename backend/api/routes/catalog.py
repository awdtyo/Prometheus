"""Scenario, subsystem, evaluation, and demo catalog endpoints."""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from backend.dependencies import InvestigationServiceDep
from backend.schemas.catalog import (
    FaultConfig,
    ScenarioDetailResponse,
    ScenarioInjectionResponse,
    ScenarioListResponse,
    SubsystemListResponse,
)

EVAL_DIR = Path("data/eval")
DEMO_DIR = Path("fixtures/demo")

router = APIRouter(tags=["catalog"])


@router.get("/scenarios", response_model=ScenarioListResponse, summary="List scenarios")
def list_scenarios(service: InvestigationServiceDep) -> ScenarioListResponse:
    """Return the scenarios that can be used to start an investigation."""
    return service.scenarios()


@router.get(
    "/scenarios/{scenario_id}",
    response_model=ScenarioDetailResponse,
    summary="Get a scenario",
)
def get_scenario(scenario_id: str, service: InvestigationServiceDep) -> ScenarioDetailResponse:
    """Return the complete configuration for one scenario."""
    return service.get_scenario(scenario_id)


@router.post(
    "/scenarios/{scenario_id}/inject",
    response_model=ScenarioInjectionResponse,
    summary="Preview a fault injection",
)
def inject_fault(
    scenario_id: str,
    fault_config: FaultConfig,
    service: InvestigationServiceDep,
) -> ScenarioInjectionResponse:
    """Validate and preview a fault without modifying the scenario fixture."""
    return service.inject_fault(scenario_id, fault_config)


@router.get(
    "/subsystems",
    response_model=SubsystemListResponse,
    summary="List subsystems",
)
def list_subsystems(service: InvestigationServiceDep) -> SubsystemListResponse:
    """Return spacecraft subsystems and their direct dependencies."""
    return service.subsystems()


@router.get(
    "/evaluation/{scenario_id}",
    response_model=dict[str, float],
    summary="Evaluation metrics for a scenario",
)
def get_evaluation(
    scenario_id: str,
    mode: str = Query(default="fake", pattern="^(fake|real)$"),
) -> dict[str, float]:
    """Return saved evaluation metrics for a scenario, labelled by LLM mode."""
    path = EVAL_DIR / f"results.{mode}.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    for row in data.get("rows", []):
        if row.get("scenario") == scenario_id and row.get("status") == "completed":
            return row.get("metrics", {})
    return {}


@router.get(
    "/demo/{scenario_id}",
    summary="Replay a recorded demo run",
)
def get_demo(scenario_id: str):
    """Return a recorded demo run result plus ordered progress events."""
    demo_dir = DEMO_DIR / scenario_id
    run_path = demo_dir / "run_result.json"
    events_path = demo_dir / "progress_events.json"
    if not run_path.exists():
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="No recorded demo for scenario")
    run_result = json.loads(run_path.read_text())
    events = []
    if events_path.exists():
        events = json.loads(events_path.read_text())
    return {"run_result": run_result, "progress_events": events}
