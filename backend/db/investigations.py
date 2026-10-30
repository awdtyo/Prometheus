"""SQLite queries for investigation metadata and cursor pagination."""

import base64
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from backend.db.database import connect

_SELECT_COLUMNS = """
    id, scenario_id, title, description, fault_type, status, progress,
    current_stage, error_message, created_at, updated_at, completed_at
"""


@dataclass(frozen=True)
class InvestigationRecord:
    """Persistence representation of one investigation."""

    id: str
    scenario_id: str
    title: str
    description: str | None
    fault_type: str | None
    status: str
    progress: int
    current_stage: str | None
    error_message: str | None
    created_at: str
    updated_at: str
    completed_at: str | None


@dataclass(frozen=True)
class InvestigationCursor:
    """Keyset pagination cursor for the investigation list."""

    created_at: str
    id: str


def _row_to_record(row: sqlite3.Row) -> InvestigationRecord:
    return InvestigationRecord(
        id=str(row["id"]),
        scenario_id=str(row["scenario_id"]),
        title=str(row["title"]),
        description=row["description"],
        fault_type=row["fault_type"],
        status=str(row["status"]),
        progress=int(row["progress"]),
        current_stage=row["current_stage"],
        error_message=row["error_message"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        completed_at=row["completed_at"],
    )


def insert_investigation(database_path: Path, record: InvestigationRecord) -> None:
    """Insert one investigation record."""
    with connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO investigations (
                id, scenario_id, title, description, fault_type, status, progress,
                current_stage, error_message, created_at, updated_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.scenario_id,
                record.title,
                record.description,
                record.fault_type,
                record.status,
                record.progress,
                record.current_stage,
                record.error_message,
                record.created_at,
                record.updated_at,
                record.completed_at,
            ),
        )


def get_investigation(database_path: Path, investigation_id: str) -> InvestigationRecord | None:
    """Return one investigation by ID, or ``None`` when it does not exist."""
    with connect(database_path) as connection:
        row = connection.execute(
            f"SELECT {_SELECT_COLUMNS} FROM investigations WHERE id = ?",
            (investigation_id,),
        ).fetchone()
    return _row_to_record(row) if row is not None else None


def list_investigations(
    database_path: Path,
    *,
    limit: int,
    cursor: InvestigationCursor | None = None,
) -> tuple[list[InvestigationRecord], bool]:
    """Return a page of investigations and whether another page exists."""
    with connect(database_path) as connection:
        if cursor is None:
            rows = connection.execute(
                f"""
                SELECT {_SELECT_COLUMNS}
                FROM investigations
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit + 1,),
            ).fetchall()
        else:
            rows = connection.execute(
                f"""
                SELECT {_SELECT_COLUMNS}
                FROM investigations
                WHERE created_at < ? OR (created_at = ? AND id < ?)
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (cursor.created_at, cursor.created_at, cursor.id, limit + 1),
            ).fetchall()

    has_more = len(rows) > limit
    return [_row_to_record(row) for row in rows[:limit]], has_more


def update_investigation_status(
    database_path: Path,
    investigation_id: str,
    *,
    status: str,
    progress: int,
    current_stage: str | None,
    updated_at: str,
    error_message: str | None = None,
    completed_at: str | None = None,
) -> None:
    """Update lifecycle fields for one investigation."""
    with connect(database_path) as connection:
        connection.execute(
            """
            UPDATE investigations
            SET status = ?, progress = ?, current_stage = ?, error_message = ?,
                updated_at = ?, completed_at = ?
            WHERE id = ?
            """,
            (
                status,
                progress,
                current_stage,
                error_message,
                updated_at,
                completed_at,
                investigation_id,
            ),
        )


def encode_cursor(record: InvestigationRecord) -> str:
    """Encode the last record of a page as an opaque cursor."""
    payload = json.dumps(
        {"created_at": record.created_at, "id": record.id},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


def decode_cursor(value: str) -> InvestigationCursor:
    """Decode an opaque cursor, raising ``ValueError`` when it is malformed."""
    try:
        raw = base64.urlsafe_b64decode(value.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
        created_at = payload["created_at"]
        identifier = payload["id"]
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise ValueError("invalid pagination cursor") from exc
    if not isinstance(created_at, str) or not isinstance(identifier, str):
        raise ValueError("invalid pagination cursor")
    return InvestigationCursor(created_at=created_at, id=identifier)
