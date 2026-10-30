"""Minimal job queue abstraction for queued investigation runs.

Only an in-memory implementation exists until the ``autopsy`` worker is wired.
The queue records run IDs and preserves FIFO order; it deliberately contains no
simulation, graph, or agent logic.
"""

from collections.abc import Sequence
from threading import Lock
from typing import Protocol


class JobQueue(Protocol):
    """Queue contract used by the run service."""

    def enqueue(self, run_id: str) -> int:
        """Add a run and return its one-based queue position."""
        ...

    def pending(self) -> Sequence[str]:
        """Return queued run IDs in FIFO order."""
        ...


class InMemoryJobQueue:
    """Thread-safe FIFO queue used by the mock service."""

    def __init__(self) -> None:
        self._run_ids: list[str] = []
        self._lock = Lock()

    def enqueue(self, run_id: str) -> int:
        with self._lock:
            if run_id not in self._run_ids:
                self._run_ids.append(run_id)
            return self._run_ids.index(run_id) + 1

    def pending(self) -> Sequence[str]:
        with self._lock:
            return tuple(self._run_ids)
