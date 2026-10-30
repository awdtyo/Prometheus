"""Evidence record contract."""

from pydantic import Field

from autopsy.schemas.base import AutopsyModel, Description, EntityId, UtcDatetime
from autopsy.schemas.enums import EvidenceStance, EvidenceType


class Evidence(AutopsyModel):
    """A citation that supports or contradicts a claim.

    ``source_id`` points at the underlying telemetry record, mission event, or
    observation. ``evidence_id`` is the stable identifier other models use when
    they cite this evidence.
    """

    evidence_id: EntityId = Field(description="Stable unique evidence identifier.")
    source_id: EntityId = Field(description="Stable identifier of the underlying source.")
    timestamp: UtcDatetime = Field(description="Time the evidence refers to, in UTC.")
    evidence_type: EvidenceType = Field(description="Category of the underlying source.")
    description: Description = Field(description="Human-readable evidence statement.")
    supports_or_contradicts: EvidenceStance = Field(
        description="Whether the evidence supports or contradicts the associated claim."
    )
    reliability: float = Field(
        ge=0.0,
        le=1.0,
        description="Reliability of the evidence, from 0.0 to 1.0.",
    )
