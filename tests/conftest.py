"""Shared pytest fixtures.

Each test gets an isolated SQLite database and a fresh application instance so
tests never touch the developer's ``data/`` directory.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.settings import Settings


@pytest.fixture()
def client(tmp_path: Path) -> Iterator[TestClient]:
    """Return a TestClient backed by a temporary SQLite database."""
    settings = Settings(
        _env_file=None,
        app_name="Mission Autopsy API",
        environment="test",
        database_path=tmp_path / "mission_autopsy_test.db",
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client
