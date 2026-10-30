"""Structured logging configuration for the backend.

Logs are emitted as JSON by default so request metadata can be consumed by log
aggregators. ``MISSION_AUTOPSY_LOG_FORMAT=text`` switches to a compact,
human-readable format for local development.
"""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from backend.settings import Settings

_REQUEST_ID: ContextVar[str] = ContextVar("request_id", default="-")

_STANDARD_RECORD_FIELDS = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
}


def get_request_id() -> str:
    """Return the request identifier bound to the current context."""
    return _REQUEST_ID.get()


def set_request_id(request_id: str) -> Any:
    """Bind a request identifier to the current context and return the token."""
    return _REQUEST_ID.set(request_id)


def reset_request_id(token: Any) -> None:
    """Restore the previous request identifier context."""
    _REQUEST_ID.reset(token)


class RequestIdFilter(logging.Filter):
    """Ensure every log record carries the active request identifier."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = get_request_id()
        return True


class JsonFormatter(logging.Formatter):
    """Render log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_FIELDS or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """Render a compact log line for interactive development."""

    def __init__(self) -> None:
        super().__init__(
            "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )


def configure_logging(settings: Settings) -> None:
    """Install a single application log handler on the root logger."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    formatter: logging.Formatter = (
        JsonFormatter() if settings.log_format == "json" else TextFormatter()
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(RequestIdFilter())
    handler.__dict__["_mission_autopsy_handler"] = True

    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, "_mission_autopsy_handler", False):
            root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)

    logging.getLogger("uvicorn.error").setLevel(level)
    logging.getLogger("uvicorn.access").setLevel(level)
