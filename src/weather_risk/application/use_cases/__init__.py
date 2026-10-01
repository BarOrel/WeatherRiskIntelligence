"""Application use cases: one module and one ``execute`` entry point per business operation.

Primary: RankHubs, CompareHubs. Supporting: AnalyzeHubRisk, GetWeatherMetrics.
Shared logic lives outside the slices (domain risk engine, HubRiskAssessor, focused services).
"""

from weather_risk.application.use_cases.analyze_hub_risk import (
    AnalyzeHubRiskHandler,
    AnalyzeHubRiskRequest,
)
from weather_risk.application.use_cases.compare_hubs import CompareHubsHandler, CompareHubsRequest
from weather_risk.application.use_cases.get_weather_metrics import (
    GetWeatherMetricsHandler,
    GetWeatherMetricsRequest,
)
from weather_risk.application.use_cases.rank_hubs import (
    RankHubsHandler,
    RankHubsRequest,
    RankHubsResult,
)

__all__ = [
    "AnalyzeHubRiskHandler",
    "AnalyzeHubRiskRequest",
    "CompareHubsHandler",
    "CompareHubsRequest",
    "GetWeatherMetricsHandler",
    "GetWeatherMetricsRequest",
    "RankHubsHandler",
    "RankHubsRequest",
    "RankHubsResult",
]
