from abc import ABC, abstractmethod

from weather_risk.application.ports import FloodHazardProvider, HurricaneHazardProvider
from weather_risk.domain.models import (
    FloodHazardData,
    GeoLocation,
    HazardData,
    HazardType,
    HurricaneHazardData,
    WeatherDateRange,
)


class Hazard(ABC):
    """A kind of hazard the application can gather data about.

    Each implementation owns its provider port, so swapping the data source for one
    hazard never touches another.
    """

    @property
    @abstractmethod
    def hazard_type(self) -> HazardType: ...

    @abstractmethod
    async def get_data(self, location: GeoLocation, date_range: WeatherDateRange) -> HazardData:
        ...


class FloodHazard(Hazard):
    def __init__(self, provider: FloodHazardProvider) -> None:
        self._provider = provider

    @property
    def hazard_type(self) -> HazardType:
        return HazardType.FLOOD

    async def get_data(
        self, location: GeoLocation, date_range: WeatherDateRange
    ) -> FloodHazardData:
        return await self._provider.get_data(location, date_range)


class HurricaneHazard(Hazard):
    def __init__(self, provider: HurricaneHazardProvider) -> None:
        self._provider = provider

    @property
    def hazard_type(self) -> HazardType:
        return HazardType.HURRICANE

    async def get_data(
        self, location: GeoLocation, date_range: WeatherDateRange
    ) -> HurricaneHazardData:
        return await self._provider.get_data(location, date_range)
