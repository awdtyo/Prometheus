"""Mission Autopsy domain package.

Pure Python domain logic for telemetry ingestion, causal graph construction,
scenario simulation, competing hypothesis generation, and evidence ranking.

This package must remain independent of FastAPI, the backend package, and any
persistence layer. See ``docs/architecture.md`` and
``tests/test_architecture.py``.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
