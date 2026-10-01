import datetime as dt
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
from support.fakes import DENVER
from support.http import Recorder, no_sleep

from weather_risk.application.errors import (
    HazardProviderResponseError,
    HazardProviderTimeoutError,
    HazardProviderUnavailableError,
    InvalidHazardDataError,
)
from weather_risk.domain.models import FloodHazardData, GeoLocation, WeatherDateRange
from weather_risk.infrastructure.cache import InMemoryTTLCache
from weather_risk.infrastructure.hazards.flood import (
    OpenMeteoFloodConfig,
    OpenMeteoFloodHazardProvider,
)
from weather_risk.infrastructure.http import RetryPolicy

BASE_URL = "https://flood.test"
RANGE = WeatherDateRange(dt.date(2017, 8, 26), dt.date(2017, 8, 28))
HOUSTON = GeoLocation(29.7604, -95.3698)


def flood_payload(**daily_overrides: Any) -> dict[str, Any]:
    daily: dict[str, Any] = {
        "time": ["2017-08-26", "2017-08-27", "2017-08-28"],
        "river_discharge": [235.59, 589.2, None],
    }
    daily.update(daily_overrides)
    return {
        "latitude": 29.775002,
        "longitude": -95.37499,
        "daily_units": {"time": "iso8601", "river_discharge": "m³/s"},
        "daily": daily,
    }


MakeProvider = Callable[..., OpenMeteoFloodHazardProvider]


@pytest.fixture
async def make_provider() -> AsyncIterator[MakeProvider]:
    clients: list[httpx.AsyncClient] = []

    def factory(
        recorder: Recorder,
        cache: InMemoryTTLCache[Any] | None = None,
        max_retries: int = 1,
        ttl: int = 600,
    ) -> OpenMeteoFloodHazardProvider:
        client = httpx.AsyncClient(transport=httpx.MockTransport(recorder))
        clients.append(client)
        return OpenMeteoFloodHazardProvider(
            client=client,
            cache=cache if cache is not None else InMemoryTTLCache[Any](10),
            config=OpenMeteoFloodConfig(
                base_url=BASE_URL,
                timeout_seconds=5.0,
                retry_policy=RetryPolicy(max_retries=max_retries, backoff_seconds=0),
                cache_ttl_seconds=ttl,
            ),
            sleep=no_sleep,
        )

    yield factory
    for client in clients:
        await client.aclose()


async def test_sends_expected_query(make_provider: MakeProvider) -> None:
    recorder = Recorder(httpx.Response(200, json=flood_payload()))

    await make_provider(recorder).get_data(HOUSTON, RANGE)

    request = recorder.requests[0]
    assert str(request.url.copy_with(query=None)) == f"{BASE_URL}/v1/flood"
    assert dict(request.url.params) == {
        "latitude": "29.7604",
        "longitude": "-95.3698",
        "start_date": "2017-08-26",
        "end_date": "2017-08-28",
        "daily": "river_discharge",
    }


async def test_maps_response(make_provider: MakeProvider) -> None:
    recorder = Recorder(httpx.Response(200, json=flood_payload()))

    data = await make_provider(recorder).get_data(HOUSTON, RANGE)

    assert isinstance(data, FloodHazardData)
    assert data.location == HOUSTON
    assert data.cell_location == GeoLocation(29.775002, -95.37499)
    assert data.date_range == RANGE
    assert [(o.date.isoformat(), o.discharge_m3s) for o in data.observations] == [
        ("2017-08-26", 235.59),
        ("2017-08-27", 589.2),
        ("2017-08-28", None),
    ]
    assert "Open-Meteo" in data.source.name
    assert any("not a flood probability" in text for text in data.limitations)
    assert not hasattr(data, "score")


