import datetime as dt

from fastapi import APIRouter

from weather_risk.application.use_cases import GetWeatherMetricsRequest
from weather_risk.presentation.api.dependencies import GetWeatherMetricsDep, WeatherServiceDep
from weather_risk.presentation.api.risk_schemas import WeatherMetricsResponse
from weather_risk.presentation.api.schemas import WeatherHistoryResponse

router = APIRouter(prefix="/hubs", tags=["weather"])


@router.get("/{hub_id}/weather/history", response_model=WeatherHistoryResponse)
async def get_hub_weather_history(
    hub_id: str,
    start_date: dt.date,
    end_date: dt.date,
    service: WeatherServiceDep,
) -> WeatherHistoryResponse:
    history = await service.get_hub_history(hub_id, start_date, end_date)
    return WeatherHistoryResponse.from_domain(hub_id, history)


@router.get("/{hub_id}/weather/metrics", response_model=WeatherMetricsResponse)
async def get_hub_weather_metrics(
    hub_id: str,
    start_date: dt.date,
    end_date: dt.date,
    handler: GetWeatherMetricsDep,
) -> WeatherMetricsResponse:
    metrics = await handler.execute(GetWeatherMetricsRequest(hub_id, start_date, end_date))
    return WeatherMetricsResponse.from_domain(hub_id, metrics)
