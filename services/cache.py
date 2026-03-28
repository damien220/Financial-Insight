"""Simple in-memory TTL cache for API responses."""

import time
from typing import Any, Optional


class TTLCache:
    """Thread-safe TTL cache for reducing redundant API calls.

    Usage::
        cache = TTLCache(default_ttl=300)  # 5 minutes
        cache.set("gold_5d", data)
        result = cache.get("gold_5d")  # returns data if < 5 min old
    """

    def __init__(self, default_ttl: int = 300):
        self._store: dict[str, tuple[float, Any]] = {}
        self._default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        expiry, value = entry
        if time.monotonic() > expiry:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        expiry = time.monotonic() + (ttl if ttl is not None else self._default_ttl)
        self._store[key] = (expiry, value)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    def size(self) -> int:
        self._cleanup()
        return len(self._store)

    def _cleanup(self) -> None:
        now = time.monotonic()
        expired = [k for k, (exp, _) in self._store.items() if now > exp]
        for k in expired:
            del self._store[k]
