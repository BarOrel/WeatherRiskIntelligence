import datetime as dt

import pytest
from support.fakes import DENVER, FakeWeatherProvider, InMemoryHubRepository

from weather_risk.application.errors import HubNotFoundError, InvalidDateRangeError
from weather_risk.application.weather import WeatherService
from weather_risk.domain.models import Hub, Region, WeatherDateRange

TODAY = dt.date(2024, 6, 15)


@pytest.fixture
def provider() -> FakeWeatherProvider:
    return FakeWeatherProvider()


@pytest.fixture
def service(provider: FakeWeatherProvider) -> WeatherService:
    denver = Hub(id="denver", name="Denver", state="CO", location=DENVER, region=Region.WEST)
    return WeatherService(
        hub_repository=InMemoryHubRepository([denver]),
        weather_provider=provider,
        max_history_days=31,
        today=lambda: TODAY,
    )


async def test_requests_history_for_hub_coordinates(
    service: WeatherService, provider: FakeWeatherProvider
) -> None:
    start, end = dt.date(2024, 1, 1), dt.date(2024, 1, 7)

    history = await service.get_hub_history("denver", start, end)

    assert provider.calls == [(DENVER, WeatherDateRange(start, end))]
    assert history.location == DENVER


async def test_unknown_hub_raises_without_calling_provider(
    service: WeatherService, provider: FakeWeatherProvider
) -> None:
    with pytest.raises(HubNotFoundError):
        await service.get_hub_history("atlantis", dt.date(2024, 1, 1), dt.date(2024, 1, 2))

    assert provider.calls == []


@pytest.mark.parametrize(
    ("start", "end", "message"),
    [
        (dt.date(2024, 1, 5), dt.date(2024, 1, 1), "must not be after"),
        (dt.date(2024, 6, 10), dt.date(2024, 6, 16), "future"),
        (dt.date(2024, 1, 1), dt.date(2024, 2, 1), "maximum is 31"),
    ],
)
async def test_rejects_invalid_ranges(
    service: WeatherService,
    provider: FakeWeatherProvider,
    start: dt.date,
    end: dt.date,
    message: str,
) -> None:
    with pytest.raises(InvalidDateRangeError, match=message):
        await service.get_hub_history("denver", start, end)

    assert provider.calls == []


async def test_accepts_range_ending_today_at_maximum_length(service: WeatherService) -> None:
    history = await service.get_hub_history("denver", TODAY - dt.timedelta(days=30), TODAY)

    assert history.date_range.days == 31
