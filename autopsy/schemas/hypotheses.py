"""Competing hypothesis contract."""

from pydantic import Field, field_validator

from autopsy.schemas.base import AutopsyModel, Description, EntityId, Label, ensure_unique


class Hypothesis(AutopsyModel):
    """One candidate causal explanation for the observed failure.

    ``confidence`` is the producer's belief in the hypothesis. ``score`` is the
    ranking score assigned by the analysis stage after evidence and contradiction
    weighting, so the two values are intentionally separate.
    """

    hypothesis_id: EntityId = Field(description="Stable unique hypothesis identifier.")
    title: Label = Field(description="Short hypothesis title.")
    summary: Description = Field(description="Concise explanation of the hypothesis.")
    causal_chain: list[Description] = Field(
        min_length=1,
        description="Ordered causal steps, from earliest cause to final effect.",
    )
    evidence_ids: list[EntityId] = Field(
        min_length=1,
        description="Evidence records that support the hypothesis.",
    )
    contradiction_ids: list[EntityId] = Field(
        default_factory=list,
        description="Evidence records that contradict the hypothesis.",
    )
    assumptions: list[Description] = Field(
        default_factory=list,
        description="Assumptions required for the hypothesis to hold.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Producer confidence, from 0.0 to 1.0.",
    )
    score: float = Field(
        ge=0.0,
        le=1.0,
        description="Final ranking score, from 0.0 to 1.0.",
    )

    @field_validator("evidence_ids", "contradiction_ids")
    @classmethod
    def _evidence_ids_are_unique(cls, value: list[str]) -> list[str]:
        ensure_unique(value, "evidence_ids and contradiction_ids")
        return value
