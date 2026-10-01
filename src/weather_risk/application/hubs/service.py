from weather_risk.application.errors import HubNotFoundError
from weather_risk.domain.models import Hub, Region
from weather_risk.domain.repositories import HubRepository


class HubService:
    """Read-side use cases for hubs."""

    def __init__(self, repository: HubRepository) -> None:
        self._repository = repository

    def list_hubs(self, region: Region | None = None) -> list[Hub]:
        if region is None:
            return self._repository.list_all()
        return self._repository.list_by_region(region)

    def get_hub(self, hub_id: str) -> Hub:
        hub = self._repository.get_by_id(hub_id)
        if hub is None:
            raise HubNotFoundError(hub_id)
        return hub
