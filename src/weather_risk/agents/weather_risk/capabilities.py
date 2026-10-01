"""Thin adapters from the agent to application use cases and services: validate the LLM's
arguments, build the use-case request, execute it, serialize the result. No business logic."""

import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from weather_risk.agents.core import AgentCapability, CapabilityRegistry, CapabilityResult
from weather_risk.agents.weather_risk import serialization as views
from weather_risk.application.hazards import HazardDataService
from weather_risk.application.hubs import HubService
from weather_risk.application.use_cases import (
    AnalyzeHubRiskHandler,
    AnalyzeHubRiskRequest,
    CompareHubsHandler,
    CompareHubsRequest,
    GetWeatherMetricsHandler,
    GetWeatherMetricsRequest,
    RankHubsHandler,
    RankHubsRequest,
)
from weather_risk.domain.models import HazardType, Region

HUB_ID = "Lowercase hub id, e.g. 'denver'"
START = "First day of the period (YYYY-MM-DD)"
END = "Last day of the period (YYYY-MM-DD), not in the future"
HAZARDS = "Hazards to score; omit for all (winter, flood, hurricane, heat)"


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ListHubsInput(_Input):
    region: Region | None = Field(default=None, description="Optional region filter")


class WeatherMetricsInput(_Input):
    hub_id: str = Field(description=HUB_ID)
    start_date: dt.date = Field(description=START)
    end_date: dt.date = Field(description=END)


class HazardDataInput(_Input):
    hub_id: str = Field(description=HUB_ID)
    hazard: HazardType = Field(description="'flood' or 'hurricane' (datasets exist only for these)")
    start_date: dt.date = Field(description=START)
    end_date: dt.date = Field(description=END)


class AnalyzeHubRiskInput(_Input):
    hub_id: str = Field(description=HUB_ID)
    start_date: dt.date = Field(description=START)
    end_date: dt.date = Field(description=END)
    hazards: list[HazardType] | None = Field(default=None, description=HAZARDS)


class RankHubsInput(_Input):
    start_date: dt.date = Field(description=START)
    end_date: dt.date = Field(description=END)
    hazards: list[HazardType] | None = Field(default=None, description=HAZARDS)
    region: Region | None = Field(default=None, description="Only hubs in this region")
    hub_ids: list[str] | None = Field(
        default=None, description="Only these hubs; omit to rank all hubs"
    )


class CompareHubsInput(_Input):
    hub_ids: list[str] = Field(min_length=2, description="Two or more hub ids")
    start_date: dt.date = Field(description=START)
    end_date: dt.date = Field(description=END)
    hazards: list[HazardType] | None = Field(default=None, description=HAZARDS)


class ListHubsCapability(AgentCapability[ListHubsInput]):
    name = "list_hubs"
    description = "List logistics hubs (id, name, state, region, coordinates)."
    input_model = ListHubsInput

    def __init__(self, service: HubService) -> None:
        self._service = service

    async def execute(self, input_data: ListHubsInput) -> CapabilityResult:
        hubs = self._service.list_hubs(input_data.region)
        return CapabilityResult({"hubs": [views.hub(h) for h in hubs]})


class GetWeatherMetricsCapability(AgentCapability[WeatherMetricsInput]):
    name = "get_weather_metrics"
    description = (
        "Factual weather statistics for a hub over a period (max 366 days): snowfall days and "
        "percentage, very cold, hot and extreme-heat days, heavy precipitation, wind, extremes."
    )
    input_model = WeatherMetricsInput

    def __init__(self, handler: GetWeatherMetricsHandler) -> None:
        self._handler = handler

    async def execute(self, input_data: WeatherMetricsInput) -> CapabilityResult:
        metrics = await self._handler.execute(
            GetWeatherMetricsRequest(input_data.hub_id, input_data.start_date, input_data.end_date)
        )
        warnings = ()
        if metrics.days_with_missing_values:
            warnings = (f"{metrics.days_with_missing_values} day(s) have missing weather values.",)
        return CapabilityResult(views.weather_metrics(input_data.hub_id, metrics), warnings)


