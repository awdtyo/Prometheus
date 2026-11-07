"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from prometheus.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings with fake credentials and an isolated cache directory."""
    return Settings(
        groq_api_key="test-key",
        groq_model="test-main",
        groq_model_fast="test-fast",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "data" / "cache",
    )
