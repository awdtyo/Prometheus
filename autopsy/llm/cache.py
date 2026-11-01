"""Disk cache for LLM responses."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def cache_key(model: str, system: str, user: str, params: dict[str, Any]) -> str:
    payload = json.dumps(
        {"model": model, "system": system, "user": user, "params": params},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class DiskCache:
    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def get(self, key: str) -> Any | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def set(self, key: str, value: Any) -> None:
        path = self._path(key)
        path.write_text(json.dumps(value, default=str))

    def bypass(self) -> bool:
        return False
