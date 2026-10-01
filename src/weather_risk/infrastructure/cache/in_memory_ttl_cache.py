import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from weather_risk.infrastructure.cache.provider import CacheProvider


@dataclass(frozen=True, slots=True)
class _Entry[T]:
    value: T
    expires_at: float


class InMemoryTTLCache[T](CacheProvider[T]):
    """Process-local, bounded TTL cache.

    - Expiry is lazy: an expired entry is dropped when read, or when the cache is full.
    - When full, expired entries are purged first, then the oldest-written entry is evicted.
    - A lock guards every operation, so it is safe from both the event loop and worker
      threads. No await happens while the lock is held.
    """

    def __init__(self, max_entries: int, clock: Callable[[], float] = time.monotonic) -> None:
        if max_entries < 1:
            raise ValueError(f"max_entries must be at least 1, got {max_entries}")
        self._max_entries = max_entries
        self._clock = clock
        self._entries: dict[str, _Entry[T]] = {}
        self._lock = threading.Lock()

    async def get(self, key: str) -> T | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= self._clock():
                del self._entries[key]
                return None
            return entry.value

    async def set(self, key: str, value: T, ttl_seconds: int) -> None:
        if ttl_seconds < 0:
            raise ValueError(f"ttl_seconds must not be negative, got {ttl_seconds}")
        with self._lock:
            # Re-inserting moves the key to the end, keeping dict order = write order.
            self._entries.pop(key, None)
            if ttl_seconds == 0:
                return
            now = self._clock()
            if len(self._entries) >= self._max_entries:
                self._make_room(now)
            self._entries[key] = _Entry(value=value, expires_at=now + ttl_seconds)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def _make_room(self, now: float) -> None:
        expired = [key for key, entry in self._entries.items() if entry.expires_at <= now]
        for key in expired:
            del self._entries[key]
        while len(self._entries) >= self._max_entries:
            del self._entries[next(iter(self._entries))]
