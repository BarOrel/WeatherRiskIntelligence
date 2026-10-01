import datetime as dt
from collections.abc import Callable

from weather_risk.application.date_ranges import historical_date_range
from weather_risk.application.errors import HubNotFoundError
from weather_risk.application.ports import WeatherProvider
from weather_risk.domain.models import Hub, WeatherHistory
from weather_risk.domain.repositories import HubRepository


class WeatherService:
    """Validated historical weather for a hub (hub lookup, date-range rules, provider call).

    Reused by the weather-history endpoint and the GetWeatherMetrics use case.
    """

    def __init__(
        self,
        hub_repository: HubRepository,
        weather_provider: WeatherProvider,
        max_history_days: int,
        today: Callable[[], dt.date] = dt.date.today,
    ) -> None:
        self._hub_repository = hub_repository
        self._weather_provider = weather_provider
        self._max_history_days = max_history_days
        self._today = today

    async def get_hub_history(
        self, hub_id: str, start_date: dt.date, end_date: dt.date
    ) -> WeatherHistory:
        hub = self._get_hub(hub_id)
        date_range = historical_date_range(
            start_date, end_date, today=self._today(), max_days=self._max_history_days
        )
        return await self._weather_provider.get_history(hub.location, date_range)

    def _get_hub(self, hub_id: str) -> Hub:
        hub = self._hub_repository.get_by_id(hub_id)
        if hub is None:
            raise HubNotFoundError(hub_id)
        return hub
