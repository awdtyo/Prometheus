"""Cross-stage data contracts.

Every structure that crosses a pipeline stage boundary is a pydantic model
defined here. Phase 0 defined :class:`Subsystem`; Phase 2 adds the spec models
(:class:`Channel`, :class:`SubsystemSpec`, :class:`Dependency`, :class:`Spec`);
Phase 3 adds observations; Phase 4 adds graph edges and the graph document.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class Subsystem(StrEnum):
    """The four subsystems Prometheus reasons about.

    This set is fixed by the project contract: exactly these values, no others.
    """

    POWER = "power"
    THERMAL = "thermal"
    COMMS = "comms"
    ADCS = "adcs"


SUBSYSTEMS: tuple[Subsystem, ...] = tuple(Subsystem)
"""Canonical iteration order for subsystems (power, thermal, comms, adcs)."""


class Channel(BaseModel):
    """One telemetry channel after spec parsing and unit normalization.

    ``name`` is the canonical identifier ``<subsystem>.<source_name>`` used by
    every later stage. ``unit`` is the canonical unit; ``original_unit`` records
    what the source file announced, so conversions stay auditable.
    """

    name: str
    subsystem: Subsystem
    source_name: str
    column: str
    unit: str
    original_unit: str
    nominal_min: float
    nominal_max: float
    description: str = ""

    @model_validator(mode="after")
    def _check(self) -> Channel:
        expected = f"{self.subsystem.value}.{self.source_name}"
        if self.name != expected:
            raise ValueError(f"channel name {self.name!r} must be {expected!r}")
        if self.nominal_max < self.nominal_min:
            raise ValueError(f"{self.name}: nominal_max below nominal_min")
        return self


class SubsystemSpec(BaseModel):
    """Per-subsystem export conventions and channels."""

    subsystem: Subsystem
    file: str
    sample_interval_s: float = Field(gt=0)
    timestamp_column: str
    timestamp_format: str
    channels: list[Channel]

    @model_validator(mode="after")
    def _check(self) -> SubsystemSpec:
        if not self.channels:
            raise ValueError(f"{self.subsystem.value}: no channels declared")
        names = [channel.name for channel in self.channels]
        if len(set(names)) != len(names):
            raise ValueError(f"{self.subsystem.value}: duplicate channel names")
        for channel in self.channels:
            if channel.subsystem is not self.subsystem:
                raise ValueError(
                    f"{channel.name}: subsystem tag does not match {self.subsystem.value}"
                )
        return self


class Dependency(BaseModel):
    """A declared cross-subsystem coupling with a plausible lag window."""

    source: Subsystem
    target: Subsystem
    mechanism: str
    lag_min_s: float = Field(ge=0)
    lag_max_s: float = Field(ge=0)

    @model_validator(mode="after")
    def _check(self) -> Dependency:
        if self.lag_max_s < self.lag_min_s:
            raise ValueError(
                f"{self.source.value}->{self.target.value}: lag window is inverted"
            )
        if self.source is self.target:
            raise ValueError("dependency source and target must differ")
        return self


class Spec(BaseModel):
    """Normalized subsystem specification for one mission run."""

    mission: str
    scenario: str
    seed: int | None = None
    duration_s: float = Field(gt=0)
    time_origin_utc: datetime
    subsystems: dict[Subsystem, SubsystemSpec]
    dependencies: list[Dependency]

    @model_validator(mode="after")
    def _check(self) -> Spec:
        if set(self.subsystems) != set(SUBSYSTEMS):
            raise ValueError("spec must declare exactly power, thermal, comms and adcs")
        for subsystem, layout in self.subsystems.items():
            if layout.subsystem is not subsystem:
                raise ValueError(f"{subsystem.value}: layout key does not match its subsystem")
        return self

    @property
    def channels(self) -> list[Channel]:
        """All channels, in subsystem order."""
        return [
            channel
            for subsystem in SUBSYSTEMS
            for channel in self.subsystems[subsystem].channels
        ]

    @property
    def channel_names(self) -> list[str]:
        """Canonical channel names, in subsystem order."""
        return [channel.name for channel in self.channels]


class ObservationKind(StrEnum):
    """What a discrete observation represents."""

    STEP = "step"
    DRIFT = "drift"
    SPIKE = "spike"
    VARIANCE = "variance"
    EVENT = "event"


class ObservationSource(StrEnum):
    """Where the observation came from."""

    TELEMETRY = "telemetry"
    EVENT = "event"


class Severity(StrEnum):
    """Operator-facing severity, shared by telemetry and log observations."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class Observation(BaseModel):
    """A discrete, citable fact extracted from one mission.

    Telemetry observations cite a canonical channel and a time interval;
    event observations cite the command/alarm log and have no channel. The
    ``id`` is assigned deterministically after detection, so identical inputs
    always produce identical identifiers.
    """

    id: str = Field(pattern=r"^OBS-\d{4,}$")
    subsystem: Subsystem
    channel: str | None = None
    t_start: datetime
    t_end: datetime
    kind: ObservationKind
    magnitude: float
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    source: ObservationSource
    detail: str = ""

    @model_validator(mode="after")
    def _check(self) -> Observation:
        if self.t_end < self.t_start:
            raise ValueError(f"{self.id}: t_end precedes t_start")
        if self.t_start.tzinfo is None or self.t_end.tzinfo is None:
            raise ValueError(f"{self.id}: timestamps must be timezone-aware")
        if self.source is ObservationSource.TELEMETRY:
            if self.kind is ObservationKind.EVENT:
                raise ValueError(f"{self.id}: telemetry observation cannot be an event")
            if not self.channel:
                raise ValueError(f"{self.id}: telemetry observation needs a channel")
        else:
            if self.kind is not ObservationKind.EVENT:
                raise ValueError(f"{self.id}: event source must have kind 'event'")
            if self.channel is not None:
                raise ValueError(f"{self.id}: event observation cannot have a channel")
        return self


