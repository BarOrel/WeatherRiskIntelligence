"""Ports for external data sources the application depends on.

Implementations live in the infrastructure layer and are wired in the composition root.
Each port is specific to one kind of data, so a new source for that data (e.g. another
flood dataset) is a new implementation, with no change to the code that uses it.
"""

from abc import ABC, abstractmethod

from weather_risk.domain.models import (
    FloodHazardData,
    GeoLocation,
    HurricaneHazardData,
    WeatherDateRange,
    WeatherHistory,
)


class WeatherProvider(ABC):
    """Source of historical daily weather observations."""

    @abstractmethod
    async def get_history(
        self, location: GeoLocation, date_range: WeatherDateRange
    ) -> WeatherHistory:
        """Return daily observations for every day in ``date_range``.

        Raises a ``WeatherProviderError`` subclass on failure.
        """


class FloodHazardProvider(ABC):
    """Source of flood exposure signals (e.g. river discharge)."""

    @abstractmethod
    async def get_data(
        self, location: GeoLocation, date_range: WeatherDateRange
    ) -> FloodHazardData:
        """Raises a ``HazardProviderError`` subclass on failure."""


class HurricaneHazardProvider(ABC):
    """Source of tropical cyclones that passed near a location."""

    @abstractmethod
    async def get_data(
        self, location: GeoLocation, date_range: WeatherDateRange
    ) -> HurricaneHazardData:
        """Raises a ``HazardProviderError`` subclass on failure."""
