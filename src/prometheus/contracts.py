"""Cross-stage data contracts.

Every structure that crosses a pipeline stage boundary is a pydantic model
defined here. Phase 0 defined :class:`Subsystem`; Phase 2 adds the spec models
(:class:`Channel`, :class:`SubsystemSpec`, :class:`Dependency`, :class:`Spec`).
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
