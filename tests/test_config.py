"""Tests for environment/.env configuration handling."""

from __future__ import annotations

from pathlib import Path

import pytest

from prometheus.config import ConfigError, Settings, load_settings


def test_agent_models_use_main_and_fast(settings: Settings) -> None:
    assert settings.model_for("proposer") == "test-main"
    assert settings.model_for("skeptic") == "test-main"
    assert settings.model_for("prosecutor") == "test-fast"
    assert settings.model_for("judge") == "test-fast"


def test_fast_model_falls_back_to_main(settings: Settings) -> None:
    without_fast = settings.model_copy(update={"groq_model_fast": None})

    assert without_fast.model_for("judge") == "test-main"


def test_require_model_raises_when_unset(settings: Settings) -> None:
    bare = settings.model_copy(update={"groq_model": ""})

    with pytest.raises(ConfigError, match="GROQ_MODEL"):
        bare.require_model()


def test_load_settings_reads_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        "GROQ_API_KEY",
        "GROQ_MODEL",
        "GROQ_MODEL_FAST",
        "PROMETHEUS_DATA_DIR",
        "PROMETHEUS_CACHE_DIR",
        "GROQ_TPM_LIMIT",
    ):
        monkeypatch.delenv(name, raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "GROQ_API_KEY=dotenv-key\nGROQ_MODEL=dotenv-main\nGROQ_MODEL_FAST=dotenv-fast\n",
        encoding="utf-8",
    )

    loaded = load_settings(env_file)

    assert loaded.groq_api_key == "dotenv-key"
    assert loaded.groq_model == "dotenv-main"
    assert loaded.groq_model_fast == "dotenv-fast"
    assert loaded.cache_dir.name == "cache"


def test_process_env_overrides_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("GROQ_MODEL=from-file\n", encoding="utf-8")
    monkeypatch.setenv("GROQ_MODEL", "from-process")
    monkeypatch.setenv("PROMETHEUS_DATA_DIR", str(tmp_path / "custom"))

    loaded = load_settings(env_file)

    assert loaded.groq_model == "from-process"
    assert loaded.data_dir == tmp_path / "custom"
    assert loaded.cache_dir == tmp_path / "custom" / "cache"


def test_blank_values_are_treated_as_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "   ")

    loaded = load_settings(tmp_path / "missing.env")

    assert loaded.groq_api_key is None


def test_reasoning_effort_defaults_and_can_be_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GROQ_REASONING_EFFORT", raising=False)
    assert load_settings(tmp_path / "missing.env").reasoning_effort == "low"

    monkeypatch.setenv("GROQ_REASONING_EFFORT", "")
    assert load_settings(tmp_path / "missing.env").reasoning_effort is None
