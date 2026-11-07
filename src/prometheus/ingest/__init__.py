"""Ingest and normalize synthetic mission data.

Public entry point: :func:`ingest_run`, returning an :class:`IngestedRun` with
raw per-channel series, normalized events, an aligned view and a data-quality
report. Only the mission directory is read; ground truth is never touched.
"""

from prometheus.ingest.errors import IngestError
from prometheus.ingest.run import AlignedView, IngestedRun, ingest_run
from prometheus.ingest.telemetry import NormalizedEvent
from prometheus.ingest.units import UnitConversion, conversion_for

__all__ = [
    "AlignedView",
    "IngestError",
    "IngestedRun",
    "NormalizedEvent",
    "UnitConversion",
    "conversion_for",
    "ingest_run",
]
