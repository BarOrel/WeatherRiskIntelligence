from typing import Annotated

from fastapi import Depends, Request

from weather_risk.agents.core import ChatRuntime
from weather_risk.application.hazards import HazardDataService
from weather_risk.application.hubs import HubService
from weather_risk.application.use_cases import (
    AnalyzeHubRiskHandler,
    CompareHubsHandler,
    GetWeatherMetricsHandler,
    RankHubsHandler,
)
from weather_risk.application.weather import WeatherService
from weather_risk.container import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_hub_service(container: Annotated[Container, Depends(get_container)]) -> HubService:
    return container.hub_service


def get_weather_service(
    container: Annotated[Container, Depends(get_container)],
) -> WeatherService:
    return container.weather_service


def get_hazard_data_service(
    container: Annotated[Container, Depends(get_container)],
) -> HazardDataService:
    return container.hazard_data_service


def get_analyze_hub_risk(
    container: Annotated[Container, Depends(get_container)],
) -> AnalyzeHubRiskHandler:
    return container.analyze_hub_risk


def get_rank_hubs(container: Annotated[Container, Depends(get_container)]) -> RankHubsHandler:
    return container.rank_hubs


def get_compare_hubs(
    container: Annotated[Container, Depends(get_container)],
) -> CompareHubsHandler:
    return container.compare_hubs


def get_weather_metrics(
    container: Annotated[Container, Depends(get_container)],
) -> GetWeatherMetricsHandler:
    return container.get_weather_metrics


def get_chat_runtime(container: Annotated[Container, Depends(get_container)]) -> ChatRuntime:
    return container.chat_runtime


HubServiceDep = Annotated[HubService, Depends(get_hub_service)]
WeatherServiceDep = Annotated[WeatherService, Depends(get_weather_service)]
HazardDataServiceDep = Annotated[HazardDataService, Depends(get_hazard_data_service)]
AnalyzeHubRiskDep = Annotated[AnalyzeHubRiskHandler, Depends(get_analyze_hub_risk)]
RankHubsDep = Annotated[RankHubsHandler, Depends(get_rank_hubs)]
CompareHubsDep = Annotated[CompareHubsHandler, Depends(get_compare_hubs)]
GetWeatherMetricsDep = Annotated[GetWeatherMetricsHandler, Depends(get_weather_metrics)]
ChatRuntimeDep = Annotated[ChatRuntime, Depends(get_chat_runtime)]
