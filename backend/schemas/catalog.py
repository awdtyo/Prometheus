"""Wire models for scenario and subsystem catalogs."""

from pydantic import Field

from backend.schemas.base import ApiModel


class ScenarioResponse(ApiModel):
    """A scenario that can be used to start an investigation."""

    id: str
    name: str
    description: str
    fault_types: list[str] = Field(default_factory=list)


class ScenarioListResponse(ApiModel):
    """Collection of available scenarios."""

    items: list[ScenarioResponse] = Field(default_factory=list)


class SubsystemResponse(ApiModel):
    """A spacecraft subsystem and its direct dependencies."""

    id: str
    name: str
    description: str
    depends_on: list[str] = Field(default_factory=list)


class SubsystemListResponse(ApiModel):
    """Collection of available subsystems."""

    items: list[SubsystemResponse] = Field(default_factory=list)
