"""Caching infrastructure: the CacheProvider abstraction, implementations and ``@cached``."""

from weather_risk.infrastructure.cache.decorator import cached
from weather_risk.infrastructure.cache.in_memory_ttl_cache import InMemoryTTLCache
from weather_risk.infrastructure.cache.keys import (
    canonicalize,
    digest,
    join_key_parts,
    location_range_key,
)
from weather_risk.infrastructure.cache.provider import CacheProvider
from weather_risk.infrastructure.cache.single_flight import SingleFlight

__all__ = [
    "CacheProvider",
    "InMemoryTTLCache",
    "SingleFlight",
    "cached",
    "canonicalize",
    "digest",
    "join_key_parts",
    "location_range_key",
]
