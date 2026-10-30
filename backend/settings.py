"""Runtime configuration for the backend.

Settings are loaded from environment variables (``MISSION_AUTOPSY_`` prefix) and
an optional ``.env`` file at the repository root. Secrets are never committed.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


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
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    log_level: str = "INFO"
    database_path: Path = Path("data/mission_autopsy.db")
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @field_validator("database_path")
    @classmethod
    def _anchor_database_path(cls, value: Path) -> Path:
        """Resolve relative database paths from the repository root."""
        if value.is_absolute():
            return value
        return _REPOSITORY_ROOT / value

    @property
    def cors_origin_list(self) -> list[str]:
        """Return the comma-separated CORS origins as a clean list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
