"""Deterministic risk scoring: metrics, normalization, strategies, engine, ranking.

Pure domain logic with no I/O. The scores here are the authoritative results; a future LLM
only explains them.
"""

from weather_risk.domain.risk.analysis import (
    HazardComparison,
    HubComparison,
    RankedHubRisk,
    ScoreDifference,
    compare_assessments,
    rank_assessments,
)
from weather_risk.domain.risk.engine import DataRequirements, RiskScoringEngine
from weather_risk.domain.risk.models import (
    HazardRiskAssessment,
    OverallRiskAssessment,
    RiskAssessmentContext,
    RiskFactor,
)
from weather_risk.domain.risk.normalization import normalize_linear, normalize_weights
from weather_risk.domain.risk.strategies import (
    FloodRiskStrategy,
    HeatRiskStrategy,
    HurricaneRiskStrategy,
    RiskStrategy,
    WinterRiskStrategy,
)
from weather_risk.domain.risk.weather_metrics import (
    WeatherMetrics,
    WeatherMetricsCalculator,
    WeatherThresholds,
)

__all__ = [
    "DataRequirements",
    "FloodRiskStrategy",
    "HazardComparison",
    "HazardRiskAssessment",
    "HeatRiskStrategy",
    "HubComparison",
    "HurricaneRiskStrategy",
    "OverallRiskAssessment",
    "RankedHubRisk",
    "RiskAssessmentContext",
    "RiskFactor",
    "RiskScoringEngine",
    "RiskStrategy",
    "ScoreDifference",
    "WeatherMetrics",
    "WeatherMetricsCalculator",
    "WeatherThresholds",
    "WinterRiskStrategy",
    "compare_assessments",
    "normalize_linear",
    "normalize_weights",
    "rank_assessments",
]
