"""Immutable scenario and subsystem definitions used by the mock backend."""

from backend.scenarios.catalog import (
    SCENARIOS,
    SUBSYSTEMS,
    FaultOptionDefinition,
    ScenarioDefinition,
    SubsystemDefinition,
    TelemetryParameterDefinition,
    get_scenario,
    list_scenarios,
    list_subsystems,
)

__all__ = [
    "SCENARIOS",
    "SUBSYSTEMS",
    "FaultOptionDefinition",
    "ScenarioDefinition",
    "SubsystemDefinition",
    "TelemetryParameterDefinition",
    "get_scenario",
    "list_scenarios",
    "list_subsystems",
]
