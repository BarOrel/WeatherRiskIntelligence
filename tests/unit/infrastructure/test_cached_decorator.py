import asyncio
import datetime as dt
from dataclasses import dataclass, field
from typing import Any

import pytest
from support.fakes import FakeClock

from weather_risk.infrastructure.cache import CacheProvider, InMemoryTTLCache, cached

TTL = 60


@dataclass
class Settings:
    ttl_seconds: int = TTL


class Service:
    """A plain class with an injected cache, like any adapter would have."""

    def __init__(self, cache: CacheProvider[Any], settings: Settings | None = None) -> None:
        self._cache = cache
        self._settings = settings or Settings()
        self.calls: list[tuple[Any, ...]] = []
        self.errors: list[Exception] = []
        self.gate: asyncio.Event | None = None

    @cached(namespace="square", ttl=lambda self: self._settings.ttl_seconds)
    async def square(self, x: int, label: str = "default") -> dict[str, Any]:
        """Square a number."""
        self.calls.append((x, label))
        if self.gate is not None:
            await self.gate.wait()
        if self.errors:
            raise self.errors.pop(0)
        return {"value": x * x, "label": label}

    @cached(namespace="echo", ttl=TTL, key_builder=lambda day: f"day={day.isoformat()}")
    async def echo_day(self, day: dt.date) -> str:
        self.calls.append((day,))
        return day.isoformat()

    @cached(namespace="nothing", ttl=TTL)
    async def nothing(self) -> None:
        self.calls.append(())


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def cache(clock: FakeClock) -> InMemoryTTLCache[Any]:
    return InMemoryTTLCache[Any](max_entries=100, clock=clock)


@pytest.fixture
def service(cache: InMemoryTTLCache[Any]) -> Service:
    return Service(cache)


async def test_miss_executes_method_and_returns_result(service: Service) -> None:
    assert await service.square(3) == {"value": 9, "label": "default"}
    assert service.calls == [(3, "default")]


async def test_identical_call_is_a_hit(service: Service) -> None:
    first = await service.square(3)
    second = await service.square(3)

    assert second == first
    assert len(service.calls) == 1


async def test_equivalent_arguments_share_one_entry(service: Service) -> None:
    await service.square(3)
    await service.square(x=3)
    await service.square(3, "default")
    await service.square(label="default", x=3)

    assert len(service.calls) == 1


async def test_different_arguments_use_different_entries(
    service: Service, cache: InMemoryTTLCache[Any]
) -> None:
    await service.square(3)
    await service.square(4)
    await service.square(3, "other")

    assert len(service.calls) == 3
    assert len(cache) == 3


async def test_expired_entry_executes_again(service: Service, clock: FakeClock) -> None:
    await service.square(3)
    clock.advance(TTL)
    await service.square(3)

    assert len(service.calls) == 2


async def test_dynamic_ttl_is_read_on_each_call(cache: InMemoryTTLCache[Any], clock: FakeClock) -> None:
    settings = Settings(ttl_seconds=10)
    service = Service(cache, settings)

    await service.square(1)
    clock.advance(10)
    settings.ttl_seconds = 100
    await service.square(1)  # expired under the old TTL -> re-cached with the new one
    clock.advance(50)
    await service.square(1)

    assert len(service.calls) == 2


async def test_zero_ttl_disables_caching(cache: InMemoryTTLCache[Any]) -> None:
    service = Service(cache, Settings(ttl_seconds=0))

    await service.square(1)
    await service.square(1)

    assert len(service.calls) == 2
    assert len(cache) == 0


@pytest.mark.parametrize("bad_ttl", [-1, 1.5, "60", True])
async def test_invalid_dynamic_ttl_is_rejected(
    cache: InMemoryTTLCache[Any], bad_ttl: Any
) -> None:
    service = Service(cache, Settings(ttl_seconds=bad_ttl))

    with pytest.raises(ValueError, match="TTL"):
        await service.square(1)
    assert service.calls == []


@pytest.mark.parametrize("bad_ttl", [-1, 2.5, None])
def test_invalid_static_ttl_is_rejected_at_decoration(bad_ttl: Any) -> None:
    with pytest.raises(ValueError, match="TTL"):
        cached(namespace="x", ttl=bad_ttl)


def test_blank_namespace_is_rejected() -> None:
    with pytest.raises(ValueError, match="namespace"):
        cached(namespace="  ", ttl=1)


def test_rejects_sync_functions() -> None:
    with pytest.raises(TypeError, match="async"):

        @cached(namespace="x", ttl=1)
        def sync(self: object) -> int:
            return 1


