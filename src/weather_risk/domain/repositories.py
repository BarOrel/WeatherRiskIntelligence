from abc import ABC, abstractmethod

from weather_risk.domain.models import Hub, Region


class HubRepository(ABC):
    """Port for reading hubs. Implementations live in the infrastructure layer."""

    @abstractmethod
    def list_all(self) -> list[Hub]:
        """Return all hubs, ordered by id."""

    @abstractmethod
    def get_by_id(self, hub_id: str) -> Hub | None:
        """Return the hub with the given id, or None if it does not exist."""

    @abstractmethod
    def list_by_region(self, region: Region) -> list[Hub]:
        """Return all hubs in the given region, ordered by id."""
