import datetime as dt
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
from support.fakes import DENVER

from weather_risk.application.errors import (
    InvalidWeatherDataError,
    WeatherProviderResponseError,
    WeatherProviderTimeoutError,
    WeatherProviderUnavailableError,
)
from weather_risk.domain.models import GeoLocation, WeatherDateRange, WeatherHistory
from weather_risk.infrastructure.cache import CacheProvider, InMemoryTTLCache, location_range_key
from weather_risk.infrastructure.http import RetryPolicy
from weather_risk.infrastructure.weather import (
    OpenMeteoConfig,
    OpenMeteoWeatherProvider,
)

BASE_URL = "https://archive.test"
RANGE = WeatherDateRange(dt.date(2024, 1, 1), dt.date(2024, 1, 2))
VARIABLES = (
    "precipitation_sum",
    "rain_sum",
    "snowfall_sum",
    "temperature_2m_max",
    "temperature_2m_min",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
)

Handler = Callable[[httpx.Request], httpx.Response]


def archive_payload(**daily_overrides: Any) -> dict[str, Any]:
    daily: dict[str, Any] = {
        "time": ["2024-01-01", "2024-01-02"],
        "precipitation_sum": [0.0, 5.4],
        "rain_sum": [0.0, 1.1],
        "snowfall_sum": [0.0, 3.08],
        "temperature_2m_max": [8.1, -2.3],
        "temperature_2m_min": [-6.4, -9.9],
        "wind_speed_10m_max": [14.2, 31.0],
        "wind_gusts_10m_max": [30.6, None],
    }
    daily.update(daily_overrides)
    return {
        "latitude": 39.73,
        "longitude": -104.99,
        "timezone": "America/Denver",
        "daily_units": {
            "time": "iso8601",
            "precipitation_sum": "mm",
            "rain_sum": "mm",
            "snowfall_sum": "cm",
            "temperature_2m_max": "°C",
            "temperature_2m_min": "°C",
            "wind_speed_10m_max": "km/h",
            "wind_gusts_10m_max": "km/h",
        },
        "daily": daily,
    }


class Recorder:
    """Mock transport handler that replays queued responses/exceptions in order."""

    def __init__(self, *outcomes: httpx.Response | Exception) -> None:
        self.requests: list[httpx.Request] = []
        self._outcomes = list(outcomes)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        outcome = self._outcomes.pop(0) if len(self._outcomes) > 1 else self._outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
async def client_factory() -> AsyncIterator[Callable[[Handler], httpx.AsyncClient]]:
    clients: list[httpx.AsyncClient] = []

    def factory(handler: Handler) -> httpx.AsyncClient:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        clients.append(client)
        return client

    yield factory
    for client in clients:
        await client.aclose()


@pytest.fixture
def make_provider(
    client_factory: Callable[[Handler], httpx.AsyncClient], sleeps: list[float]
) -> Callable[..., OpenMeteoWeatherProvider]:
    async def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    def factory(
        handler: Handler,
        max_retries: int = 2,
        cache: CacheProvider[WeatherHistory] | None = None,
        cache_ttl_seconds: int = 1800,
    ) -> OpenMeteoWeatherProvider:
        return OpenMeteoWeatherProvider(
            client=client_factory(handler),
            cache=cache if cache is not None else InMemoryTTLCache[WeatherHistory](10),
            config=OpenMeteoConfig(
                base_url=BASE_URL,
                timeout_seconds=5.0,
                retry_policy=RetryPolicy(max_retries=max_retries, backoff_seconds=0.1),
                cache_ttl_seconds=cache_ttl_seconds,
            ),
            sleep=record_sleep,
        )

    return factory


async def test_sends_expected_query(make_provider: Callable[..., OpenMeteoWeatherProvider]) -> None:
    recorder = Recorder(httpx.Response(200, json=archive_payload()))

    await make_provider(recorder).get_history(DENVER, RANGE)

    request = recorder.requests[0]
    assert str(request.url).startswith(f"{BASE_URL}/v1/archive?")
    assert dict(request.url.params) == {
        "latitude": "39.7392",
        "longitude": "-104.9903",
        "start_date": "2024-01-01",
        "end_date": "2024-01-02",
        "daily": (
            "precipitation_sum,rain_sum,snowfall_sum,temperature_2m_max,"
            "temperature_2m_min,wind_speed_10m_max,wind_gusts_10m_max"
        ),
        "timezone": "auto",
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
    }


