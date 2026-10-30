"""Response model for the health endpoint."""

from typing import Literal

from backend.schemas.base import ApiModel


class HealthResponse(ApiModel):
    """Liveness and build metadata returned by ``GET /api/v1/health``."""

    status: Literal["ok"] = "ok"
    service: str
    version: str
    environment: str
