"""Service contracts that keep routes independent of the domain implementation."""

from collections.abc import Iterator
from typing import Protocol

from backend.schemas.catalog import ScenarioListResponse, SubsystemListResponse
from backend.schemas.investigation import (
    HypothesisListResponse,
    InvestigationCreate,
    InvestigationListResponse,
    InvestigationResponse,
    ProgressEvent,
    TimelineResponse,
)


class InvestigationService(Protocol):
    """Use cases exposed to the investigation HTTP routes."""

    def create(self, payload: InvestigationCreate) -> InvestigationResponse:
        """Create and start an investigation."""
        ...

    def list(self, *, limit: int, cursor: str | None = None) -> InvestigationListResponse:
        """Return a cursor-paginated page of investigations."""
        ...

    def get(self, investigation_id: str) -> InvestigationResponse:
        """Return one investigation or raise ``NotFoundError``."""
        ...

    def hypotheses(self, investigation_id: str) -> HypothesisListResponse:
        """Return ranked hypotheses for an investigation."""
        ...

    def timeline(self, investigation_id: str) -> TimelineResponse:
        """Return the reconstructed timeline for an investigation."""
        ...

    def stream_progress(self, investigation_id: str) -> Iterator[ProgressEvent]:
        """Yield progress events for server-sent event streaming."""
        ...

    def scenarios(self) -> ScenarioListResponse:
        """Return the available scenario catalog."""
        ...

    def subsystems(self) -> SubsystemListResponse:
        """Return the available subsystem catalog."""
        ...
