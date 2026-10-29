from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from .util import atomic_write

CACHE_VERSION = 3
MAX_ENTRIES = 8000
CACHEABLE_STATUSES = ("killed", "survived", "timeout")


class Cache:
    def __init__(self, path: str, enabled: bool = True) -> None:
        self.path = path
        self.enabled = enabled
        self.entries: Dict[str, Dict[str, Any]] = {}
        if enabled:
            self._load()

    def _load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return
        if not isinstance(data, dict) or data.get("version") != CACHE_VERSION:
            return
        entries = data.get("entries")
        if isinstance(entries, dict):
            self.entries = {
                str(key): value
                for key, value in entries.items()
                if isinstance(value, dict)
                and value.get("status") in CACHEABLE_STATUSES
            }

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        return self.entries.get(key)

    def put(self, key: str, status: str, duration: float, killer: Optional[str], output: str) -> None:
        if not self.enabled or status not in CACHEABLE_STATUSES:
            return
        self.entries[key] = {
            "status": status,
            "duration": round(float(duration), 4),
            "killer": killer,
            "output": output[-2000:],
        }
        if len(self.entries) > MAX_ENTRIES:
            overflow = len(self.entries) - MAX_ENTRIES
            for old_key in list(self.entries)[:overflow]:
                self.entries.pop(old_key, None)

    def save(self) -> None:
        if not self.enabled:
            return
        payload = {"version": CACHE_VERSION, "entries": self.entries}
        try:
            atomic_write(self.path, json.dumps(payload, indent=2, ensure_ascii=False))
        except OSError:
            pass

    def clear(self) -> None:
        self.entries = {}
        try:
            os.unlink(self.path)
        except OSError:
            pass
