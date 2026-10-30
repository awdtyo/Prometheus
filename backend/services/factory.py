"""Select the service implementation used by the running application."""

from backend.services.interfaces import InvestigationService
from backend.services.mock_service import MockInvestigationService
from backend.settings import Settings


def build_investigation_service(settings: Settings) -> InvestigationService:
    """Return the configured investigation service.

    Only the mock implementation exists today. When the independent ``autopsy``
    package exposes an investigation pipeline, add its adapter here and select it
    with ``MISSION_AUTOPSY_USE_MOCK_SERVICES=false``.
    """
    if settings.use_mock_services:
        return MockInvestigationService(settings.database_path)

    raise RuntimeError(
        "The autopsy investigation adapter is not implemented yet. "
        "Set MISSION_AUTOPSY_USE_MOCK_SERVICES=true to run the mock service."
    )
