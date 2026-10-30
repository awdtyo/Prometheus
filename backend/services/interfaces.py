"""Service contracts that keep routes independent of the domain implementation."""

from collections.abc import Iterator
from typing import Protocol

from backend.schemas.catalog import (
    FaultConfig,
    ScenarioDetailResponse,
    ScenarioInjectionResponse,
    ScenarioListResponse,
    SubsystemListResponse,
)
from backend.schemas.investigation import (
    HypothesisListResponse,
    InvestigationCreate,
    InvestigationListResponse,
    InvestigationResponse,
    ProgressEvent,
    TimelineResponse,
)
from backend.schemas.run import RunCreate, RunResponse


class InvestigationService(Protocol):
    """Use cases exposed to the investigation, scenario, and run routes."""

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

    def get_scenario(self, scenario_id: str) -> ScenarioDetailResponse:
        """Return one scenario definition or raise ``NotFoundError``."""
        ...

    def inject_fault(
        self, scenario_id: str, fault_config: FaultConfig
    ) -> ScenarioInjectionResponse:
        """Validate and preview a fault injection without changing the fixture."""
        ...

    def subsystems(self) -> SubsystemListResponse:
        """Return the available subsystem catalog."""
        ...

    def create_run(self, payload: RunCreate) -> RunResponse:
        """Validate, persist, and enqueue an investigation run."""
        ...
