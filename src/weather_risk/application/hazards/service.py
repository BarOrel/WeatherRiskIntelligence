import datetime as dt
from collections.abc import Callable

from weather_risk.application.date_ranges import historical_date_range
from weather_risk.application.errors import HubNotFoundError
from weather_risk.application.hazards.registry import HazardRegistry
from weather_risk.domain.models import HazardData, HazardType
from weather_risk.domain.repositories import HubRepository


class HazardDataService:
    """Gathers hazard data for a hub. Orchestration only: no scoring or interpretation.

    This is the capability a future agent will call. It hides every provider detail.
    """

    def __init__(
        self,
        hub_repository: HubRepository,
        registry: HazardRegistry,
        max_history_days: int,
        today: Callable[[], dt.date] = dt.date.today,
    ) -> None:
        self._hub_repository = hub_repository
        self._registry = registry
        self._max_history_days = max_history_days
        self._today = today

    @property
    def supported_hazards(self) -> tuple[HazardType, ...]:
        return self._registry.supported_types

    async def get_hub_hazard_data(
        self,
        hub_id: str,
        hazard_type: HazardType,
        start_date: dt.date,
        end_date: dt.date,
    ) -> HazardData:
        hub = self._hub_repository.get_by_id(hub_id)
        if hub is None:
            raise HubNotFoundError(hub_id)

        hazard = self._registry.get(hazard_type)
        date_range = historical_date_range(
            start_date, end_date, today=self._today(), max_days=self._max_history_days
        )
        return await hazard.get_data(hub.location, date_range)
