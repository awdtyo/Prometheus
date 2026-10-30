"""SQLite connection helpers and the initial schema.

The backend owns all persistence. Domain payloads remain outside SQLite until the
investigation workflow is implemented; the current schema stores investigation
metadata and mock progress only. SQLite is accessed through the standard library.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS investigations (
    id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    description TEXT,
    fault_type TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    progress INTEGER NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
    current_stage TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_investigations_status
    ON investigations (status);

CREATE INDEX IF NOT EXISTS idx_investigations_created_at
    ON investigations (created_at DESC, id DESC);
"""

_COLUMN_MIGRATIONS: dict[str, str] = {
    "title": "ALTER TABLE investigations ADD COLUMN title TEXT NOT NULL DEFAULT ''",
    "description": "ALTER TABLE investigations ADD COLUMN description TEXT",
    "fault_type": "ALTER TABLE investigations ADD COLUMN fault_type TEXT",
    "progress": ("ALTER TABLE investigations ADD COLUMN progress INTEGER NOT NULL DEFAULT 0"),
    "current_stage": "ALTER TABLE investigations ADD COLUMN current_stage TEXT",
    "error_message": "ALTER TABLE investigations ADD COLUMN error_message TEXT",
    "completed_at": "ALTER TABLE investigations ADD COLUMN completed_at TEXT",
}


@contextmanager
def connect(database_path: Path) -> Iterator[sqlite3.Connection]:
    """Open a SQLite connection, committing on success and closing always."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _apply_column_migrations(connection: sqlite3.Connection) -> None:
    existing = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(investigations)").fetchall()
    }
    for column, statement in _COLUMN_MIGRATIONS.items():
        if column not in existing:
            connection.execute(statement)


def init_db(database_path: Path) -> None:
    """Create the database directory and apply the idempotent schema."""
    with connect(database_path) as connection:
        connection.executescript(_SCHEMA)
        _apply_column_migrations(connection)
