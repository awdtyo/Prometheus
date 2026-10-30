"""UTC timestamp helpers shared by the HTTP and persistence layers.

The public API always serializes timestamps as ISO 8601 with a ``Z`` suffix and
millisecond precision. SQLite stores the same string representation so records
round-trip without lossy conversions.
"""

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def to_iso_z(value: datetime) -> str:
    """Serialize an aware datetime as UTC ISO 8601 with a ``Z`` suffix."""
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_iso_z(value: str) -> datetime:
    """Parse an ISO 8601 timestamp, accepting both ``Z`` and numeric offsets."""
    normalized = value.strip()
    if normalized.endswith(("Z", "z")):
        normalized = f"{normalized[:-1]}+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a UTC offset")
    return parsed.astimezone(UTC)
