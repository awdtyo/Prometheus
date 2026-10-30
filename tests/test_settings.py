"""Configuration and environment-variable tests."""

from pathlib import Path

import pytest

from backend.settings import Settings


def test_settings_read_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MISSION_AUTOPSY_ENVIRONMENT", "production")
    monkeypatch.setenv("MISSION_AUTOPSY_LOG_LEVEL", "debug")
    monkeypatch.setenv("MISSION_AUTOPSY_LOG_FORMAT", "text")
    monkeypatch.setenv("MISSION_AUTOPSY_USE_MOCK_SERVICES", "false")

    settings = Settings(_env_file=None)

    assert settings.environment == "production"
    assert settings.log_level == "DEBUG"
    assert settings.log_format == "text"
    assert settings.use_mock_services is False


def test_settings_normalize_prefix_and_cors() -> None:
    settings = Settings(
        _env_file=None,
        api_prefix="api/v1/",
        cors_origins="http://one.test, http://two.test ,",
    )

    assert settings.api_prefix == "/api/v1"
    assert settings.cors_origin_list == ["http://one.test", "http://two.test"]


def test_relative_database_path_is_anchored_to_repository_root() -> None:
    settings = Settings(_env_file=None, database_path=Path("data/custom.db"))

    assert settings.database_path.is_absolute()
    assert settings.database_path.name == "custom.db"


def test_invalid_log_level_is_rejected() -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, log_level="verbose")
