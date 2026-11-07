"""Configuration loaded from the environment and from ``.env``.

The only place Prometheus reads secrets or model names. Callers must never
hardcode ``GROQ_API_KEY`` or the model identifiers; they come from here.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

#: Repository root, resolved from this file (``<root>/src/prometheus/config.py``).
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

#: Default data directory, gitignored, holding caches and generated artefacts.
DEFAULT_DATA_DIR: Path = PROJECT_ROOT / "data"

#: Which configured model each hypothesis agent uses.
#: ``main`` is ``GROQ_MODEL``; ``fast`` is ``GROQ_MODEL_FAST`` falling back to main.
_AGENT_MODEL_ROLE: dict[str, str] = {
    "proposer": "main",
    "skeptic": "main",
    "prosecutor": "fast",
    "judge": "fast",
}


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


class Settings(BaseModel):
    """Resolved runtime configuration.

    Instances are produced by :func:`load_settings`; construct them directly
    only in tests.
    """

    groq_api_key: str | None = None
    groq_model: str = ""
    groq_model_fast: str | None = None
    data_dir: Path = Field(default=DEFAULT_DATA_DIR)
    cache_dir: Path = Field(default=DEFAULT_DATA_DIR / "cache")
    tpm_limit: int | None = Field(
        default=None,
        description="Optional tokens-per-minute ceiling overriding Groq rate-limit headers.",
    )
    reasoning_effort: str | None = Field(
        default="low",
        description="Sent to Groq where supported; set GROQ_REASONING_EFFORT empty to omit.",
    )
    request_timeout: float = 30.0

    def require_model(self) -> str:
        """Return ``GROQ_MODEL``, or raise :class:`ConfigError` if unset."""
        if not self.groq_model:
            raise ConfigError(
                "GROQ_MODEL is not set. Add it to .env (see .env.example)."
            )
        return self.groq_model

    def model_for(self, agent: str) -> str:
        """Return the model configured for a hypothesis agent.

        Args:
            agent: One of ``proposer``, ``skeptic``, ``prosecutor``, ``judge``.

        Raises:
            ConfigError: The agent name is unknown or the required model is unset.
        """
        role = _AGENT_MODEL_ROLE.get(agent.strip().lower())
        if role is None:
            expected = ", ".join(sorted(_AGENT_MODEL_ROLE))
            raise ConfigError(f"Unknown agent {agent!r}; expected one of: {expected}.")
        if role == "main":
            return self.require_model()
        model = self.groq_model_fast or self.groq_model
        if not model:
            raise ConfigError(
                "GROQ_MODEL is not set (GROQ_MODEL_FAST is unset too). Add it to .env."
            )
        return model


def load_settings(dotenv_path: Path | None = None) -> Settings:
    """Build :class:`Settings` from ``.env`` plus the process environment.

    Real environment variables take precedence over ``.env`` entries.

    Args:
        dotenv_path: Optional explicit ``.env`` path; defaults to the repo root.
    """
    load_dotenv(dotenv_path or PROJECT_ROOT / ".env", override=False)

    data_dir = Path(os.getenv("PROMETHEUS_DATA_DIR") or DEFAULT_DATA_DIR).expanduser()
    cache_dir = Path(
        os.getenv("PROMETHEUS_CACHE_DIR") or data_dir / "cache"
    ).expanduser()
    tpm_raw = os.getenv("GROQ_TPM_LIMIT", "").strip()

    return Settings(
        groq_api_key=_clean(os.getenv("GROQ_API_KEY")),
        groq_model=_clean(os.getenv("GROQ_MODEL")) or "",
        groq_model_fast=_clean(os.getenv("GROQ_MODEL_FAST")),
        data_dir=data_dir,
        cache_dir=cache_dir,
        tpm_limit=int(tpm_raw) if tpm_raw else None,
        reasoning_effort=_clean(os.getenv("GROQ_REASONING_EFFORT", "low")),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return load_settings()


def _clean(value: str | None) -> str | None:
    """Trim whitespace and treat an empty value as unset."""
    if value is None:
        return None
    value = value.strip()
    return value or None
