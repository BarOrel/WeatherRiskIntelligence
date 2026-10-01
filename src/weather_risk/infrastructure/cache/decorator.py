"""``@cached``: a reusable read-through cache for async methods.

The cache itself is never created or looked up globally. It is resolved from the decorated
instance, which received it through constructor injection (by default ``self._cache``).
"""

import functools
import inspect
import logging
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, Concatenate, ParamSpec, TypeVar

from weather_risk.infrastructure.cache.keys import digest
from weather_risk.infrastructure.cache.single_flight import SingleFlight
from weather_risk.infrastructure.cache.provider import CacheProvider

logger = logging.getLogger(__name__)

S = TypeVar("S")
P = ParamSpec("P")
R = TypeVar("R")

AsyncMethod = Callable[Concatenate[S, P], Awaitable[R]]
CachedMethod = Callable[Concatenate[S, P], Coroutine[Any, Any, R]]

DEFAULT_CACHE_ATTRIBUTE = "_cache"


def cached(
    namespace: str,
    ttl: int | Callable[[Any], int],
    key_builder: Callable[..., str] | None = None,
    cache: Callable[[Any], CacheProvider[Any]] | None = None,
    single_flight: bool = True,
) -> Callable[[AsyncMethod[S, P, R]], CachedMethod[S, P, R]]:
    """Cache successful results of an async method.

    Args:
        namespace: Key prefix; must be unique per cached method. Include a version
            (e.g. ``"weather-history:v1"``) to invalidate entries when the result shape changes.
        ttl: Seconds, or ``lambda self: ...`` resolved on every call (e.g. from injected
            settings). ``0`` disables caching; negative or non-integer values raise ValueError.
        key_builder: Called with the method's arguments (without ``self``) and returns the key
            segment after the namespace. Defaults to a SHA-256 digest of all bound arguments.
        cache: ``lambda self: ...`` returning the injected CacheProvider.
            Defaults to ``self._cache``.
        single_flight: Coalesce concurrent identical misses into one execution.

    Exceptions are never cached. ``None`` results are not cached, because a cache returns
    ``None`` for a miss.
    """
    if not namespace.strip():
        raise ValueError("namespace must not be blank")
    if not callable(ttl):
        _validate_ttl(ttl)

    def decorator(func: AsyncMethod[S, P, R]) -> CachedMethod[S, P, R]:
        if not inspect.iscoroutinefunction(func):
            raise TypeError(f"@cached requires an async function, got {func.__qualname__}")

        signature = inspect.signature(func)
        self_name = next(iter(signature.parameters))
        function_id = f"{func.__module__}.{func.__qualname__}"
        flights: SingleFlight[R] = SingleFlight()

        def build_key(instance: S, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
            if key_builder is not None:
                return f"{namespace}:{key_builder(*args, **kwargs)}"
            bound = signature.bind(instance, *args, **kwargs)
            bound.apply_defaults()
            arguments = {k: v for k, v in bound.arguments.items() if k != self_name}
            return f"{namespace}:{digest([function_id, arguments])}"

        @functools.wraps(func)
        async def wrapper(self: S, *args: P.args, **kwargs: P.kwargs) -> R:
            ttl_seconds = _validate_ttl(ttl(self) if callable(ttl) else ttl)
            if ttl_seconds == 0:
                return await func(self, *args, **kwargs)

            provider = _resolve_cache(self, cache)
            key = build_key(self, args, kwargs)

            hit = await _read(provider, key)
            if hit is not None:
                logger.debug("Cache HIT %s", key)
                return hit

            async def load() -> R:
                # Re-check: a flight for this key may have completed since the first read.
                hit = await _read(provider, key)
                if hit is not None:
                    logger.debug("Cache HIT %s", key)
                    return hit
                logger.debug("Cache MISS %s", key)
                result = await func(self, *args, **kwargs)
                if result is not None:
                    await _write(provider, key, result, ttl_seconds)
                return result

            if not single_flight:
                return await load()
            # id(provider) is stable while the flight runs: load() holds a reference to it.
            return await flights.run((id(provider), key), load)

        return wrapper

    return decorator


def _validate_ttl(ttl_seconds: object) -> int:
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or ttl_seconds < 0:
        raise ValueError(f"Cache TTL must be a non-negative int, got {ttl_seconds!r}")
    return ttl_seconds


def _resolve_cache(
    instance: object, resolver: Callable[[Any], CacheProvider[Any]] | None
) -> CacheProvider[Any]:
    if resolver is not None:
        provider = resolver(instance)
    else:
        provider = getattr(instance, DEFAULT_CACHE_ATTRIBUTE, None)
    if not isinstance(provider, CacheProvider):
        raise TypeError(
            f"{type(instance).__qualname__} has no injected CacheProvider "
            f"(expected '{DEFAULT_CACHE_ATTRIBUTE}' or a cache= resolver)"
        )
    return provider


async def _read(provider: CacheProvider[Any], key: str) -> Any:
    try:
        return await provider.get(key)
    except Exception:
        logger.warning("Cache read failed for %s; bypassing cache", key, exc_info=True)
        return None


async def _write(provider: CacheProvider[Any], key: str, value: Any, ttl_seconds: int) -> None:
    try:
        await provider.set(key, value, ttl_seconds)
    except Exception:
        logger.warning("Cache write failed for %s", key, exc_info=True)
