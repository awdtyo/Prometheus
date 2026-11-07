"""CLI smoke tests: help, version, and llm-ping behaviour with a mocked client."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

import prometheus.cli as cli
from prometheus.config import Settings
from prometheus.llm.client import LLMClient, LLMError

runner = CliRunner()


@pytest.fixture
def fake_settings(tmp_path: Path) -> Settings:
    return Settings(
        groq_api_key="test-key",
        groq_model="test-main",
        cache_dir=tmp_path / "cache",
    )


def test_help_lists_commands() -> None:
    result = runner.invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    assert "llm-ping" in result.output


def test_version() -> None:
    result = runner.invoke(cli.app, ["--version"])

    assert result.exit_code == 0
    assert "prometheus" in result.output


def test_llm_ping_without_key_explains_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Config lookup happens inside the command, so patch the module-level symbol.
    monkeypatch.setattr(cli, "get_settings", lambda: Settings())

    result = runner.invoke(cli.app, ["llm-ping"])

    combined = result.output + getattr(result, "stderr", "")
    assert result.exit_code == 1
    assert "GROQ_API_KEY" in combined


def test_llm_ping_success(
    fake_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: fake_settings)

    def fake_complete_json(self, prompt, schema, **kwargs):  # type: ignore[no-untyped-def]
        return schema(status="ok", echo="a helpful model")

    monkeypatch.setattr(LLMClient, "complete_json", fake_complete_json)

    result = runner.invoke(cli.app, ["llm-ping"])

    assert result.exit_code == 0
    assert '"status": "ok"' in result.output
    assert "a helpful model" in result.output
    assert "usage:" in result.output


def test_llm_ping_reports_failure(
    fake_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: fake_settings)

    def failing_complete_json(self, prompt, schema, **kwargs):  # type: ignore[no-untyped-def]
        raise LLMError("boom")

    monkeypatch.setattr(LLMClient, "complete_json", failing_complete_json)

    result = runner.invoke(cli.app, ["llm-ping"])

    combined = result.output + getattr(result, "stderr", "")
    assert result.exit_code == 1
    assert "boom" in combined
