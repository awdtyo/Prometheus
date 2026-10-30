"""Persistence smoke tests."""

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
