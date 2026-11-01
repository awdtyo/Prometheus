"""Disk cache for LLM responses."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def cache_key(
    model: str,
    system: str,
    user: str,
    params: dict[str, Any],
    *,
    mode: str | None = None,
    provider: str | None = None,
    schema: str | None = None,
) -> str:
    """Hash the request into a cache key.

    ``mode`` (fake/real), ``provider`` and ``schema`` (response model name) are
    part of the key so a fake-generated entry is never confused with a real one
    for the same model/prompt.
    """
    payload = {
        "model": model,
        "system": system,
        "user": user,
        "params": params,
    }
    if mode is not None:
        payload["mode"] = mode
    if provider is not None:
        payload["provider"] = provider
    if schema is not None:
        payload["schema"] = schema
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


class DiskCache:
    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        """Return the cached entry ``{"mode": ..., "value": ...}`` or None."""
        path = self._path(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def set(self, key: str, entry: dict[str, Any]) -> None:
        path = self._path(key)
        path.write_text(json.dumps(entry, default=str))

    def bypass(self) -> bool:
        return False
