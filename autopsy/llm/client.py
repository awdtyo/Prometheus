"""LLM client: complete_json with validation, caching, rate limiting."""

from __future__ import annotations

import json
import logging
import random
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from autopsy.llm.cache import DiskCache, cache_key
from autopsy.llm.config import LLMConfig
from autopsy.llm.errors import (
    AuthenticationError,
    InvalidOutputError,
    RateLimitExhaustedError,
    TimeoutError,
)
from autopsy.llm.limiter import RateLimiter

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


@dataclass
class LLMCounters:
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cache_hits: int = 0
    per_model: dict[str, dict[str, int]] = field(default_factory=dict)

    def record_call(self, model: str, tokens_in: int, tokens_out: int) -> None:
        self.calls += 1
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out
        entry = self.per_model.setdefault(model, {"calls": 0, "tokens_in": 0, "tokens_out": 0})
        entry["calls"] += 1
        entry["tokens_in"] += tokens_in
        entry["tokens_out"] += tokens_out

    def record_cache_hit(self) -> None:
        self.cache_hits += 1


_NODE_ID_RE = re.compile(r"\b(obs:[A-Za-z0-9_.-]+)\b|\b(evt:[A-Za-z0-9_.-]+)\b")


def _extract_node_ids(user: str) -> list[str]:
    """Pull real node ids out of the agent prompt context so canned
    hypotheses/evidence cite ids that actually exist."""
    found: list[str] = []
    for match in _NODE_ID_RE.finditer(user):
        found.append(match.group(1) or match.group(2))
    return found


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _evidence_dict(source_id: str, user: str, stance: str) -> dict[str, Any]:
    return {
        "evidence_id": "ev_canned_00",
        "source_id": source_id,
        "timestamp": _now_iso(),
        "evidence_type": "observation",
        "description": "canned evidence",
        "supports_or_contradicts": stance,
        "reliability": 0.5,
    }


def _claim_dict() -> dict[str, Any]:
    return {"text": "canned claim", "label": "inference"}


def _hypothesis_dict(user: str, index: int) -> dict[str, Any]:
    nodes = _extract_node_ids(user)
    chain = nodes[:3] or ["obs:canned_001"]
    anchor = chain[0]
    return {
        "hypothesis_id": f"hyp_canned_{index:02d}",
        "title": f"canned hypothesis {index}",
        "summary": "canned explanation",
        "causal_chain": list(chain),
        "evidence_ids": [anchor],
        "contradiction_ids": [],
        "assumptions": [],
        "confidence": 0.5,
        "score": 0.5,
    }


class FakeLLM:
    """Deterministic offline LLM returning schema-valid canned outputs.

    Every response model used by the agents (``Hypothesis``,
    ``ProposerOutput``, ``Evidence``, ``LabelledClaim``,
    ``ProsecutorOutput``, ``SkepticOutput``) is built from its schema so the
    canned output validates. Hypotheses and evidence cite real node ids parsed
    from the prompt context instead of fabricated identifiers.
    """

    def complete(
        self,
        model: str,
        system: str,
        user: str,
        response_model: type[T],
        max_tokens: int,
        temperature: float,
    ) -> T:
        data = _canned(response_model, user)
        return response_model.model_validate(data)


def _canned(model: type[BaseModel], user: str = "") -> dict[str, Any]:
    name = model.__name__

    if name == "ProposerOutput":
        return {"hypotheses": [_hypothesis_dict(user, i) for i in range(3)]}

    if name == "Hypothesis":
        return _hypothesis_dict(user, 0)

    if name == "Evidence":
        stance = "contradicts" if "skeptic" in user.lower() else "supports"
        nodes = _extract_node_ids(user)
        return _evidence_dict(nodes[0] if nodes else "obs:canned_001", user, stance)

    if name == "LabelledClaim":
        return _claim_dict()

    if name == "ProsecutorOutput":
        nodes = _extract_node_ids(user)
        anchor = nodes[0] if nodes else "obs:canned_001"
        return {
            "evidence": [_evidence_dict(anchor, user, "supports")],
            "claims": [_claim_dict()],
        }

    if name == "SkepticOutput":
        nodes = _extract_node_ids(user)
        anchor = nodes[0] if nodes else "obs:canned_001"
        return {"evidence": [_evidence_dict(anchor, user, "contradicts")]}

    # Generic annotation-based fallback for any other model.
    result: dict[str, Any] = {}
    for field_name, field_info in model.model_fields.items():
        ann = field_info.annotation
        origin = getattr(ann, "__origin__", None)
        is_list = ann is list or origin is list
        if ann is str:
            result[field_name] = "canned"
        elif ann is int:
            result[field_name] = 1
        elif ann is float:
            result[field_name] = 0.5
        elif ann is bool:
            result[field_name] = True
        elif is_list:
            result[field_name] = []
        elif ann is dict or origin is dict:
            result[field_name] = {}
        else:
            default = field_info.default if field_info.default is not ... else None
            result[field_name] = default
    return result


