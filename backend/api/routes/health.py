"""Liveness endpoint used by developers and the frontend status shell."""

from fastapi import APIRouter

from autopsy import __version__
from backend.dependencies import SettingsDep
from backend.schemas.health import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse, summary="Check API health")
def read_health(settings: SettingsDep) -> HealthResponse:
    """Return liveness and build metadata for the API."""
    return HealthResponse(
        service=settings.app_name,
        version=__version__,
        environment=settings.environment,
    )
