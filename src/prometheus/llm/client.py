"""The single entry point for every Groq LLM call.

Responsibilities (see AGENTS.md):

* retry with exponential backoff on 429/5xx;
* keep temperature at or below 0.2;
* validate JSON output against a pydantic schema, re-asking exactly once;
* cache responses on disk, keyed by a hash of model and prompt, with a bypass;
* count calls, cache hits, retries and tokens per call and per run;
* respect Groq's tokens-per-minute budget using ``x-ratelimit-*`` headers,
  sleeping before the limit instead of only reacting to a 429.

Tests inject a fake Groq client and a fake sleep function, so no test touches
the network.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from prometheus.config import ConfigError, Settings, get_settings

logger = logging.getLogger(__name__)

#: Hard ceiling from AGENTS.md; requests above this are rejected.
MAX_TEMPERATURE: float = 0.2

#: Default sampling temperature for every call.
DEFAULT_TEMPERATURE: float = 0.1

#: Default output budget per call.
DEFAULT_MAX_TOKENS: int = 900

#: Total attempts per request (first try plus retries).
MAX_ATTEMPTS: int = 4

#: Exponential backoff base in seconds.
BASE_BACKOFF: float = 0.5

#: Backoff ceiling in seconds.
MAX_BACKOFF: float = 8.0

#: Recommended ceiling from AGENTS.md; longer prompts log a warning.
MAX_PROMPT_TOKENS: int = 3000

#: HTTP statuses worth retrying.
RETRYABLE_STATUS: frozenset[int] = frozenset({429, 500, 502, 503, 504})

#: Exception class names worth retrying when no status code is attached.
RETRYABLE_EXCEPTIONS: frozenset[str] = frozenset(
    {"APIConnectionError", "APITimeoutError", "TimeoutException", "ConnectError"}
)

_DURATION_PART = re.compile(r"(?P<value>\d+(?:\.\d+)?)(?P<unit>[smh])")

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """Raised when a Groq call cannot be completed."""


class InvalidJSONError(LLMError):
    """Raised when the model returns invalid JSON twice in a row."""


class UsageStats(BaseModel):
    """Per-run counters, including the token spend AGENTS.md asks us to log."""

    calls: int = 0
    retries: int = 0
    cache_hits: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    sleep_seconds: float = 0.0

    def record_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        """Add one completed call's token usage."""
        self.calls += 1
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.total_tokens += prompt_tokens + completion_tokens

    def summary(self) -> str:
        """Return a compact one-line summary suitable for CLI output or logs."""
        return (
            f"calls={self.calls} cache_hits={self.cache_hits} retries={self.retries} "
            f"prompt_tokens={self.prompt_tokens} completion_tokens={self.completion_tokens} "
            f"total_tokens={self.total_tokens} slept={self.sleep_seconds:.1f}s"
        )


