"""Pydantic schemas for the four agents' JSON responses.

These models sit between the LLM and the stable contracts: the client validates
the raw JSON into one of them, the citation validator checks every identifier
against the mission, and only then is a :class:`prometheus.contracts.Hypothesis`
built. Keeping the LLM-facing schemas separate makes the trust boundary clear.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from prometheus.contracts import RootCauseLabel, Subsystem

__all__ = [
    "JudgeNarrativeItem",
    "JudgeNarratives",
    "ProposalBatch",
    "ProposedHypothesis",
    "ProsecutorNarrativeItem",
    "ProsecutorNarratives",
    "SkepticNarrativeItem",
    "SkepticNarratives",
]


class ProposedHypothesis(BaseModel):
    """One raw hypothesis as returned by the Proposer."""

    root_cause: RootCauseLabel
    root_subsystem: Subsystem
    summary: str = Field(min_length=1, max_length=220)
    chain: list[str] = Field(min_length=3, max_length=6)
    edges: list[str] = Field(default_factory=list, max_length=6)
    rationale: str = Field(min_length=1, max_length=600)


class ProposalBatch(BaseModel):
    """The Proposer's complete response: three to six competing hypotheses."""

    hypotheses: list[ProposedHypothesis] = Field(min_length=3, max_length=6)


class ProsecutorNarrativeItem(BaseModel):
    """The Prosecutor's prose for one hypothesis; evidence IDs are code-owned."""

    hypothesis_id: str
    summary: str = Field(min_length=1, max_length=500)


class ProsecutorNarratives(BaseModel):
    """One Prosecutor response covering every hypothesis."""

    items: list[ProsecutorNarrativeItem] = Field(default_factory=list)


class SkepticNarrativeItem(BaseModel):
    """Alternative explanations for one hypothesis.

    Penalties and contradictions are computed by code and are deliberately not
    part of this schema, so the model cannot alter them.
    """

    hypothesis_id: str
    alternatives: list[str] = Field(default_factory=list, max_length=3)
    summary: str = Field(min_length=1, max_length=500)


class SkepticNarratives(BaseModel):
    """One Skeptic response covering every hypothesis."""

    items: list[SkepticNarrativeItem] = Field(default_factory=list)


class JudgeNarrativeItem(BaseModel):
    """The Judge's rationale for one hypothesis; scores are code-owned."""

    hypothesis_id: str
    rationale: str = Field(min_length=1, max_length=600)


class JudgeNarratives(BaseModel):
    """One Judge response covering every ranked hypothesis."""

    items: list[JudgeNarrativeItem] = Field(default_factory=list)