@pytest.mark.parametrize(
    "payload",
    [
        {"error": True, "reason": "nope"},
        flood_payload(river_discharge=[1.0]),
        flood_payload(time=["2017-08-26", "2017-08-27", "2017-08-29"]),
        flood_payload(river_discharge=[1.0, -5.0, 2.0]),
        flood_payload(river_discharge=["high", 1.0, 2.0]),
        {**flood_payload(), "daily_units": {"river_discharge": "ft³/s"}},
        [],
    ],
    ids=["error-body", "length", "dates", "negative", "non-numeric", "units", "not-object"],
)
async def test_malformed_response(make_provider: MakeProvider, payload: Any) -> None:
    with pytest.raises(InvalidHazardDataError):
        await make_provider(Recorder(httpx.Response(200, json=payload))).get_data(HOUSTON, RANGE)


async def test_non_json_body(make_provider: MakeProvider) -> None:
    with pytest.raises(InvalidHazardDataError, match="JSON"):
        await make_provider(Recorder(httpx.Response(200, text="<html>"))).get_data(HOUSTON, RANGE)


@pytest.mark.parametrize(
    ("outcome", "error_type"),
    [
        (httpx.ReadTimeout("slow"), HazardProviderTimeoutError),
        (httpx.ConnectError("refused"), HazardProviderUnavailableError),
        (httpx.Response(503), HazardProviderResponseError),
        (httpx.Response(400, json={"reason": "bad"}), HazardProviderResponseError),
    ],
)
async def test_failures_map_to_hazard_errors(
    make_provider: MakeProvider, outcome: Any, error_type: type[Exception]
) -> None:
    with pytest.raises(error_type) as exc_info:
        await make_provider(Recorder(outcome)).get_data(HOUSTON, RANGE)

    assert not isinstance(exc_info.value, httpx.HTTPError)


class TestCaching:
    async def test_repeat_request_is_served_from_injected_cache(
        self, make_provider: MakeProvider
    ) -> None:
        cache = InMemoryTTLCache[Any](10)
        recorder = Recorder(httpx.Response(200, json=flood_payload()))
        provider = make_provider(recorder, cache=cache)

        first = await provider.get_data(HOUSTON, RANGE)
        second = await provider.get_data(HOUSTON, RANGE)

        assert second is first
        assert len(recorder.requests) == 1
        assert len(cache) == 1

    async def test_different_location_or_range_are_separate_entries(
        self, make_provider: MakeProvider
    ) -> None:
        cache = InMemoryTTLCache[Any](10)
        shifted = WeatherDateRange(dt.date(2017, 8, 27), dt.date(2017, 8, 29))
        recorder = Recorder(
            httpx.Response(200, json=flood_payload()),
            httpx.Response(200, json=flood_payload(time=["2017-08-27", "2017-08-28", "2017-08-29"])),
            httpx.Response(200, json=flood_payload()),
        )
        provider = make_provider(recorder, cache=cache)

        await provider.get_data(HOUSTON, RANGE)
        await provider.get_data(HOUSTON, shifted)
        await provider.get_data(DENVER, RANGE)

        assert len(recorder.requests) == 3
        assert len(cache) == 3

    async def test_failures_are_not_cached(self, make_provider: MakeProvider) -> None:
        cache = InMemoryTTLCache[Any](10)
        recorder = Recorder(httpx.Response(400), httpx.Response(200, json=flood_payload()))
        provider = make_provider(recorder, cache=cache)

        with pytest.raises(HazardProviderResponseError):
            await provider.get_data(HOUSTON, RANGE)
        await provider.get_data(HOUSTON, RANGE)

        assert len(recorder.requests) == 2
        assert len(cache) == 1

    async def test_ttl_from_config(self, make_provider: MakeProvider) -> None:
        recorder = Recorder(httpx.Response(200, json=flood_payload()))
        provider = make_provider(recorder, ttl=0)

        await provider.get_data(HOUSTON, RANGE)
        await provider.get_data(HOUSTON, RANGE)

        assert len(recorder.requests) == 2
