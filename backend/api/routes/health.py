"""Liveness endpoint used by developers and the frontend status shell."""

from fastapi import APIRouter

from backend.dependencies import SettingsDep
from backend.schemas.health import HealthResponse
from backend.version import get_core_version

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse, summary="Check API health")
def read_health(settings: SettingsDep) -> HealthResponse:
    """Return liveness and build metadata for the API."""
    return HealthResponse(
        service=settings.app_name,
        version=get_core_version(),
        environment=settings.environment,
    )
