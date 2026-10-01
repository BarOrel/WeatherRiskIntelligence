"""Use case: deterministic risk assessment of one hub."""

import datetime as dt
from dataclasses import dataclass

from weather_risk.application.hubs import HubService
from weather_risk.application.risk import HubRiskAssessor
from weather_risk.domain.models import HazardType
from weather_risk.domain.risk import OverallRiskAssessment


@dataclass(frozen=True, slots=True)
class AnalyzeHubRiskRequest:
    hub_id: str
    start_date: dt.date
    end_date: dt.date
    hazards: tuple[HazardType, ...] | None = None
    """None = every hazard with a positive configured weight."""

    def __post_init__(self) -> None:
        if self.hazards is not None:
            object.__setattr__(self, "hazards", tuple(self.hazards))


class AnalyzeHubRiskHandler:
    def __init__(self, hubs: HubService, assessor: HubRiskAssessor) -> None:
        self._hubs = hubs
        self._assessor = assessor

    async def execute(self, request: AnalyzeHubRiskRequest) -> OverallRiskAssessment:
        hub = self._hubs.get_hub(request.hub_id)
        scope = self._assessor.scope(request.start_date, request.end_date, request.hazards)
        return await self._assessor.assess(hub, scope)