class GetHazardDataCapability(AgentCapability[HazardDataInput]):
    name = "get_hazard_data"
    description = (
        "Raw hazard signals for a hub (no scores): 'flood' = GloFAS river discharge statistics; "
        "'hurricane' = NOAA/NHC tropical cyclones that passed within the search radius."
    )
    input_model = HazardDataInput

    def __init__(self, service: HazardDataService) -> None:
        self._service = service

    async def execute(self, input_data: HazardDataInput) -> CapabilityResult:
        data = await self._service.get_hub_hazard_data(
            input_data.hub_id, input_data.hazard, input_data.start_date, input_data.end_date
        )
        return CapabilityResult(views.hazard_data(input_data.hub_id, data))


class AnalyzeHubRiskCapability(AgentCapability[AnalyzeHubRiskInput]):
    name = "analyze_hub_risk"
    description = (
        "Deterministic 0-100 exposure scores for one hub: overall score, per-hazard scores and "
        "the factor evidence (raw values, normalized scores, weights, contributions)."
    )
    input_model = AnalyzeHubRiskInput

    def __init__(self, handler: AnalyzeHubRiskHandler) -> None:
        self._handler = handler

    async def execute(self, input_data: AnalyzeHubRiskInput) -> CapabilityResult:
        assessment = await self._handler.execute(
            AnalyzeHubRiskRequest(
                hub_id=input_data.hub_id,
                start_date=input_data.start_date,
                end_date=input_data.end_date,
                hazards=_optional_tuple(input_data.hazards),
            )
        )
        return CapabilityResult(views.overall(assessment), views.assessment_warnings(assessment))


class RankHubsCapability(AgentCapability[RankHubsInput]):
    name = "rank_hubs"
    description = (
        "Rank hubs by deterministic exposure score (highest first), optionally for selected "
        "hazards, a region or specific hubs. Includes each hub's full factor evidence."
    )
    input_model = RankHubsInput

    def __init__(self, handler: RankHubsHandler) -> None:
        self._handler = handler

    async def execute(self, input_data: RankHubsInput) -> CapabilityResult:
        result = await self._handler.execute(
            RankHubsRequest(
                start_date=input_data.start_date,
                end_date=input_data.end_date,
                hazards=_optional_tuple(input_data.hazards),
                region=input_data.region,
                hub_ids=_optional_tuple(input_data.hub_ids),
            )
        )
        ranked = result.rankings
        warnings: list[str] = []
        for r in ranked:
            warnings.extend(views.assessment_warnings(r.assessment))
        return CapabilityResult(views.ranking(ranked), tuple(dict.fromkeys(warnings)))


class CompareHubsCapability(AgentCapability[CompareHubsInput]):
    name = "compare_hubs"
    description = (
        "Compare two or more hubs: overall and per-hazard scores, pairwise score differences, "
        "and each hub's full factor evidence."
    )
    input_model = CompareHubsInput

    def __init__(self, handler: CompareHubsHandler) -> None:
        self._handler = handler

    async def execute(self, input_data: CompareHubsInput) -> CapabilityResult:
        comparison = await self._handler.execute(
            CompareHubsRequest(
                hub_ids=tuple(input_data.hub_ids),
                start_date=input_data.start_date,
                end_date=input_data.end_date,
                hazards=_optional_tuple(input_data.hazards),
            )
        )
        warnings: list[str] = []
        for a in comparison.assessments:
            warnings.extend(views.assessment_warnings(a))
        return CapabilityResult(views.comparison(comparison), tuple(dict.fromkeys(warnings)))


def build_capabilities(
    *,
    hub_service: HubService,
    hazard_data_service: HazardDataService,
    get_weather_metrics: GetWeatherMetricsHandler,
    analyze_hub_risk: AnalyzeHubRiskHandler,
    rank_hubs: RankHubsHandler,
    compare_hubs: CompareHubsHandler,
) -> CapabilityRegistry:
    capabilities: list[AgentCapability[Any]] = [
        ListHubsCapability(hub_service),
        GetWeatherMetricsCapability(get_weather_metrics),
        GetHazardDataCapability(hazard_data_service),
        AnalyzeHubRiskCapability(analyze_hub_risk),
        RankHubsCapability(rank_hubs),
        CompareHubsCapability(compare_hubs),
    ]
    return CapabilityRegistry(capabilities)


def _optional_tuple[T](values: list[T] | None) -> tuple[T, ...] | None:
    return None if values is None else tuple(values)
