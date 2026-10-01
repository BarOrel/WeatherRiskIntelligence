import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx

from weather_risk.application.errors import (
    InvalidWeatherDataError,
    WeatherProviderResponseError,
    WeatherProviderTimeoutError,
    WeatherProviderUnavailableError,
)
from weather_risk.application.ports import WeatherProvider
from weather_risk.domain.models import GeoLocation, WeatherDateRange, WeatherHistory
from weather_risk.infrastructure.cache import CacheProvider, cached, location_range_key
from weather_risk.infrastructure.http import ProviderErrors, RetryPolicy, get_with_retry
from weather_risk.infrastructure.weather.open_meteo.mapping import (
    DAILY_VARIABLE_UNITS,
    to_weather_history,
)

ARCHIVE_PATH = "/v1/archive"
HISTORY_CACHE_NAMESPACE = "weather-history:open-meteo:v1"

_ERRORS = ProviderErrors(
    timeout=WeatherProviderTimeoutError,
    unavailable=WeatherProviderUnavailableError,
    response=WeatherProviderResponseError,
)


@dataclass(frozen=True, slots=True)
class OpenMeteoConfig:
    base_url: str
    timeout_seconds: float
    retry_policy: RetryPolicy
    cache_ttl_seconds: int


class OpenMeteoWeatherProvider(WeatherProvider):
    """Historical daily weather from the Open-Meteo archive API.

    The ``httpx.AsyncClient`` and ``CacheProvider`` are injected and owned by the
    composition root.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        cache: CacheProvider[WeatherHistory],
        config: OpenMeteoConfig,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._client = client
        self._cache = cache
        self._config = config
        self._url = config.base_url.rstrip("/") + ARCHIVE_PATH
        self._sleep = sleep

    @cached(
        namespace=HISTORY_CACHE_NAMESPACE,
        ttl=lambda self: self._config.cache_ttl_seconds,
        key_builder=location_range_key,
    )
    async def get_history(
        self, location: GeoLocation, date_range: WeatherDateRange
    ) -> WeatherHistory:
        response = await get_with_retry(
            self._client,
            self._url,
            source="Open-Meteo",
            params=_query_params(location, date_range),
            timeout_seconds=self._config.timeout_seconds,
            retry_policy=self._config.retry_policy,
            errors=_ERRORS,
            sleep=self._sleep,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise InvalidWeatherDataError("Open-Meteo response is not valid JSON") from exc
        return to_weather_history(payload, location, date_range)


def _query_params(location: GeoLocation, date_range: WeatherDateRange) -> dict[str, str]:
    return {
        "latitude": str(location.latitude),
        "longitude": str(location.longitude),
        "start_date": date_range.start.isoformat(),
        "end_date": date_range.end.isoformat(),
        "daily": ",".join(DAILY_VARIABLE_UNITS),
        "timezone": "auto",
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
    }
