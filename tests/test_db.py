"""Persistence smoke tests."""

import sqlite3
from pathlib import Path

from backend.db.database import connect, init_db


def test_init_db_creates_investigations_table(tmp_path: Path) -> None:
    database_path = tmp_path / "nested" / "mission_autopsy.db"

    init_db(database_path)

    assert database_path.exists()
    with connect(database_path) as connection:
        tables = {
            row["name"]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }

    assert "investigations" in tables
    assert "runs" in tables


def test_init_db_is_idempotent_and_migrates_old_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "mission_autopsy.db"
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE investigations (
                id TEXT PRIMARY KEY,
                scenario_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT '2026-01-01T00:00:00.000Z',
                updated_at TEXT NOT NULL DEFAULT '2026-01-01T00:00:00.000Z'
            )
            """
        )

    init_db(database_path)
    init_db(database_path)

    with connect(database_path) as connection:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(investigations)").fetchall()
        }

    assert {
        "title",
        "description",
        "fault_type",
        "progress",
        "current_stage",
        "error_message",
        "completed_at",
    } <= columns
