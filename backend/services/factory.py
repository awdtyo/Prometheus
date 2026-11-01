import os

from backend.settings import get_settings


def build_investigation_service(settings=None):
    """Build the configured investigation service.

    Mock mode is the default and is used by every test; the real autopsy-backed
    service is selected with ``MISSION_AUTOPSY_USE_MOCK_SERVICES=false``.
    """
    if settings is None:
        settings = get_settings()
    use_mock = os.getenv("MISSION_AUTOPSY_USE_MOCK_SERVICES", "true").lower() == "true"
    if use_mock:
        from backend.services.mock_service import MockInvestigationService

        return MockInvestigationService(settings.database_path)
    from autopsy.llm.client import LLMClient
    from autopsy.llm.config import LLMConfig
    from backend.services.autopsy_service import AutopsyInvestigationService

    fake = os.getenv("MISSION_AUTOPSY_FAKE_LLM", "false").lower() == "true"
    return AutopsyInvestigationService(llm=LLMClient(LLMConfig(fake=fake)))


def create_service():
    """Thin alias kept for backwards compatibility."""
    return build_investigation_service(None)
