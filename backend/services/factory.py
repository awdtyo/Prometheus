"""Application service factory.

Builds the investigation service from the runtime ``Settings``. Mock mode is
the default (and every test); the real autopsy-backed service is selected with
``MISSION_AUTOPSY_USE_MOCK_SERVICES=false``.
"""

from __future__ import annotations

import os

from backend.settings import Settings, get_settings


def build_investigation_service(settings: Settings | None = None):
    """Build the configured investigation service.

    ``settings`` may be ``None``, in which case the process-wide settings are
    used (loaded from environment variables). Mock mode is honored both via
    ``settings.use_mock_services`` and the ``MISSION_AUTOPSY_USE_MOCK_SERVICES``
    environment variable.
    """
    if settings is None:
        settings = get_settings()

    use_mock = settings.use_mock_services
    if os.getenv("MISSION_AUTOPSY_USE_MOCK_SERVICES") is not None:
        use_mock = os.getenv("MISSION_AUTOPSY_USE_MOCK_SERVICES", "true").lower() == "true"

    if use_mock:
        from backend.services.mock_service import MockInvestigationService

        return MockInvestigationService(settings.database_path)

    from autopsy.llm.client import LLMClient, LLMConfig
    from backend.services.autopsy_service import AutopsyInvestigationService

    fake = os.getenv("MISSION_AUTOPSY_FAKE_LLM", "false").lower() == "true"
    return AutopsyInvestigationService(
        database_path=settings.database_path,
        llm=LLMClient(LLMConfig(fake=fake)),
    )


def create_service():
    """Thin alias kept for backwards compatibility."""
    return build_investigation_service(None)