async def test_maps_response_to_weather_history(
    make_provider: Callable[..., OpenMeteoWeatherProvider],
) -> None:
    recorder = Recorder(httpx.Response(200, json=archive_payload()))

    history = await make_provider(recorder).get_history(DENVER, RANGE)

    assert history.location == DENVER
    assert history.date_range == RANGE
    assert history.timezone == "America/Denver"
    second = history.observations[1]
    assert second.date == dt.date(2024, 1, 2)
    assert second.precipitation_mm == 5.4
    assert second.rain_mm == 1.1
    assert second.snowfall_cm == 3.08
    assert second.temperature_max_c == -2.3
    assert second.temperature_min_c == -9.9
    assert second.wind_speed_max_kmh == 31.0
    assert second.wind_gust_max_kmh is None


@pytest.mark.parametrize(
    "payload",
    [
        {"error": True, "reason": "nope"},
        {"timezone": "UTC", "daily": {"time": ["2024-01-01"]}},
        archive_payload(rain_sum=[0.0]),
        archive_payload(time=["2024-01-01", "2024-01-03"]),
        archive_payload(**{variable: [0.0] for variable in VARIABLES}, time=["2024-01-01"]),
        archive_payload(rain_sum=["lots", 1.0]),
        archive_payload(wind_speed_10m_max=[-1.0, 2.0]),
        archive_payload(temperature_2m_min=[20.0, -9.9]),
        [],
    ],
    ids=[
        "error-body",
        "missing-variables",
        "length-mismatch",
        "wrong-dates",
        "incomplete-range",
        "non-numeric",
        "negative-wind",
        "min-above-max",
        "not-an-object",
    ],
)
async def test_malformed_response_raises_invalid_data(
    make_provider: Callable[..., OpenMeteoWeatherProvider], payload: Any
) -> None:
    recorder = Recorder(httpx.Response(200, json=payload))

    with pytest.raises(InvalidWeatherDataError):
        await make_provider(recorder).get_history(DENVER, RANGE)


async def test_unexpected_units_raise_invalid_data(
    make_provider: Callable[..., OpenMeteoWeatherProvider],
) -> None:
    payload = archive_payload()
    payload["daily_units"]["temperature_2m_max"] = "°F"

    with pytest.raises(InvalidWeatherDataError, match="units"):
        await make_provider(Recorder(httpx.Response(200, json=payload))).get_history(
            DENVER, RANGE
        )


async def test_non_json_body_raises_invalid_data(
    make_provider: Callable[..., OpenMeteoWeatherProvider],
) -> None:
    recorder = Recorder(httpx.Response(200, text="<html>oops</html>"))

    with pytest.raises(InvalidWeatherDataError, match="JSON"):
        await make_provider(recorder).get_history(DENVER, RANGE)


async def test_client_error_is_not_retried(
    make_provider: Callable[..., OpenMeteoWeatherProvider], sleeps: list[float]
) -> None:
    recorder = Recorder(
        httpx.Response(400, json={"error": True, "reason": "Parameter 'start_date' is out of range"})
    )

    with pytest.raises(WeatherProviderResponseError, match="out of range") as exc_info:
        await make_provider(recorder).get_history(DENVER, RANGE)

    assert exc_info.value.status_code == 400
    assert len(recorder.requests) == 1
    assert sleeps == []


@pytest.mark.parametrize(
    ("outcome", "error_type"),
    [
        (httpx.Response(503), WeatherProviderResponseError),
        (httpx.Response(429), WeatherProviderResponseError),
        (httpx.ReadTimeout("slow"), WeatherProviderTimeoutError),
        (httpx.ConnectError("refused"), WeatherProviderUnavailableError),
    ],
)
async def test_transient_failures_are_retried_then_raised(
    make_provider: Callable[..., OpenMeteoWeatherProvider],
    sleeps: list[float],
    outcome: httpx.Response | Exception,
    error_type: type[Exception],
) -> None:
    recorder = Recorder(outcome)

    with pytest.raises(error_type):
        await make_provider(recorder, max_retries=2).get_history(DENVER, RANGE)

    assert len(recorder.requests) == 3
    assert sleeps == [0.1, 0.2]


