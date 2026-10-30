"""Investigation run endpoints."""

from fastapi import APIRouter, status

from backend.dependencies import InvestigationServiceDep
from backend.schemas.run import RunCreate, RunResponse

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post(
    "",
    response_model=RunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create and queue an investigation run",
)
def create_run(payload: RunCreate, service: InvestigationServiceDep) -> RunResponse:
    """Validate the run configuration and enqueue it for the mock worker."""
    return service.create_run(payload)