class LLMClient:
    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig.from_env()
        self.counters = LLMCounters()
        self._limiter = RateLimiter(
            requests_per_minute=self.config.requests_per_minute,
            tokens_per_minute=self.config.tokens_per_minute,
            tokens_per_day=self.config.tokens_per_day,
        )
        self._cache = DiskCache(self.config.cache_dir)
        self._lock = threading.Lock()
        self._client = None
        if not self.config.fake and self.config.api_key:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=self.config.api_key, base_url=self.config.base_url)
            except Exception as exc:
                logger.warning("Failed to init OpenAI client: %s", exc)
                self._client = None

    def complete_json(
        self,
        model: str,
        system: str,
        user: str,
        response_model: type[T],
        max_tokens: int = 1024,
        temperature: float = 0.0,
        bypass_cache: bool = False,
    ) -> T:
        params = {"max_tokens": max_tokens, "temperature": temperature}
        key = cache_key(model, system, user, params)

        if not bypass_cache:
            cached = self._cache.get(key)
            if cached is not None:
                self.counters.record_cache_hit()
                try:
                    return response_model.model_validate(cached)
                except ValidationError:
                    pass

        if self.config.fake:
            result = FakeLLM().complete(
                model, system, user, response_model, max_tokens, temperature
            )
            if not bypass_cache:
                self._cache.set(key, result.model_dump())
            self.counters.record_call(model, 0, 0)
            return result

        if self._client is None:
            raise AuthenticationError("No API client available (missing key).")

        estimated = len(system + user) // 4 + max_tokens
        self._limiter.acquire(estimated)

        last_error: Exception | None = None
        for attempt in range(2):
            try:
                resp = self._client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature,
                    response_format={"type": "json_object"},
                    timeout=60,
                )
                content = resp.choices[0].message.content or ""
                usage = getattr(resp, "usage", None)
                tokens_in = getattr(usage, "prompt_tokens", 0) if usage else 0
                tokens_out = getattr(usage, "completion_tokens", 0) if usage else 0
                self._limiter.correct(tokens_in + tokens_out, estimated)

                try:
                    data = json.loads(content)
                except json.JSONDecodeError as exc:
                    raise InvalidOutputError(f"Invalid JSON: {exc}") from exc

                try:
                    result = response_model.model_validate(data)
                except ValidationError as exc:
                    if attempt == 0:
                        # retry with validation error appended
                        user = user + f"\n\nPrevious output failed validation: {exc}"
                        last_error = exc
                        continue
                    raise InvalidOutputError(str(exc)) from exc

                if not bypass_cache:
                    self._cache.set(key, result.model_dump())
                self.counters.record_call(model, tokens_in, tokens_out)
                return result
            except Exception as exc:
                # map to typed errors
                msg = str(exc).lower()
                if "401" in msg or "auth" in msg or "api key" in msg:
                    raise AuthenticationError(str(exc)) from exc
                if "429" in msg or "rate" in msg:
                    # backoff with retry-after
                    retry_after = 1.0
                    # try to parse
                    import re

                    m = re.search(r"retry.after[:\s]+(\d+)", msg)
                    if m:
                        retry_after = float(m.group(1))
                    wait = retry_after * (2**attempt) + random.uniform(0, 1)
                    if attempt == 1:
                        raise RateLimitExhaustedError(str(exc)) from exc
                    time.sleep(wait)
                    last_error = exc
                    continue
                if "timeout" in msg:
                    raise TimeoutError(str(exc)) from exc
                raise

        if last_error:
            raise InvalidOutputError(str(last_error)) from last_error
        raise InvalidOutputError("Unknown failure")


def complete_json(
    model: str,
    system: str,
    user: str,
    response_model: type[T],
    max_tokens: int = 1024,
    temperature: float = 0.0,
    bypass_cache: bool = False,
    config: LLMConfig | None = None,
) -> T:
    client = LLMClient(config)
    return client.complete_json(
        model, system, user, response_model, max_tokens, temperature, bypass_cache
    )
