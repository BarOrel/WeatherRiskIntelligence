"""Flood exposure from the Open-Meteo Flood API (GloFAS river discharge).

API: https://open-meteo.com/en/docs/flood-api
"""

import asyncio
import datetime as dt
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from weather_risk.application.errors import (
    HazardProviderResponseError,
    HazardProviderTimeoutError,
    HazardProviderUnavailableError,
    InvalidHazardDataError,
)
from weather_risk.application.ports import FloodHazardProvider
from weather_risk.domain.errors import DomainValidationError
from weather_risk.domain.models import (
    DailyRiverDischarge,
    FloodHazardData,
    GeoLocation,
    HazardDataSource,
    WeatherDateRange,
)
from weather_risk.infrastructure.cache import CacheProvider, cached, location_range_key
from weather_risk.infrastructure.http import ProviderErrors, RetryPolicy, get_with_retry

FLOOD_PATH = "/v1/flood"
CACHE_NAMESPACE = "hazard:flood:open-meteo:v1"
DISCHARGE_UNIT = "m³/s"

SOURCE = HazardDataSource(
    name="Open-Meteo Flood API (Copernicus GloFAS river discharge)",
    url="https://open-meteo.com/en/docs/flood-api",
)
LIMITATIONS = (
    "River discharge is a flood-exposure signal, not a flood probability or risk score.",
    "Values are for the nearest modelled river grid cell (about 5 km resolution), which may "
    "not be the river closest to the site; see cell_location.",
    "Does not account for urban drainage, pluvial (rainfall) flooding, storm surge, building "
    "elevation, local topography or infrastructure resilience.",
    "Daily values are modelled reanalysis/forecast data, not gauge measurements.",
)

_ERRORS = ProviderErrors(
    timeout=HazardProviderTimeoutError,
    unavailable=HazardProviderUnavailableError,
    response=HazardProviderResponseError,
)


@dataclass(frozen=True, slots=True)
class OpenMeteoFloodConfig:
    base_url: str
    timeout_seconds: float
    retry_policy: RetryPolicy
    cache_ttl_seconds: int


class OpenMeteoFloodHazardProvider(FloodHazardProvider):
    def __init__(
        self,
        client: httpx.AsyncClient,
        cache: CacheProvider[Any],
        config: OpenMeteoFloodConfig,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._client = client
        self._cache = cache
        self._config = config
        self._url = config.base_url.rstrip("/") + FLOOD_PATH
        self._sleep = sleep

    @cached(
        namespace=CACHE_NAMESPACE,
        ttl=lambda self: self._config.cache_ttl_seconds,
        key_builder=location_range_key,
    )
    async def get_data(
        self, location: GeoLocation, date_range: WeatherDateRange
    ) -> FloodHazardData:
        response = await get_with_retry(
            self._client,
            self._url,
            source="Open-Meteo Flood API",
            params={
                "latitude": str(location.latitude),
                "longitude": str(location.longitude),
                "start_date": date_range.start.isoformat(),
                "end_date": date_range.end.isoformat(),
                "daily": "river_discharge",
            },
            timeout_seconds=self._config.timeout_seconds,
            retry_policy=self._config.retry_policy,
            errors=_ERRORS,
            sleep=self._sleep,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise InvalidHazardDataError("Flood API response is not valid JSON") from exc
        return to_flood_hazard_data(payload, location, date_range)


class _Daily(BaseModel):
    time: list[dt.date]
    river_discharge: list[float | None]


class _FloodResponse(BaseModel):
    latitude: float
    longitude: float
    daily_units: dict[str, str] | None = None
    daily: _Daily


def to_flood_hazard_data(
    payload: Any, location: GeoLocation, date_range: WeatherDateRange
) -> FloodHazardData:
    try:
        response = _FloodResponse.model_validate(payload)
    except ValidationError as exc:
        raise InvalidHazardDataError(
            f"Flood API response has an unexpected shape ({exc.error_count()} errors)"
        ) from exc

    unit = (response.daily_units or {}).get("river_discharge", DISCHARGE_UNIT)
    if unit != DISCHARGE_UNIT:
        raise InvalidHazardDataError(f"Flood API returned discharge in '{unit}'")

    daily = response.daily
    if len(daily.river_discharge) != len(daily.time):
        raise InvalidHazardDataError(
            f"Flood API returned {len(daily.river_discharge)} values for {len(daily.time)} days"
        )
    if daily.time != date_range.dates():
        raise InvalidHazardDataError(
            f"Flood API days do not match the requested range {date_range.start}..{date_range.end}"
        )

    try:
        return FloodHazardData(
            location=location,
            date_range=date_range,
            source=SOURCE,
            limitations=LIMITATIONS,
            cell_location=GeoLocation(response.latitude, response.longitude),
            observations=tuple(
                DailyRiverDischarge(date=day, discharge_m3s=value)
                for day, value in zip(daily.time, daily.river_discharge, strict=True)
            ),
        )
    except DomainValidationError as exc:
        raise InvalidHazardDataError(f"Flood API returned invalid values: {exc}") from exc
