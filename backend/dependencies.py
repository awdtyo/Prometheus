"""Shared FastAPI dependencies.

Only dependency wiring belongs here. Business logic lives in ``backend.services``.
"""

from typing import Annotated, cast

from fastapi import Depends, Request

from backend.db.database import init_db
from backend.exceptions import ServiceUnavailableError
from backend.services.factory import build_investigation_service
from backend.services.interfaces import InvestigationService
from backend.settings import Settings


def get_app_settings(request: Request) -> Settings:
    """Read the settings instance attached to the running application."""
    return cast(Settings, request.app.state.settings)


def get_investigation_service(request: Request) -> InvestigationService:
    """Read the configured investigation service from application state.

    If the caller did not run the application lifespan (for example a bare
    ``TestClient``), initialize SQLite and the service lazily so requests still
    work.
    """
    service = getattr(request.app.state, "investigation_service", None)
    if service is None:
        settings = get_app_settings(request)
        init_db(settings.database_path)
        try:
            service = build_investigation_service(settings)
        except RuntimeError as exc:
            raise ServiceUnavailableError(str(exc)) from exc
        request.app.state.investigation_service = service
    return cast(InvestigationService, service)


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
InvestigationServiceDep = Annotated[InvestigationService, Depends(get_investigation_service)]