class ResponseCache:
    """On-disk JSON response cache under ``data/cache/``."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)

    @staticmethod
    def key(model: str, prompt: str, system: str | None = None) -> str:
        """Hash model, system prompt and prompt into a hex cache key.

        AGENTS.md specifies ``hash(model + prompt)``; the system prompt is
        folded in as well so two calls cannot collide when only their system
        message differs.
        """
        payload = f"{model}\x00{system or ''}\x00{prompt}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def path_for(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def get(self, key: str) -> str | None:
        """Return the cached response text, or ``None`` on a miss."""
        path = self.path_for(key)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
        response = payload.get("response")
        return response if isinstance(response, str) else None

    def put(
        self,
        key: str,
        *,
        model: str,
        prompt: str,
        response: str,
        usage: dict[str, int],
    ) -> None:
        """Store a response atomically. Cache failures must not break a run."""
        payload = {
            "key": key,
            "model": model,
            "prompt_sha": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "created_at": datetime.now(UTC).isoformat(),
            "usage": usage,
            "response": response,
        }
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            tmp = self.path_for(key).with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload), encoding="utf-8")
            tmp.replace(self.path_for(key))
        except OSError as exc:  # pragma: no cover - disk failure path
            logger.warning("could not write response cache: %s", exc)


def parse_duration_seconds(value: str) -> float | None:
    """Parse Groq duration headers such as ``1s``, ``2.5s`` or ``1m30s``.

    Returns ``None`` when the value cannot be understood.
    """
    text = (value or "").strip().lower()
    if not text:
        return None
    if text.isdigit():
        return float(text)
    total = 0.0
    matched = False
    for match in _DURATION_PART.finditer(text):
        matched = True
        amount = float(match.group("value"))
        unit = match.group("unit")
        total += amount * {"s": 1.0, "m": 60.0, "h": 3600.0}[unit]
    return total if matched else None


def _status_code(exc: Exception) -> int | None:
    """Best-effort extraction of an HTTP status from an SDK exception."""
    for candidate in (getattr(exc, "status_code", None), getattr(exc, "code", None)):
        if isinstance(candidate, int):
            return candidate
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def _is_retryable(exc: Exception, status: int | None) -> bool:
    if status is not None:
        return status in RETRYABLE_STATUS
    return type(exc).__name__ in RETRYABLE_EXCEPTIONS


class LLMClient:
    """Groq client wrapper used by every stage of the pipeline."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: Any | None = None,
        cache: ResponseCache | None = None,
        cache_enabled: bool = True,
        max_attempts: int = MAX_ATTEMPTS,
        base_backoff: float = BASE_BACKOFF,
        max_backoff: float = MAX_BACKOFF,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client
        self._cache = cache or ResponseCache(self._settings.cache_dir)
        self._cache_enabled = cache_enabled
        self._max_attempts = max(1, max_attempts)
        self._base_backoff = base_backoff
        self._max_backoff = max_backoff
        self._sleep = sleep
        self._monotonic = monotonic
        self.stats = UsageStats()
        self._tpm_remaining: int | None = None
        self._tpm_reset_at: float = 0.0

    # -- public API ---------------------------------------------------------

    def complete(
        self,
        prompt: str,
        *,
        agent: str | None = None,
        model: str | None = None,
        system: str | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        use_cache: bool | None = None,
    ) -> str:
        """Return a raw text completion.

        Args:
            prompt: User prompt. Keep it under ~3,000 tokens.
            agent: Optional agent name; selects the configured model.
            model: Explicit model, overriding ``agent``.
            system: Optional system message.
            temperature: Sampling temperature, at most 0.2.
            max_tokens: Output token budget.
            use_cache: Per-call cache override; otherwise the client default.

        Raises:
            ConfigError: No model is configured, or the agent name is unknown.
            LLMError: The call failed after all retries.
        """
        if not 0.0 <= temperature <= MAX_TEMPERATURE:
            raise ValueError(f"temperature must be between 0 and {MAX_TEMPERATURE}")
        resolved_model = self._resolve_model(agent=agent, model=model)
        self._warn_if_prompt_too_long(prompt, system)

        cache_on = self._cache_enabled if use_cache is None else use_cache
        cache_key = ResponseCache.key(resolved_model, prompt, system)
        if cache_on:
            cached = self._cache.get(cache_key)
            if cached is not None:
                self.stats.cache_hits += 1
                logger.info("cache hit model=%s key=%s", resolved_model, cache_key[:12])
                return cached

        messages = self._build_messages(prompt, system)
        text, usage, headers = self._request(
            messages=messages,
            model=resolved_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        self._apply_rate_limit_headers(headers)

        if cache_on:
            self._cache.put(
                cache_key,
                model=resolved_model,
                prompt=prompt,
                response=text,
                usage=usage,
            )
        return text

    def complete_json(
        self,
        prompt: str,
        schema: type[T],
        *,
        agent: str | None = None,
        model: str | None = None,
        system: str | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        use_cache: bool | None = None,
    ) -> T:
        """Return a completion validated against a pydantic schema.

        On invalid JSON the model is re-asked exactly once with the validation
        error attached. A second failure raises :class:`InvalidJSONError`; an
        invalid object is never returned to the caller.
        """
        instruction = self._json_instruction(schema)
        current_prompt = instruction + prompt
        for attempt in (1, 2):
            text = self.complete(
                current_prompt,
                agent=agent,
                model=model,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
                use_cache=use_cache,
            )
            try:
                return schema.model_validate_json(_strip_code_fences(text))
            except ValidationError as exc:
                if attempt == 2:
                    raise InvalidJSONError(
                        f"model returned invalid JSON twice for schema {schema.__name__}"
                    ) from exc
                logger.warning("invalid JSON from model; re-asking once")
                current_prompt = (
                    instruction
                    + prompt
                    + "\n\nYour previous reply was not valid JSON matching the schema. "
                    + f"Validation error: {exc.errors()[:2]}. Reply with JSON only."
                )
        raise InvalidJSONError(  # pragma: no cover - loop always returns or raises
            f"model returned invalid JSON for schema {schema.__name__}"
        )

    def reset_stats(self) -> None:
        """Clear per-run counters."""
        self.stats = UsageStats()

    # -- internals ----------------------------------------------------------

    def _resolve_model(self, *, agent: str | None, model: str | None) -> str:
        if model:
            return model
        if agent:
            return self._settings.model_for(agent)
        return self._settings.require_model()

    @staticmethod
    def _warn_if_prompt_too_long(prompt: str, system: str | None) -> None:
        estimated = (len(prompt) + len(system or "")) // 4
        if estimated > MAX_PROMPT_TOKENS:
            logger.warning(
                "prompt is ~%d tokens, above the ~%d token guidance; trim it",
                estimated,
                MAX_PROMPT_TOKENS,
            )

    def _get_client(self) -> Any:
        if self._client is None:
            from groq import Groq

            if not self._settings.groq_api_key:
                raise ConfigError(
                    "GROQ_API_KEY is not set. Add it to .env (see .env.example)."
                )
            self._client = Groq(
                api_key=self._settings.groq_api_key,
                timeout=self._settings.request_timeout,
            )
        return self._client

    @staticmethod
    def _build_messages(prompt: str, system: str | None) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    @staticmethod
    def _json_instruction(schema: type[BaseModel]) -> str:
        return (
            "Respond with a single JSON object only, no prose and no code fences. "
            "It must validate against this JSON Schema:\n"
            f"{json.dumps(schema.model_json_schema())}\n\n"
        )

    def _request(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> tuple[str, dict[str, int], dict[str, str]]:
        estimated = self._estimate_tokens(messages, max_tokens)
        last_error: Exception | None = None

        for attempt in range(1, self._max_attempts + 1):
            self._throttle(estimated)
            try:
                text, usage, headers = self._create(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as exc:  # noqa: BLE001 - classified below
                status = _status_code(exc)
                retryable = _is_retryable(exc, status)
                if not retryable or attempt == self._max_attempts:
                    raise LLMError(
                        f"Groq call failed (status={status}): {exc}"
                    ) from exc
                last_error = exc
                delay = min(self._base_backoff * 2 ** (attempt - 1), self._max_backoff)
                self.stats.retries += 1
                self.stats.sleep_seconds += delay
                logger.warning(
                    "retryable Groq failure status=%s; attempt %d/%d in %.2fs",
                    status,
                    attempt,
                    self._max_attempts,
                    delay,
                )
                self._sleep(delay)
                continue

            self.stats.record_usage(
                usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
            )
            logger.info(
                "llm call model=%s prompt_tokens=%d completion_tokens=%d total=%d",
                model,
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
                usage.get("total_tokens", 0),
            )
            return text, usage, headers

        raise LLMError(f"Groq call failed after retries: {last_error}")

    def _create(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> tuple[str, dict[str, int], dict[str, str]]:
        completions = self._get_client().chat.completions
        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        effort = self._settings.reasoning_effort
        if effort:
            params["reasoning_effort"] = effort
        raw_api = getattr(completions, "with_raw_response", None)
        if raw_api is not None:
            raw = raw_api.create(**params)
            headers = _lower_headers(getattr(raw, "headers", None))
            data = raw.parse()
        else:
            data = completions.create(**params)
            headers = _lower_headers(getattr(data, "headers", None))

        choices = getattr(data, "choices", None) or []
        content = ""
        if choices:
            content = getattr(getattr(choices[0], "message", None), "content", "") or ""
        return content, _usage_dict(getattr(data, "usage", None)), headers

    def _estimate_tokens(self, messages: list[dict[str, str]], max_tokens: int) -> int:
        chars = sum(len(message.get("content", "")) for message in messages)
        return max(1, chars // 4) + max_tokens

    def _throttle(self, estimated_tokens: int) -> None:
        """Sleep before a call would exceed the remaining per-minute budget."""
        if self._tpm_remaining is None:
            return
        if self._tpm_remaining - estimated_tokens >= 0:
            return
        wait = self._tpm_reset_at - self._monotonic()
        self._tpm_remaining = None
        if wait <= 0:
            return
        logger.info("tokens-per-minute budget nearly spent; sleeping %.2fs", wait)
        self.stats.sleep_seconds += wait
        self._sleep(wait)

    def _apply_rate_limit_headers(self, headers: dict[str, str]) -> None:
        remaining_raw = headers.get("x-ratelimit-remaining-tokens")
        reset_raw = headers.get("x-ratelimit-reset-tokens", "")
        if remaining_raw is None:
            return
        try:
            remaining = int(float(remaining_raw))
        except ValueError:
            return
        limit = self._settings.tpm_limit
        if limit is not None:
            remaining = min(remaining, limit)
        reset_seconds = parse_duration_seconds(reset_raw)
        self._tpm_remaining = remaining
        self._tpm_reset_at = self._monotonic() + (reset_seconds or 0.0)
        logger.debug(
            "rate limit remaining_tokens=%d reset_in=%.2fs",
            remaining,
            reset_seconds or 0.0,
        )


def _usage_dict(usage: Any) -> dict[str, int]:
    if usage is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    total = int(getattr(usage, "total_tokens", prompt_tokens + completion_tokens) or 0)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total,
    }


def _lower_headers(headers: Any) -> dict[str, str]:
    if not headers:
        return {}
    try:
        items = dict(headers).items()
    except (TypeError, ValueError):
        return {}
    return {str(key).lower(): str(value) for key, value in items}


def _strip_code_fences(text: str) -> str:
    """Remove a surrounding ```json ... ``` fence if the model added one."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) >= 2 and lines[-1].strip().startswith("```"):
        return "\n".join(lines[1:-1]).strip()
    return stripped
