import datetime as dt
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
from support.hurdat2_samples import ATLANTIC, PACIFIC
from support.http import Router, no_sleep

from weather_risk.application.errors import (
    HazardProviderResponseError,
    HazardProviderTimeoutError,
    HazardProviderUnavailableError,
    InvalidHazardDataError,
)
from weather_risk.domain.models import GeoLocation, HurricaneHazardData, WeatherDateRange
from weather_risk.infrastructure.cache import InMemoryTTLCache
from weather_risk.infrastructure.hazards.hurricane import (
    NoaaHurricaneConfig,
    NoaaHurricaneHazardProvider,
)
from weather_risk.infrastructure.http import RetryPolicy

ATL_URL = "https://nhc.test/data/hurdat/hurdat2-atl.txt"
PAC_URL = "https://nhc.test/data/hurdat/hurdat2-nepac.txt"
MIAMI = GeoLocation(25.7617, -80.1918)
AUGUST_2020 = WeatherDateRange(dt.date(2020, 8, 1), dt.date(2020, 8, 31))


def ok_routes() -> dict[str, httpx.Response | Exception]:
    return {ATL_URL: httpx.Response(200, text=ATLANTIC), PAC_URL: httpx.Response(200, text=PACIFIC)}


MakeProvider = Callable[..., NoaaHurricaneHazardProvider]


@pytest.fixture
async def make_provider() -> AsyncIterator[MakeProvider]:
    clients: list[httpx.AsyncClient] = []

    def factory(
        router: Router,
        cache: InMemoryTTLCache[Any] | None = None,
        radius_km: float = 200.0,
    ) -> NoaaHurricaneHazardProvider:
        client = httpx.AsyncClient(transport=httpx.MockTransport(router))
        clients.append(client)
        return NoaaHurricaneHazardProvider(
            client=client,
            cache=cache if cache is not None else InMemoryTTLCache[Any](10),
            config=NoaaHurricaneConfig(
                dataset_urls=(ATL_URL, PAC_URL),
                timeout_seconds=5.0,
                retry_policy=RetryPolicy(max_retries=1, backoff_seconds=0),
                search_radius_km=radius_km,
                cache_ttl_seconds=600,
                dataset_ttl_seconds=3600,
            ),
            sleep=no_sleep,
        )

    yield factory
    for client in clients:
        await client.aclose()


async def test_downloads_each_configured_dataset(make_provider: MakeProvider) -> None:
    router = Router(ok_routes())

    await make_provider(router).get_data(MIAMI, AUGUST_2020)

    assert sorted(str(r.url) for r in router.requests) == sorted([ATL_URL, PAC_URL])
    assert all(r.method == "GET" for r in router.requests)


async def test_maps_matching_storms(make_provider: MakeProvider) -> None:
    data = await make_provider(Router(ok_routes())).get_data(MIAMI, AUGUST_2020)

    assert isinstance(data, HurricaneHazardData)
    assert data.location == MIAMI
    assert data.date_range == AUGUST_2020
    assert data.search_radius_km == 200.0
    assert data.data_coverage_end == dt.date(2020, 7, 1)  # earliest of the files' last dates
    assert "National Hurricane Center" in data.source.name
    [event] = data.events
    assert (event.storm_id, event.name, event.peak_category) == ("AL012020", "ALPHA", 2)
    assert event.closest_approach_km < 25


async def test_proximity_filtering_uses_configured_radius(make_provider: MakeProvider) -> None:
    data = await make_provider(Router(ok_routes()), radius_km=10).get_data(MIAMI, AUGUST_2020)

    assert data.events == ()
    assert data.search_radius_km == 10


async def test_date_filtering_and_no_matches(make_provider: MakeProvider) -> None:
    september = WeatherDateRange(dt.date(2020, 9, 1), dt.date(2020, 9, 30))

    data = await make_provider(Router(ok_routes())).get_data(MIAMI, september)

    assert data.events == ()


async def test_flags_ranges_beyond_dataset_coverage(make_provider: MakeProvider) -> None:
    data = await make_provider(Router(ok_routes())).get_data(MIAMI, AUGUST_2020)

    assert any("covers storms through 2020-07-01" in text for text in data.limitations)


async def test_malformed_dataset(make_provider: MakeProvider) -> None:
    routes = ok_routes() | {ATL_URL: httpx.Response(200, text="AL012020, ALPHA, 9,\n")}

    with pytest.raises(InvalidHazardDataError):
        await make_provider(Router(routes)).get_data(MIAMI, AUGUST_2020)


@pytest.mark.parametrize(
    ("outcome", "error_type"),
    [
        (httpx.Response(404), HazardProviderResponseError),
        (httpx.Response(503), HazardProviderResponseError),
        (httpx.ConnectError("refused"), HazardProviderUnavailableError),
        (httpx.ReadTimeout("slow"), HazardProviderTimeoutError),
    ],
)
async def test_provider_failures(
    make_provider: MakeProvider, outcome: Any, error_type: type[Exception]
) -> None:
    routes = ok_routes() | {PAC_URL: outcome}

    with pytest.raises(error_type):
        await make_provider(Router(routes)).get_data(MIAMI, AUGUST_2020)


class TestCaching:
    async def test_repeat_request_is_a_cache_hit(self, make_provider: MakeProvider) -> None:
        router = Router(ok_routes())
        provider = make_provider(router)

        first = await provider.get_data(MIAMI, AUGUST_2020)
        second = await provider.get_data(MIAMI, AUGUST_2020)

        assert second is first
        assert len(router.requests) == 2  # one download per dataset file

    async def test_dataset_is_downloaded_once_for_different_searches(
        self, make_provider: MakeProvider
    ) -> None:
        cache = InMemoryTTLCache[Any](10)
        router = Router(ok_routes())
        provider = make_provider(router, cache=cache)
        houston = GeoLocation(29.7604, -95.3698)

        await provider.get_data(MIAMI, AUGUST_2020)
        await provider.get_data(houston, AUGUST_2020)
        await provider.get_data(MIAMI, WeatherDateRange(dt.date(2020, 1, 1), dt.date(2020, 12, 31)))

        assert len(router.requests) == 2
        assert len(cache) == 4  # 1 parsed dataset + 3 distinct searches

    async def test_failed_download_is_not_cached(self, make_provider: MakeProvider) -> None:
        cache = InMemoryTTLCache[Any](10)
        routes = ok_routes() | {PAC_URL: httpx.Response(404)}
        router = Router(routes)
        provider = make_provider(router, cache=cache)

        with pytest.raises(HazardProviderResponseError):
            await provider.get_data(MIAMI, AUGUST_2020)
        assert len(cache) == 0

        routes[PAC_URL] = httpx.Response(200, text=PACIFIC)
        data = await provider.get_data(MIAMI, AUGUST_2020)

        assert [e.name for e in data.events] == ["ALPHA"]
