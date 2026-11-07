"""YAML scenario definitions for fault injection.

Scenarios live as package data under ``sim/scenarios/`` so runs are reproducible
without external files. A scenario declares the fault, the ground-truth causal
chain (and therefore the exact effect timings the simulator applies), one benign
distractor, and the command/alarm log.
"""

from __future__ import annotations

from importlib import resources
from importlib.resources.abc import Traversable
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from prometheus.contracts import Subsystem
from prometheus.sim.channels import channel_keys


class ScenarioError(ValueError):
    """Raised when a scenario cannot be found or parsed."""


class FaultConfig(BaseModel):
    """The injected fault, its window and per-scenario magnitude parameters."""

    type: str
    start_s: float = Field(gt=0)
    ramp_s: float = Field(default=600.0, ge=0)
    end_s: float | None = None
    params: dict[str, float] = Field(default_factory=dict)


class ChainStep(BaseModel):
    """One ordered step of the true causal chain."""

    order: int = Field(ge=1)
    subsystem: Subsystem
    channel: str
    direction: Literal["up", "down"]
    onset_offset_s: float = Field(ge=0)
    ramp_s: float = Field(default=180.0, ge=1)
    expected_delta: float
    mechanism: str

    @model_validator(mode="after")
    def _direction_matches_delta(self) -> ChainStep:
        if self.direction == "up" and self.expected_delta <= 0:
            raise ValueError("direction 'up' requires a positive expected_delta")
        if self.direction == "down" and self.expected_delta >= 0:
            raise ValueError("direction 'down' requires a negative expected_delta")
        return self


class DistractorConfig(BaseModel):
    """A benign transient that is explicitly not part of the causal chain."""

    type: str
    start_s: float = Field(ge=0)
    duration_s: float = Field(gt=0)
    subsystem: Subsystem
    channel: str
    magnitude: float
    description: str


class EventSpec(BaseModel):
    """A command or alarm written to ``events.csv``."""

    at_s: float = Field(ge=0)
    kind: Literal["command", "alarm"]
    subsystem: Subsystem
    severity: Literal["info", "warning", "critical"]
    code: str
    message: str


class Scenario(BaseModel):
    """A complete, validated injection scenario."""

    name: str
    title: str
    description: str
    duration_s: float = Field(default=21_600.0, gt=0)
    time_origin_utc: str = "2026-03-14T00:00:00+00:00"
    fault: FaultConfig
    chain: list[ChainStep]
    distractor: DistractorConfig
    events: list[EventSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_ordering_and_channels(self) -> Scenario:
        known = channel_keys()
        for step in self.chain:
            if (step.subsystem, step.channel) not in known:
                raise ValueError(f"unknown chain channel {step.subsystem}/{step.channel}")
        if not self.chain:
            raise ValueError("scenario needs at least one chain step")
        orders = [step.order for step in self.chain]
        if orders != list(range(1, len(self.chain) + 1)):
            raise ValueError("chain order must be 1..N in list order")
        onsets = [step.onset_offset_s for step in self.chain]
        if onsets != sorted(onsets):
            raise ValueError("chain onsets must be non-decreasing")
        if self.fault.start_s + onsets[-1] >= self.duration_s:
            raise ValueError("last chain onset must fall inside the mission")
        distractor_end = self.distractor.start_s + self.distractor.duration_s
        if distractor_end >= self.fault.start_s:
            raise ValueError("distractor must finish before the fault starts")
        if (self.distractor.subsystem, self.distractor.channel) not in known:
            raise ValueError("unknown distractor channel")
        return self


def _scenarios_dir() -> Traversable:
    return resources.files("prometheus.sim").joinpath("scenarios")


def available_scenarios() -> list[str]:
    """Return the scenario names packaged with Prometheus, sorted."""
    return sorted(
        path.name.removesuffix(".yaml")
        for path in _scenarios_dir().iterdir()
        if path.name.endswith(".yaml")
    )


def load_scenario(name: str) -> Scenario:
    """Load and validate a scenario by name.

    Raises:
        ScenarioError: The scenario does not exist or fails validation.
    """
    path = _scenarios_dir().joinpath(f"{name}.yaml")
    if not path.is_file():
        options = ", ".join(available_scenarios())
        raise ScenarioError(f"unknown scenario {name!r}; available: {options}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        scenario = Scenario.model_validate(raw)
    except (yaml.YAMLError, ValueError) as exc:
        raise ScenarioError(f"invalid scenario {name!r}: {exc}") from exc
    if scenario.name != name:
        raise ScenarioError(f"scenario file {name}.yaml declares name {scenario.name!r}")
    return scenario
