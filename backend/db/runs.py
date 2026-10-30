"""SQLite queries for queued investigation runs."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from backend.db.database import connect

_SELECT_COLUMNS = """
    run_id, scenario_id, status, title, config_json, fault_config_json, message,
    created_at, updated_at, queued_at, started_at, completed_at, error_message
"""


@dataclass(frozen=True)
class RunRecord:
    """Persistence representation of one investigation run."""

    run_id: str
    scenario_id: str
    status: str
    title: str
    config_json: str
    fault_config_json: str | None
    message: str
    created_at: str
    updated_at: str
    queued_at: str
    started_at: str | None
    completed_at: str | None
    error_message: str | None


def _row_to_record(row: sqlite3.Row) -> RunRecord:
    return RunRecord(
        run_id=str(row["run_id"]),
        scenario_id=str(row["scenario_id"]),
        status=str(row["status"]),
        title=str(row["title"]),
        config_json=str(row["config_json"]),
        fault_config_json=row["fault_config_json"],
        message=str(row["message"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        queued_at=str(row["queued_at"]),
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        error_message=row["error_message"],
    )


def insert_run(database_path: Path, record: RunRecord) -> None:
    """Insert one queued run."""
    with connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO runs (
                run_id, scenario_id, status, title, config_json, fault_config_json,
                message, created_at, updated_at, queued_at, started_at, completed_at,
                error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.run_id,
                record.scenario_id,
                record.status,
                record.title,
                record.config_json,
                record.fault_config_json,
                record.message,
                record.created_at,
                record.updated_at,
                record.queued_at,
                record.started_at,
                record.completed_at,
                record.error_message,
            ),
        )


def get_run(database_path: Path, run_id: str) -> RunRecord | None:
    """Return one run by ID, or ``None`` when it does not exist."""
    with connect(database_path) as connection:
        row = connection.execute(
            f"SELECT {_SELECT_COLUMNS} FROM runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    return _row_to_record(row) if row is not None else None
