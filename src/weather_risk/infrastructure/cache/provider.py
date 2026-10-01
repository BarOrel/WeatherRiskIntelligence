from abc import ABC, abstractmethod


class CacheProvider[T](ABC):
    """Key-value cache with per-entry expiry.

    An infrastructure concern: adapters use it (via ``@cached``) to avoid repeated I/O.
    Application code never sees it. ``InMemoryTTLCache`` implements it today; a Redis
    implementation can replace it in the composition root.
    """

    @abstractmethod
    async def get(self, key: str) -> T | None:
        """Return the cached value, or None if absent or expired."""

    @abstractmethod
    async def set(self, key: str, value: T, ttl_seconds: int) -> None:
        """Store ``value`` for ``ttl_seconds``. A TTL of 0 stores nothing."""
