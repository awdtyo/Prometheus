"""Runtime configuration for the backend.

Settings are loaded from environment variables (``MISSION_AUTOPSY_`` prefix) and
an optional ``.env`` file at the repository root. Secrets are never committed.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

_VALID_LOG_LEVELS = {"CRITICAL", "DEBUG", "ERROR", "INFO", "WARNING"}


class Settings(BaseSettings):
    """Backend configuration with safe local defaults."""

    model_config = SettingsConfigDict(
        env_prefix="MISSION_AUTOPSY_",
        env_file=_REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )

    app_name: str = "Mission Autopsy API"
    environment: Literal["development", "test", "production"] = "development"
    api_prefix: str = "/api"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"
    database_path: Path = Path("data/mission_autopsy.db")
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    use_mock_services: bool = True
    mock_stream_delay_seconds: float = Field(default=0.0, ge=0.0, le=5.0)

    @field_validator("database_path")
    @classmethod
    def _anchor_database_path(cls, value: Path) -> Path:
        """Resolve relative database paths from the repository root."""
        if value.is_absolute():
            return value
        return _REPOSITORY_ROOT / value

    @field_validator("api_prefix")
    @classmethod
    def _normalize_api_prefix(cls, value: str) -> str:
        """Ensure the API prefix starts with one slash and has no trailing slash."""
        normalized = f"/{value.strip('/')}" if value.strip("/") else ""
        return normalized

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        """Validate and normalize the configured Python log level."""
        normalized = value.strip().upper()
        if normalized not in _VALID_LOG_LEVELS:
            allowed = ", ".join(sorted(_VALID_LOG_LEVELS))
            raise ValueError(f"log_level must be one of: {allowed}")
        return normalized

    @property
    def cors_origin_list(self) -> list[str]:
        """Return the comma-separated CORS origins as a clean list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
