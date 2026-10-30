"""Response model for the health endpoint."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Liveness and build metadata returned by ``GET /api/health``."""

    status: Literal["ok"] = "ok"
    service: str
    version: str
    environment: str
