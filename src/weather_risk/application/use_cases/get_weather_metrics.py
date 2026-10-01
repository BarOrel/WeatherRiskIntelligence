"""Use case: factual weather statistics for a hub (e.g. share of days with snowfall).
No scoring involved."""

import datetime as dt
from dataclasses import dataclass

from weather_risk.application.weather import WeatherService
from weather_risk.domain.risk import WeatherMetrics, WeatherMetricsCalculator


@dataclass(frozen=True, slots=True)
class GetWeatherMetricsRequest:
    hub_id: str
    start_date: dt.date
    end_date: dt.date


class GetWeatherMetricsHandler:
    def __init__(self, weather: WeatherService, calculator: WeatherMetricsCalculator) -> None:
        self._weather = weather
        self._calculator = calculator

    async def execute(self, request: GetWeatherMetricsRequest) -> WeatherMetrics:
        history = await self._weather.get_hub_history(
            request.hub_id, request.start_date, request.end_date
        )
        return self._calculator.calculate(history)
