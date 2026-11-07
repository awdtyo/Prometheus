"""Synthetic mission generation and fault injection.

Public entry points are :func:`simulate`, :func:`load_scenario`,
:func:`available_scenarios` and :func:`write_run`.
"""

from prometheus.sim.model import Run, simulate
from prometheus.sim.output import WrittenRun, write_run
from prometheus.sim.scenario import (
    Scenario,
    ScenarioError,
    available_scenarios,
    load_scenario,
)

__all__ = [
    "Run",
    "Scenario",
    "ScenarioError",
    "WrittenRun",
    "available_scenarios",
    "load_scenario",
    "simulate",
    "write_run",
]