class ObservationSet(BaseModel):
    """The observations extracted from one mission run."""

    scenario: str
    seed: int | None = None
    mission: str = ""
    observations: list[Observation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> ObservationSet:
        identifiers = [observation.id for observation in self.observations]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("observation ids must be unique")
        return self


class GraphEdge(BaseModel):
    """One directed candidate causal link between two observations.

    Timing is stored three ways so later stages can audit it: ``onset_lag_s``
    is the difference of observation onsets, ``xcorr_lag_s`` is the
    event-aligned cross-correlation peak, and ``lag_estimate_s`` combines them.
    The range brackets both estimates. ``statistical_support`` and
    ``edge_score`` are computed in code, never set by an LLM.
    """

    id: str = Field(pattern=r"^EDGE-\d{4,}$")
    source: str
    target: str
    spec_support: bool
    mechanism: str = ""
    onset_lag_s: float
    xcorr_lag_s: float | None = None
    lag_estimate_s: float
    lag_min_s: float = Field(ge=0.0)
    lag_max_s: float = Field(ge=0.0)
    correlation: float = Field(ge=-1.0, le=1.0)
    p_value: float = Field(ge=0.0, le=1.0)
    statistical_support: float = Field(ge=0.0, le=1.0)
    lag_agreement: float = Field(ge=0.0, le=1.0)
    confidence_factor: float = Field(default=1.0, ge=0.0, le=1.0)
    edge_score: float = Field(ge=0.0, le=1.0)
    provenance: str = ""

    @model_validator(mode="after")
    def _check(self) -> GraphEdge:
        if self.source == self.target:
            raise ValueError(f"{self.id}: self edge")
        if self.lag_max_s < self.lag_min_s:
            raise ValueError(f"{self.id}: lag range is inverted")
        return self


class GraphDocument(BaseModel):
    """Serializable temporal causal graph for one mission.

    Nodes are :class:`Observation` models and edges carry their own stable
    identifiers. A validator enforces the ordering rule on the serialized form,
    so a hand-edited or corrupt JSON file cannot introduce a backward edge.
    """

    scenario: str
    seed: int | None = None
    mission: str = ""
    nodes: list[Observation] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> GraphDocument:
        node_ids = [node.id for node in self.nodes]
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("graph node ids must be unique")
        by_id = {node.id: node for node in self.nodes}
        edge_ids = [edge.id for edge in self.edges]
        if len(set(edge_ids)) != len(edge_ids):
            raise ValueError("graph edge ids must be unique")
        for edge in self.edges:
            if edge.source not in by_id or edge.target not in by_id:
                raise ValueError(f"{edge.id}: endpoint does not exist")
            if by_id[edge.target].t_start <= by_id[edge.source].t_start:
                raise ValueError(f"{edge.id}: edge violates temporal ordering")
        return self
