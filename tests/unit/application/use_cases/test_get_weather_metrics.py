import pytest
from support.fakes import DENVER
from support.use_cases import END, START, Fixture, make_fixture

from weather_risk.application.errors import HubNotFoundError, InvalidDateRangeError
from weather_risk.application.use_cases import GetWeatherMetricsRequest
from weather_risk.domain.risk import WeatherMetricsCalculator, WeatherThresholds


@pytest.fixture
def fx() -> Fixture:
    return make_fixture()


async def test_metrics_come_from_the_shared_calculator(fx: Fixture) -> None:
    metrics = await fx.get_weather_metrics.execute(GetWeatherMetricsRequest("denver", START, END))

    history = await fx.weather_service.get_hub_history("denver", START, END)
    assert metrics == WeatherMetricsCalculator(WeatherThresholds()).calculate(history)
    assert metrics.days == 365
    assert [loc for loc, _ in fx.weather.calls] == [DENVER, DENVER]


async def test_unknown_hub(fx: Fixture) -> None:
    with pytest.raises(HubNotFoundError):
        await fx.get_weather_metrics.execute(GetWeatherMetricsRequest("atlantis", START, END))


async def test_invalid_dates(fx: Fixture) -> None:
    with pytest.raises(InvalidDateRangeError):
        await fx.get_weather_metrics.execute(GetWeatherMetricsRequest("denver", END, START))
