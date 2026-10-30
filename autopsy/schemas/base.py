"""Shared primitives for the Mission Autopsy domain contracts.

Every schema in this package inherits from :class:`AutopsyModel`. The base
configuration is deliberately strict: unknown fields are rejected, floating
point values must be finite, and assignments are re-validated.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated, Any, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

# Identifiers are opaque, stable, and unique within their documented scope.
# Recommended format: ``<prefix>_<uuid4hex>`` (for example ``evt_4f...``).
ENTITY_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
SUBSYSTEM_ID_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
PARAMETER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
TYPE_NAME_PATTERN = r"^[a-z][a-z0-9_]*$"


def _normalize_utc(value: datetime) -> datetime:
    """Reject naive datetimes and normalize aware values to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware (UTC or an explicit offset)")
    return value.astimezone(UTC)


def _validate_json_object(value: dict[str, Any]) -> dict[str, Any]:
    """Ensure metadata/parameters can survive a JSON round trip."""
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("value must be a JSON-serializable object") from exc
    return value


def ensure_unique(values: list[str], field_name: str) -> None:
    """Reject duplicate identifiers in a collection."""
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicate values")


# All internal timestamps are UTC. Incoming values may carry any explicit
# offset, but they are converted before validation succeeds.
UtcDatetime = Annotated[datetime, AfterValidator(_normalize_utc)]

EntityId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=ENTITY_ID_PATTERN,
    ),
]
SubsystemId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=SUBSYSTEM_ID_PATTERN,
    ),
]
SourceId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=ENTITY_ID_PATTERN,
    ),
]
ParameterName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=PARAMETER_PATTERN,
    ),
]
TypeName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=TYPE_NAME_PATTERN,
    ),
]
Label = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=512),
]
Description = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4000),
]
Unit = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=32),
]
JsonObject = Annotated[dict[str, Any], AfterValidator(_validate_json_object)]


class AutopsyModel(BaseModel):
    """Base class for every domain contract.

    ``extra="forbid"`` makes accidental contract drift a validation error.
    ``allow_inf_nan=False`` keeps NaN and infinity out of persisted results.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        allow_inf_nan=False,
    )

    def to_json(self, *, indent: int | None = None) -> str:
        """Serialize to a JSON string using enum values and UTC timestamps."""
        return self.model_dump_json(indent=indent)

    @classmethod
    def from_json(cls, payload: str | bytes) -> Self:
        """Deserialize and validate a JSON payload."""
        return cls.model_validate_json(payload)
