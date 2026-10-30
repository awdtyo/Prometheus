"""Scenario and subsystem catalog endpoints."""

from fastapi import APIRouter

from backend.dependencies import InvestigationServiceDep
from backend.schemas.catalog import (
    FaultConfig,
    ScenarioDetailResponse,
    ScenarioInjectionResponse,
    ScenarioListResponse,
    SubsystemListResponse,
)

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
