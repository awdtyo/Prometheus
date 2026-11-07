"""Unit tests for the Groq client: retries, JSON validation, cache, budgeting."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from prometheus.config import ConfigError, Settings
from prometheus.llm.client import (
    InvalidJSONError,
    LLMClient,
    LLMError,
    ResponseCache,
    parse_duration_seconds,
)
from tests.fakes import FakeClock, FakeCompletion, FakeGroq, FakeStatusError


class Answer(BaseModel):
    status: str
    echo: str


def make_client(
    settings: Settings,
    script: list[object],
    **kwargs: object,
) -> tuple[LLMClient, FakeGroq]:
    fake = FakeGroq(list(script))
    client = LLMClient(
        settings=settings,
        client=fake,
        sleep=lambda _seconds: None,
        **kwargs,  # type: ignore[arg-type]
    )
    return client, fake


def test_complete_returns_text_and_counts_tokens(settings: Settings) -> None:
    client, fake = make_client(
        settings, [FakeCompletion("hello", prompt_tokens=12, completion_tokens=3)]
    )

    assert client.complete("say hi") == "hello"
    assert len(fake.calls) == 1
    assert fake.calls[0]["model"] == "test-main"
    assert fake.calls[0]["temperature"] <= 0.2
    assert client.stats.calls == 1
    assert client.stats.prompt_tokens == 12
    assert client.stats.completion_tokens == 3
    assert client.stats.total_tokens == 15


def test_temperature_above_limit_is_rejected(settings: Settings) -> None:
    client, fake = make_client(settings, ["never used"])

    with pytest.raises(ValueError, match="temperature"):
        client.complete("too hot", temperature=0.9)

    assert fake.calls == []


def test_reasoning_effort_is_forwarded(settings: Settings) -> None:
    client, fake = make_client(settings, ["ok"])

    client.complete("p")

    assert fake.calls[0]["reasoning_effort"] == "low"


def test_oversized_prompt_warns(
    settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    client, _ = make_client(settings, ["ok"])

    with caplog.at_level("WARNING", logger="prometheus.llm.client"):
        client.complete("word " * 4000)

    assert any("above the" in record.message for record in caplog.records)


def test_reasoning_effort_omitted_when_disabled(settings: Settings) -> None:
    quiet = settings.model_copy(update={"reasoning_effort": None})
    client, fake = make_client(quiet, ["ok"])

    client.complete("p")

    assert "reasoning_effort" not in fake.calls[0]


def test_agent_model_selection(settings: Settings) -> None:
    client, fake = make_client(settings, ["a", "b"])

    client.complete("p1", agent="proposer")
    client.complete("p2", agent="judge")

    assert [call["model"] for call in fake.calls] == ["test-main", "test-fast"]


def test_unknown_agent_raises(settings: Settings) -> None:
    client, _ = make_client(settings, [])

    with pytest.raises(ConfigError, match="Unknown agent"):
        client.complete("p", agent="bystander")


def test_missing_main_model_raises(settings: Settings) -> None:
    bare = Settings(groq_api_key="k", cache_dir=settings.cache_dir)
    client, fake = make_client(bare, [])

    with pytest.raises(ConfigError, match="GROQ_MODEL"):
        client.complete("p")

    assert fake.calls == []


def test_retries_on_429_then_succeeds(settings: Settings) -> None:
    clock = FakeClock()
    fake = FakeGroq([FakeStatusError(429), FakeStatusError(429), "recovered"])
    client = LLMClient(settings=settings, client=fake, sleep=clock.sleep, monotonic=clock.monotonic)

    assert client.complete("p") == "recovered"
    assert len(fake.calls) == 3
    assert client.stats.retries == 2
    assert clock.sleeps == [0.5, 1.0]
    assert client.stats.total_tokens == 15


def test_retries_on_5xx(settings: Settings) -> None:
    client, fake = make_client(settings, [FakeStatusError(503), "ok"])

    assert client.complete("p") == "ok"
    assert len(fake.calls) == 2


def test_non_retryable_status_fails_immediately(settings: Settings) -> None:
    client, fake = make_client(settings, [FakeStatusError(400)])

    with pytest.raises(LLMError, match="status=400"):
        client.complete("p")

    assert len(fake.calls) == 1
    assert client.stats.retries == 0


def test_retry_exhaustion_raises(settings: Settings) -> None:
    client, fake = make_client(
        settings,
        [FakeStatusError(500), FakeStatusError(500)],
        max_attempts=2,
    )

    with pytest.raises(LLMError, match="failed"):
        client.complete("p")

    assert len(fake.calls) == 2
    assert client.stats.retries == 1


def test_invalid_json_reasks_once_then_succeeds(settings: Settings) -> None:
    client, fake = make_client(
        settings,
        ["not json at all", '{"status": "ok", "echo": "hi"}'],
    )

    answer = client.complete_json("ping", Answer)

    assert answer.status == "ok"
    assert len(fake.calls) == 2
    assert "not valid JSON" in fake.calls[1]["messages"][-1]["content"]


def test_invalid_json_twice_raises(settings: Settings) -> None:
    client, fake = make_client(settings, ["nope", "still nope"])

    with pytest.raises(InvalidJSONError, match="twice"):
        client.complete_json("ping", Answer)

    assert len(fake.calls) == 2


def test_code_fences_are_stripped(settings: Settings) -> None:
    fenced = '```json\n{"status": "ok", "echo": "hi"}\n```'
    client, _ = make_client(settings, [fenced])

    assert client.complete_json("ping", Answer).echo == "hi"


def test_cache_hit_skips_the_sdk(settings: Settings) -> None:
    first = FakeCompletion('{"status": "ok", "echo": "cached"}')
    client_one, _ = make_client(settings, [first])
    assert client_one.complete_json("ping", Answer).echo == "cached"

    # Second client has an empty script: any SDK call would raise AssertionError.
    client_two, fake_two = make_client(settings, [])
    assert client_two.complete_json("ping", Answer).echo == "cached"
    assert fake_two.calls == []
    assert client_two.stats.cache_hits == 1


def test_cache_bypass_calls_the_sdk_again(settings: Settings) -> None:
    client, fake = make_client(
        settings,
        ["first", "second"],
        cache_enabled=False,
    )

    assert client.complete("same prompt") == "first"
    assert client.complete("same prompt") == "second"
    assert len(fake.calls) == 2
    assert client.stats.cache_hits == 0
    assert not settings.cache_dir.exists() or not list(settings.cache_dir.glob("*.json"))


def test_cache_key_includes_model(settings: Settings) -> None:
    client, fake = make_client(settings, ["one", "two"])

    assert client.complete("same prompt", model="model-a") == "one"
    assert client.complete("same prompt", model="model-b") == "two"
    assert len(fake.calls) == 2


def test_tpm_budget_sleeps_before_next_call(settings: Settings) -> None:
    clock = FakeClock()
    rate_limited = FakeCompletion(
        "one", headers={"x-ratelimit-remaining-tokens": "5", "x-ratelimit-reset-tokens": "2s"}
    )
    fake = FakeGroq([rate_limited, "two"])
    client = LLMClient(settings=settings, client=fake, sleep=clock.sleep, monotonic=clock.monotonic)

    assert client.complete("p", max_tokens=100) == "one"
    assert client.complete("q", max_tokens=100) == "two"

    # Estimated prompt+output exceeds the 5 remaining tokens, so the client waits
    # for the advertised reset instead of provoking a 429.
    assert clock.sleeps == [2.0]
    assert client.stats.sleep_seconds == 2.0
    assert client.stats.retries == 0


def test_parse_duration_seconds() -> None:
    assert parse_duration_seconds("1s") == 1.0
    assert parse_duration_seconds("2.5s") == 2.5
    assert parse_duration_seconds("1m30s") == 90.0
    assert parse_duration_seconds("") is None
    assert parse_duration_seconds("later") is None


def test_response_cache_key_changes_with_model_and_system() -> None:
    base = ResponseCache.key("m", "p")
    assert base != ResponseCache.key("m2", "p")
    assert base != ResponseCache.key("m", "p", "be terse")


def test_cache_survives_a_corrupt_file(settings: Settings) -> None:
    client, fake = make_client(settings, ["fresh"])
    key = ResponseCache.key("test-main", "p")
    cache = ResponseCache(settings.cache_dir)
    cache.directory.mkdir(parents=True, exist_ok=True)
    cache.path_for(key).write_text("{not json", encoding="utf-8")

    assert client.complete("p") == "fresh"
    assert fake.calls[0]["model"] == "test-main"
