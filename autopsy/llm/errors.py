"""Typed exceptions for the LLM layer."""


class LLMError(Exception):
    """Base class for LLM errors."""


class AuthenticationError(LLMError):
    """Missing or invalid API key."""


class RateLimitExhaustedError(LLMError):
    """Rate limit exhausted after retries."""


class InvalidOutputError(LLMError):
    """Model output failed validation."""


class TimeoutError(LLMError):
    """Request timed out."""
