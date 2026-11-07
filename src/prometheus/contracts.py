"""Cross-stage data contracts.

Every structure that crosses a pipeline stage boundary is a pydantic model
defined here. Contracts grow phase by phase; only :class:`Subsystem` exists in
Phase 0.
"""

from enum import StrEnum


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
