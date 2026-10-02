"""Tropical cyclone exposure from NOAA National Hurricane Center HURDAT2 best-track data.

Source: https://www.nhc.noaa.gov/data/#hurdat (machine-readable files under
https://www.nhc.noaa.gov/data/hurdat/). NOAA offers no public query API for historical
tracks, so the provider downloads the official files, caches the parsed dataset, and searches
it locally.
"""

import asyncio
import datetime as dt
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

from weather_risk.application.errors import (
    HazardProviderResponseError,
    HazardProviderTimeoutError,
    HazardProviderUnavailableError,
)
from weather_risk.application.ports import HurricaneHazardProvider
from weather_risk.domain.models import (
    GeoLocation,
    HazardDataSource,
    HurricaneHazardData,
    TropicalCycloneEvent,
    WeatherDateRange,
)
from weather_risk.infrastructure.cache import CacheProvider, cached, location_range_key
from weather_risk.infrastructure.hazards.hurricane.hurdat2 import BestTrackStorm, parse_hurdat2
from weather_risk.infrastructure.hazards.hurricane.proximity import find_events
from weather_risk.infrastructure.http import ProviderErrors, RetryPolicy, get_with_retry

SEARCH_CACHE_NAMESPACE = "hazard:hurricane:noaa:v1"
DATASET_CACHE_NAMESPACE = "hazard:hurricane:noaa:hurdat2:v1"

SOURCE = HazardDataSource(
    name="NOAA National Hurricane Center HURDAT2 best-track data",
    url="https://www.nhc.noaa.gov/data/#hurdat",
)
LIMITATIONS = (
    "Tropical cyclone proximity is a hazard-exposure signal, not a risk score.",
    "Distance is measured to the storm centre; damaging wind, rain and surge can extend "
    "beyond the search radius, and storms outside it can still affect the site.",
    "Best-track positions are 6-hourly; positions between fixes are linearly interpolated.",
    "Covers the North Atlantic and Eastern/Central North Pacific basins only.",
    "Dates and times are UTC.",
)

_ERRORS = ProviderErrors(
    timeout=HazardProviderTimeoutError,
    unavailable=HazardProviderUnavailableError,
    response=HazardProviderResponseError,
)


@dataclass(frozen=True, slots=True)
class NoaaHurricaneConfig:
    dataset_urls: tuple[str, ...]
    timeout_seconds: float
    retry_policy: RetryPolicy
    search_radius_km: float
    cache_ttl_seconds: int
    dataset_ttl_seconds: int


@dataclass(frozen=True, slots=True)
class BestTrackDataset:
    storms: tuple[BestTrackStorm, ...]
    coverage_end: dt.date | None
    """Earliest of the files' last track dates: every basin is covered up to here."""


def _search_key(location: GeoLocation, date_range: WeatherDateRange, radius_km: float) -> str:
    return f"{location_range_key(location, date_range)}&radius_km={radius_km:.3f}"


class NoaaHurricaneHazardProvider(HurricaneHazardProvider):
    def __init__(
        self,
        client: httpx.AsyncClient,
        cache: CacheProvider[Any],
        config: NoaaHurricaneConfig,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._client = client
        self._cache = cache
        self._config = config
        self._sleep = sleep

    async def get_data(
        self, location: GeoLocation, date_range: WeatherDateRange
    ) -> HurricaneHazardData:
        return await self._search(location, date_range, self._config.search_radius_km)

    @cached(
        namespace=SEARCH_CACHE_NAMESPACE,
        ttl=lambda self: self._config.cache_ttl_seconds,
        key_builder=_search_key,
    )
    async def _search(
        self, location: GeoLocation, date_range: WeatherDateRange, radius_km: float
    ) -> HurricaneHazardData:
        dataset = await self._load_dataset(self._config.dataset_urls)
        limitations = LIMITATIONS
        if dataset.coverage_end is not None and date_range.end > dataset.coverage_end:
            limitations += (
                f"NHC best-track data currently covers storms through {dataset.coverage_end}; "
                "later storms are not included yet.",
            )
        return HurricaneHazardData(
            location=location,
            date_range=date_range,
            source=SOURCE,
            limitations=limitations,
            search_radius_km=radius_km,
            data_coverage_end=dataset.coverage_end,
            events=await asyncio.to_thread(_find, dataset.storms, location, date_range, radius_km),
        )

    @cached(namespace=DATASET_CACHE_NAMESPACE, ttl=lambda self: self._config.dataset_ttl_seconds)
    async def _load_dataset(self, urls: tuple[str, ...]) -> BestTrackDataset:
        texts = await asyncio.gather(*(self._download(url) for url in urls))
        # Parsing ~10 MB of best-track text is CPU-bound: keep it off the event loop.
        files = await asyncio.to_thread(lambda: [parse_hurdat2(text) for text in texts])
        ends = [max(storm.end_date for storm in storms) for storms in files if storms]
        return BestTrackDataset(
            storms=tuple(storm for storms in files for storm in storms),
            coverage_end=min(ends) if ends else None,
        )

    async def _download(self, url: str) -> str:
        response = await get_with_retry(
            self._client,
            url,
            source="NOAA NHC HURDAT2",
            timeout_seconds=self._config.timeout_seconds,
            retry_policy=self._config.retry_policy,
            errors=_ERRORS,
            sleep=self._sleep,
        )
        return response.text


def _find(
    storms: tuple[BestTrackStorm, ...],
    location: GeoLocation,
    date_range: WeatherDateRange,
    radius_km: float,
) -> tuple[TropicalCycloneEvent, ...]:
    """CPU-bound proximity search over every track point; run in a worker thread."""
    return tuple(find_events(storms, location, date_range, radius_km))
