from __future__ import annotations

from pydantic import BaseModel, Field

from autopsy.schemas.evidence import Evidence
from autopsy.schemas.hypotheses import Hypothesis


class ProposerOutput(BaseModel):
    hypotheses: list[Hypothesis] = Field(min_length=3, max_length=4)


class LabelledClaim(BaseModel):
    text: str
    label: str  # evidence | inference | speculation


class ProsecutorOutput(BaseModel):
    evidence: list[Evidence] = Field(default_factory=list)
    claims: list[LabelledClaim] = Field(default_factory=list)


class SkepticOutput(BaseModel):
    evidence: list[Evidence] = Field(default_factory=list)


class AgentError(Exception):
    pass
