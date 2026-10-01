"""Use case: structured, deterministic comparison of two or more hubs (no prose)."""

import datetime as dt
from dataclasses import dataclass

from weather_risk.application.errors import InvalidRiskRequestError
from weather_risk.application.hubs import HubService
from weather_risk.application.risk import HubRiskAssessor
from weather_risk.domain.models import HazardType
from weather_risk.domain.risk import HubComparison, compare_assessments


@dataclass(frozen=True, slots=True)
class CompareHubsRequest:
    hub_ids: tuple[str, ...]
    start_date: dt.date
    end_date: dt.date
    hazards: tuple[HazardType, ...] | None = None
    """None = every hazard with a positive configured weight."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "hub_ids", tuple(self.hub_ids))
        if self.hazards is not None:
            object.__setattr__(self, "hazards", tuple(self.hazards))


class CompareHubsHandler:
    def __init__(self, hubs: HubService, assessor: HubRiskAssessor) -> None:
        self._hubs = hubs
        self._assessor = assessor

    async def execute(self, request: CompareHubsRequest) -> HubComparison:
        unique_ids = list(dict.fromkeys(request.hub_ids))
        if len(unique_ids) < 2:
            raise InvalidRiskRequestError("Comparison needs at least two distinct hubs")
        hubs = [self._hubs.get_hub(i) for i in unique_ids]
        scope = self._assessor.scope(request.start_date, request.end_date, request.hazards)
        return compare_assessments(await self._assessor.assess_many(hubs, scope))
