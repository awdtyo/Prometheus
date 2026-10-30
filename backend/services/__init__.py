"""Application services that orchestrate investigations.

Routes call services; services call persistence and, once implemented, the
``autopsy`` pipeline. No FastAPI imports belong in this package.
"""

from backend.services.factory import build_investigation_service
from backend.services.interfaces import InvestigationService
from backend.services.mock_service import MockInvestigationService

__all__ = [
    "InvestigationService",
    "MockInvestigationService",
    "build_investigation_service",
]
