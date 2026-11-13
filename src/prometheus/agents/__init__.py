"""Phase 5 hypothesis agents: Proposer, Prosecutor, Skeptic and Judge.

The package exposes the orchestration entry point only; individual agents are
importable from their own modules. Every LLM call goes through
:mod:`prometheus.llm.client`, and every score is computed in code.
"""

from __future__ import annotations

from prometheus.agents.run import (
    InvestigationResult,
    investigate_run,
    write_investigation,
)

__all__ = [
    "InvestigationResult",
    "investigate_run",
    "write_investigation",
]
