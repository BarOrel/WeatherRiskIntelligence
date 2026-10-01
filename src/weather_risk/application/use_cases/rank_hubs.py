"""Use case: rank hubs by deterministic exposure (overall score desc, then hub id)."""

import datetime as dt
from dataclasses import dataclass

from weather_risk.application.hubs import HubService
from weather_risk.application.risk import HubRiskAssessor
from weather_risk.domain.models import HazardType, Region, WeatherDateRange
from weather_risk.domain.risk import RankedHubRisk, rank_assessments


@dataclass(frozen=True, slots=True)
class RankHubsRequest:
    start_date: dt.date
    end_date: dt.date
    hazards: tuple[HazardType, ...] | None = None
    """None = every hazard with a positive configured weight."""
    region: Region | None = None
    hub_ids: tuple[str, ...] | None = None
    """Restrict to these hubs (default: all hubs). Combined with ``region`` as a filter."""

    def __post_init__(self) -> None:
        for name in ("hazards", "hub_ids"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, tuple(value))


@dataclass(frozen=True, slots=True)
class RankHubsResult:
    date_range: WeatherDateRange
    region: Region | None
    rankings: tuple[RankedHubRisk, ...]


class RankHubsHandler:
    def __init__(self, hubs: HubService, assessor: HubRiskAssessor) -> None:
        self._hubs = hubs
        self._assessor = assessor

    async def execute(self, request: RankHubsRequest) -> RankHubsResult:
        if request.hub_ids:
            hubs = [self._hubs.get_hub(i) for i in dict.fromkeys(request.hub_ids)]
        else:
            hubs = self._hubs.list_hubs()
        if request.region is not None:
            hubs = [hub for hub in hubs if hub.region is request.region]
        scope = self._assessor.scope(request.start_date, request.end_date, request.hazards)
        assessments = await self._assessor.assess_many(hubs, scope)
        return RankHubsResult(scope.date_range, request.region, rank_assessments(assessments))
