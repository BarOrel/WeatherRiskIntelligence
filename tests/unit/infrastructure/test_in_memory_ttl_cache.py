import pytest
from support.fakes import FakeClock

from weather_risk.infrastructure.cache import InMemoryTTLCache


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def cache(clock: FakeClock) -> InMemoryTTLCache[str]:
    return InMemoryTTLCache[str](max_entries=10, clock=clock)


async def test_miss_returns_none(cache: InMemoryTTLCache[str]) -> None:
    assert await cache.get("missing") is None


async def test_hit_returns_stored_value(cache: InMemoryTTLCache[str]) -> None:
    await cache.set("k", "v", ttl_seconds=60)

    assert await cache.get("k") == "v"


async def test_entry_is_served_until_just_before_expiry(
    cache: InMemoryTTLCache[str], clock: FakeClock
) -> None:
    await cache.set("k", "v", ttl_seconds=60)
    clock.advance(59.999)

    assert await cache.get("k") == "v"


async def test_expired_entry_is_never_returned_and_is_removed(
    cache: InMemoryTTLCache[str], clock: FakeClock
) -> None:
    await cache.set("k", "v", ttl_seconds=60)
    clock.advance(60)

    assert await cache.get("k") is None
    assert len(cache) == 0


async def test_overwrite_replaces_value_and_resets_ttl(
    cache: InMemoryTTLCache[str], clock: FakeClock
) -> None:
    await cache.set("k", "old", ttl_seconds=60)
    clock.advance(50)
    await cache.set("k", "new", ttl_seconds=60)
    clock.advance(50)

    assert await cache.get("k") == "new"


async def test_keys_are_independent(cache: InMemoryTTLCache[str], clock: FakeClock) -> None:
    await cache.set("a", "1", ttl_seconds=10)
    await cache.set("b", "2", ttl_seconds=100)
    clock.advance(10)

    assert await cache.get("a") is None
    assert await cache.get("b") == "2"


async def test_zero_ttl_stores_nothing_and_evicts_existing(
    cache: InMemoryTTLCache[str],
) -> None:
    await cache.set("k", "v", ttl_seconds=60)
    await cache.set("k", "v2", ttl_seconds=0)

    assert await cache.get("k") is None


async def test_negative_ttl_is_rejected(cache: InMemoryTTLCache[str]) -> None:
    with pytest.raises(ValueError, match="ttl_seconds"):
        await cache.set("k", "v", ttl_seconds=-1)


def test_rejects_invalid_capacity() -> None:
    with pytest.raises(ValueError, match="max_entries"):
        InMemoryTTLCache[str](max_entries=0)


async def test_full_cache_purges_expired_entries_first(clock: FakeClock) -> None:
    cache = InMemoryTTLCache[str](max_entries=2, clock=clock)
    await cache.set("long", "1", ttl_seconds=100)
    await cache.set("short", "2", ttl_seconds=5)
    clock.advance(5)

    await cache.set("new", "3", ttl_seconds=100)

    assert await cache.get("long") == "1"
    assert await cache.get("new") == "3"
    assert len(cache) == 2


async def test_full_cache_evicts_oldest_write(clock: FakeClock) -> None:
    cache = InMemoryTTLCache[str](max_entries=2, clock=clock)
    await cache.set("a", "1", ttl_seconds=100)
    await cache.set("b", "2", ttl_seconds=100)
    await cache.set("a", "1b", ttl_seconds=100)  # rewrite makes "b" the oldest

    await cache.set("c", "3", ttl_seconds=100)

    assert await cache.get("b") is None
    assert await cache.get("a") == "1b"
    assert await cache.get("c") == "3"
