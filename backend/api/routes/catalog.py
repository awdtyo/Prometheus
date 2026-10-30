"""Read-only scenario and subsystem catalog endpoints."""

from fastapi import APIRouter

from backend.dependencies import InvestigationServiceDep
from backend.schemas.catalog import ScenarioListResponse, SubsystemListResponse

router = APIRouter(tags=["catalog"])


@router.get("/scenarios", response_model=ScenarioListResponse, summary="List scenarios")
def list_scenarios(service: InvestigationServiceDep) -> ScenarioListResponse:
    """Return the scenarios that can be used to start an investigation."""
    return service.scenarios()


@router.get(
    "/subsystems",
    response_model=SubsystemListResponse,
    summary="List subsystems",
)
def list_subsystems(service: InvestigationServiceDep) -> SubsystemListResponse:
    """Return spacecraft subsystems and their direct dependencies."""
    return service.subsystems()