async def test_recovers_when_retry_succeeds(
    make_provider: Callable[..., OpenMeteoWeatherProvider], sleeps: list[float]
) -> None:
    recorder = Recorder(
        httpx.ConnectError("refused"),
        httpx.Response(502),
        httpx.Response(200, json=archive_payload()),
    )

    history = await make_provider(recorder).get_history(DENVER, RANGE)

    assert len(history.observations) == 2
    assert len(recorder.requests) == 3
    assert sleeps == [0.1, 0.2]


async def test_zero_retries_makes_a_single_attempt(
    make_provider: Callable[..., OpenMeteoWeatherProvider], sleeps: list[float]
) -> None:
    recorder = Recorder(httpx.ConnectError("refused"))

    with pytest.raises(WeatherProviderUnavailableError):
        await make_provider(recorder, max_retries=0).get_history(DENVER, RANGE)

    assert len(recorder.requests) == 1
    assert sleeps == []


async def test_httpx_exceptions_do_not_leak(
    make_provider: Callable[..., OpenMeteoWeatherProvider],
) -> None:
    recorder = Recorder(httpx.ConnectError("refused"))

    with pytest.raises(WeatherProviderUnavailableError) as exc_info:
        await make_provider(recorder, max_retries=0).get_history(DENVER, RANGE)

    assert not isinstance(exc_info.value, httpx.HTTPError)
    assert isinstance(exc_info.value.__cause__, httpx.ConnectError)


class TestCaching:
    async def test_uses_injected_cache_and_skips_http_on_hit(
        self, make_provider: Callable[..., OpenMeteoWeatherProvider]
    ) -> None:
        cache = InMemoryTTLCache[WeatherHistory](10)
        recorder = Recorder(httpx.Response(200, json=archive_payload()))
        provider = make_provider(recorder, cache=cache)

        first = await provider.get_history(DENVER, RANGE)
        second = await provider.get_history(DENVER, RANGE)

        assert second is first
        assert len(recorder.requests) == 1
        key = "weather-history:open-meteo:v1:" + location_range_key(DENVER, RANGE)
        assert await cache.get(key) is first

    async def test_different_date_range_is_a_different_entry(
        self, make_provider: Callable[..., OpenMeteoWeatherProvider]
    ) -> None:
        cache = InMemoryTTLCache[WeatherHistory](10)
        later = WeatherDateRange(dt.date(2024, 1, 2), dt.date(2024, 1, 3))
        recorder = Recorder(
            httpx.Response(200, json=archive_payload()),
            httpx.Response(200, json=archive_payload(time=["2024-01-02", "2024-01-03"])),
        )
        provider = make_provider(recorder, cache=cache)

        await provider.get_history(DENVER, RANGE)
        await provider.get_history(DENVER, later)

        assert len(recorder.requests) == 2
        assert len(cache) == 2

    async def test_failures_are_not_cached(
        self, make_provider: Callable[..., OpenMeteoWeatherProvider]
    ) -> None:
        cache = InMemoryTTLCache[WeatherHistory](10)
        recorder = Recorder(httpx.Response(400), httpx.Response(200, json=archive_payload()))
        provider = make_provider(recorder, cache=cache)

        with pytest.raises(WeatherProviderResponseError):
            await provider.get_history(DENVER, RANGE)
        assert len(cache) == 0

        await provider.get_history(DENVER, RANGE)
        assert len(recorder.requests) == 2
        assert len(cache) == 1

    async def test_ttl_comes_from_injected_config(
        self, make_provider: Callable[..., OpenMeteoWeatherProvider]
    ) -> None:
        recorder = Recorder(httpx.Response(200, json=archive_payload()))
        provider = make_provider(recorder, cache_ttl_seconds=0)

        await provider.get_history(DENVER, RANGE)
        await provider.get_history(DENVER, RANGE)

        assert len(recorder.requests) == 2

    def test_cache_key_contains_coordinates_and_dates(self) -> None:
        assert location_range_key(DENVER, RANGE) == (
            "end=2024-01-02&lat=39.739200&lon=-104.990300&start=2024-01-01"
        )
        assert location_range_key(
            GeoLocation(-0.0, -0.0), RANGE
        ) == location_range_key(GeoLocation(0.0, 0.0), RANGE)
