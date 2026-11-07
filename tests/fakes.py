"""Test doubles for the Groq SDK, so unit tests never touch the network."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any


class FakeStatusError(Exception):
    """Stand-in for a Groq SDK error carrying an HTTP status code."""

    def __init__(self, status_code: int, message: str = "fake Groq error") -> None:
        super().__init__(message)
        self.status_code = status_code


class FakeUsage:
    """Minimal ``usage`` object mirroring the Groq response shape."""

    def __init__(self, prompt_tokens: int = 10, completion_tokens: int = 5) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = prompt_tokens + completion_tokens


class FakeCompletion:
    """Minimal chat-completion object."""

    def __init__(
        self,
        content: str,
        *,
        headers: dict[str, str] | None = None,
        prompt_tokens: int = 10,
        completion_tokens: int = 5,
    ) -> None:
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]
        self.usage = FakeUsage(prompt_tokens, completion_tokens)
        self.headers = headers or {}


class FakeRawResponse:
    """Mirrors ``with_raw_response.create`` returning headers plus ``parse()``."""

    def __init__(self, completion: FakeCompletion) -> None:
        self.headers = completion.headers
        self._completion = completion

    def parse(self) -> FakeCompletion:
        return self._completion


class _FakeRawAPI:
    def __init__(self, completions: FakeCompletions) -> None:
        self._completions = completions

    def create(self, **kwargs: Any) -> FakeRawResponse:
        return FakeRawResponse(self._completions.create(**kwargs))


class FakeCompletions:
    """Scripted ``chat.completions`` endpoint.

    Each script entry is a ``FakeCompletion``, a plain string (shorthand for a
    completion with that content), or an exception to raise.
    """

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []
        self.with_raw_response = _FakeRawAPI(self)

    def create(self, **kwargs: Any) -> FakeCompletion:
        self.calls.append(kwargs)
        if not self.script:
            raise AssertionError("FakeCompletions script exhausted")
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, str):
            return FakeCompletion(item)
        return item


class FakeGroq:
    """Fake ``Groq`` client exposing ``chat.completions``."""

    def __init__(self, script: list[Any]) -> None:
        self.completions = FakeCompletions(script)
        self.chat = SimpleNamespace(completions=self.completions)

    @property
    def calls(self) -> list[dict[str, Any]]:
        return self.completions.calls


class FakeClock:
    """Deterministic clock replacing ``time.monotonic`` and ``time.sleep``."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds
