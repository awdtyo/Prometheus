"""LLM client layer: the only code that talks to an LLM.

Deterministic offline FakeLLM is the default when no API key is present.
"""

from __future__ import annotations

from autopsy.llm.client import LLMClient, LLMCounters, complete_json
from autopsy.llm.config import LLMConfig, ModelName
from autopsy.llm.errors import (
    AuthenticationError,
    InvalidOutputError,
    RateLimitExhaustedError,
    TimeoutError,
)

__all__ = [
    "LLMClient",
    "LLMCounters",
    "complete_json",
    "LLMConfig",
    "ModelName",
    "AuthenticationError",
    "InvalidOutputError",
    "RateLimitExhaustedError",
    "TimeoutError",
]
