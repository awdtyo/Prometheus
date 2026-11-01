"""Thread-safe rate limiter for free-tier LLM usage."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class _State:
    minute_tokens: int = 0
    minute_start: float = 0.0
    day_tokens: int = 0
    day_start: float = 0.0
    lock: threading.Lock = None  # type: ignore[assignment]


class RateLimiter:
    def __init__(
        self,
        requests_per_minute: int = 30,
        tokens_per_minute: int = 8000,
        tokens_per_day: int = 200_000,
    ) -> None:
        self.rpm = requests_per_minute
        self.tpm = tokens_per_minute
        self.tpd = tokens_per_day
        self._lock = threading.Lock()
        self._minute_tokens = 0
        self._minute_start = time.monotonic()
        self._day_tokens = 0
        self._day_start = time.monotonic()
        self._requests_this_minute = 0
        self._request_minute_start = time.monotonic()

    def acquire(self, estimated_tokens: int) -> None:
        """Block until the call can be made within limits."""
        while True:
            with self._lock:
                now = time.monotonic()
                # reset minute windows
                if now - self._minute_start >= 60:
                    self._minute_tokens = 0
                    self._minute_start = now
                if now - self._request_minute_start >= 60:
                    self._requests_this_minute = 0
                    self._request_minute_start = now
                # reset day window
                if now - self._day_start >= 86400:
                    self._day_tokens = 0
                    self._day_start = now

                # daily budget warning
                if self._day_tokens + estimated_tokens >= 0.9 * self.tpd:
                    logger.warning(
                        "LLM daily token budget near limit: %d / %d",
                        self._day_tokens + estimated_tokens,
                        self.tpd,
                    )

                # check if we can proceed
                if (
                    self._requests_this_minute < self.rpm
                    and self._minute_tokens + estimated_tokens <= self.tpm
                    and self._day_tokens + estimated_tokens <= self.tpd
                ):
                    self._requests_this_minute += 1
                    self._minute_tokens += estimated_tokens
                    self._day_tokens += estimated_tokens
                    return
                # compute sleep time
                if self._requests_this_minute >= self.rpm:
                    wait = 60 - (now - self._request_minute_start)
                elif self._minute_tokens + estimated_tokens > self.tpm:
                    wait = 60 - (now - self._minute_start)
                else:
                    wait = 60 - (now - self._day_start)
                    if wait <= 0:
                        wait = 1
                wait = max(0.1, min(wait, 60))
            time.sleep(wait)

    def correct(self, actual_tokens: int, estimated_tokens: int) -> None:
        """Adjust token counts after a real response."""
        with self._lock:
            delta = actual_tokens - estimated_tokens
            self._minute_tokens = max(0, self._minute_tokens + delta)
            self._day_tokens = max(0, self._day_tokens + delta)
