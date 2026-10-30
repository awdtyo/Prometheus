"""Shared FastAPI dependencies.

Only dependency wiring belongs here. Business logic lives in ``backend.services``.
"""

from typing import Annotated, cast

from fastapi import Depends, Request

from backend.settings import Settings


def get_app_settings(request: Request) -> Settings:
    """Read the settings instance attached to the running application."""
    return cast(Settings, request.app.state.settings)


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