async def test_exceptions_are_not_cached(service: Service, cache: InMemoryTTLCache[Any]) -> None:
    service.errors.append(RuntimeError("boom"))

    with pytest.raises(RuntimeError):
        await service.square(2)
    assert len(cache) == 0

    assert await service.square(2) == {"value": 4, "label": "default"}
    assert len(service.calls) == 2


async def test_none_results_are_not_cached(service: Service) -> None:
    await service.nothing()
    await service.nothing()

    assert len(service.calls) == 2


async def test_custom_key_builder(service: Service, cache: InMemoryTTLCache[Any]) -> None:
    await service.echo_day(dt.date(2024, 1, 1))
    await service.echo_day(day=dt.date(2024, 1, 1))

    assert len(service.calls) == 1
    assert await cache.get("echo:day=2024-01-01") == "2024-01-01"


def test_metadata_is_preserved() -> None:
    assert Service.square.__name__ == "square"
    assert Service.square.__doc__ == "Square a number."
    assert Service.square.__qualname__ == "Service.square"
    assert Service.square.__wrapped__ is not None  # type: ignore[attr-defined]


async def test_each_instance_uses_its_own_injected_cache(clock: FakeClock) -> None:
    cache_a = InMemoryTTLCache[Any](10, clock=clock)
    cache_b = InMemoryTTLCache[Any](10, clock=clock)
    a, b = Service(cache_a), Service(cache_b)

    await a.square(5)
    await b.square(5)

    assert len(a.calls) == len(b.calls) == 1
    assert len(cache_a) == len(cache_b) == 1


async def test_custom_cache_resolver() -> None:
    class Holder:
        def __init__(self, store: CacheProvider[Any]) -> None:
            self.store = store
            self.calls = 0

        @cached(namespace="h", ttl=TTL, cache=lambda self: self.store)
        async def value(self) -> int:
            self.calls += 1
            return 42

    holder = Holder(InMemoryTTLCache[Any](10))
    assert await holder.value() == await holder.value() == 42
    assert holder.calls == 1


async def test_missing_cache_dependency_fails_clearly() -> None:
    class NoCache:
        @cached(namespace="n", ttl=TTL)
        async def value(self) -> int:
            return 1

    with pytest.raises(TypeError, match="no injected CacheProvider"):
        await NoCache().value()


async def test_unsupported_argument_type_fails_clearly(service: Service) -> None:
    with pytest.raises(TypeError, match="key_builder"):
        await service.square(object())  # type: ignore[arg-type]


@dataclass
class BrokenCache(CacheProvider[Any]):
    reads: int = field(default=0)

    async def get(self, key: str) -> Any:
        self.reads += 1
        raise ConnectionError("cache down")

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        raise ConnectionError("cache down")


async def test_broken_cache_is_bypassed() -> None:
    service = Service(BrokenCache())

    assert await service.square(2) == {"value": 4, "label": "default"}
    assert len(service.calls) == 1


class TestSingleFlight:
    async def test_concurrent_identical_misses_execute_once(self, service: Service) -> None:
        service.gate = asyncio.Event()
        callers = [asyncio.create_task(service.square(7)) for _ in range(20)]
        await asyncio.sleep(0)  # let every caller reach the cache/flight
        service.gate.set()

        results = await asyncio.gather(*callers)

        assert len(service.calls) == 1
        assert all(result == {"value": 49, "label": "default"} for result in results)

    async def test_concurrent_different_keys_run_independently(self, service: Service) -> None:
        service.gate = asyncio.Event()
        callers = [asyncio.create_task(service.square(n)) for n in range(5)]
        await asyncio.sleep(0)
        service.gate.set()

        await asyncio.gather(*callers)

        assert len(service.calls) == 5

    async def test_concurrent_callers_share_a_failure_which_is_not_cached(
        self, service: Service
    ) -> None:
        service.gate = asyncio.Event()
        service.errors.append(RuntimeError("upstream down"))
        callers = [asyncio.create_task(service.square(7)) for _ in range(5)]
        await asyncio.sleep(0)
        service.gate.set()

        results = await asyncio.gather(*callers, return_exceptions=True)

        assert all(isinstance(r, RuntimeError) for r in results)
        assert len(service.calls) == 1
        assert await service.square(7) == {"value": 49, "label": "default"}
        assert len(service.calls) == 2

    async def test_cancelled_caller_does_not_cancel_shared_work(self, service: Service) -> None:
        service.gate = asyncio.Event()
        first = asyncio.create_task(service.square(7))
        second = asyncio.create_task(service.square(7))
        await asyncio.sleep(0)

        first.cancel()
        service.gate.set()

        assert await second == {"value": 49, "label": "default"}
        assert first.cancelled()
        assert len(service.calls) == 1
