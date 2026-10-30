"""Shared Pydantic configuration and wire-level field types."""

from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, PlainSerializer

from backend.timeutils import parse_iso_z, to_iso_z


def _coerce_utc(value: Any) -> Any:
    if isinstance(value, str):
        value = parse_iso_z(value)
    if not isinstance(value, datetime):
        return value
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


UtcDatetime = Annotated[
    datetime,
    BeforeValidator(_coerce_utc),
    PlainSerializer(to_iso_z, return_type=str, when_used="json"),
]


class ApiModel(BaseModel):
    """Base class for public request and response DTOs."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
