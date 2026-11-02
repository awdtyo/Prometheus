"""LLM model names and configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class ModelName:
    REASONING = "openai/gpt-oss-120b"
    FAST = "openai/gpt-oss-20b"
    ALT = "qwen/qwen3.8-27b"


@dataclass(frozen=True)
class LLMConfig:
    api_key: str | None = None
    base_url: str = "https://api.groq.com/openai/v1"
    cache_dir: Path = field(default_factory=lambda: Path("data/llm_cache"))
    fake: bool = True
    requests_per_minute: int = 30
    tokens_per_minute: int = 8000
    tokens_per_day: int = 200_000

    @classmethod
    def from_env(cls) -> LLMConfig:
        api_key = os.environ.get("GROQ_API_KEY") or os.environ.get("MISSION_AUTOPSY_LLM_API_KEY")
        # treat placeholder as missing
        if api_key and api_key.strip().lower() in {"", "your-api-key", "your_api_key"}:
            api_key = None
        fake_env = os.environ.get("MISSION_AUTOPSY_LLM_FAKE", "").strip().lower()
        if fake_env in {"true", "1", "yes"}:
            fake = True
        elif fake_env in {"false", "0", "no"}:
            fake = False
        else:
            fake = api_key is None
        cache_dir = Path(os.environ.get("MISSION_AUTOPSY_LLM_CACHE_DIR", "data/llm_cache"))
        return cls(api_key=api_key, fake=fake, cache_dir=cache_dir)
