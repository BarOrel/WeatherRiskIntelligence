"""Response schemas for weather metrics and risk results.

Scores are rounded to 2 decimals for display; the domain keeps full precision.
"""

import datetime as dt

from pydantic import BaseModel

from weather_risk.application.use_cases import RankHubsResult
from weather_risk.domain.models import HazardType, Region
from weather_risk.domain.risk import (
    HazardComparison,
    HazardRiskAssessment,
    HubComparison,
    OverallRiskAssessment,
    RankedHubRisk,
    RiskFactor,
    ScoreDifference,
    WeatherMetrics,
)

DECIMALS = 2


def _r(value: float) -> float:
    return round(value, DECIMALS)


def _r_opt(value: float | None) -> float | None:
    return None if value is None else _r(value)


# --- Weather metrics -----------------------------------------------------------------------


class WeatherThresholdsResponse(BaseModel):
    snowfall_day_cm: float
    very_cold_day_c: float
    hot_day_c: float
    extreme_heat_day_c: float
    heavy_precipitation_mm: float
    high_wind_gust_kmh: float
    severe_wind_gust_kmh: float


class WeatherMetricsResponse(BaseModel):
    hub_id: str
    start_date: dt.date
    end_date: dt.date
    days: int
    days_with_missing_values: int
    thresholds: WeatherThresholdsResponse
    snowfall_days: int
    snowfall_day_percentage: float
    total_snowfall_cm: float
    max_daily_snowfall_cm: float | None
    very_cold_days: int
    very_cold_day_percentage: float
    min_temperature_c: float | None
    hot_days: int
    hot_day_percentage: float
    extreme_heat_days: int
    extreme_heat_day_percentage: float
    max_temperature_c: float | None
    heavy_precipitation_days: int
    heavy_precipitation_day_percentage: float
    total_precipitation_mm: float
    max_daily_precipitation_mm: float | None
    high_wind_days: int
    high_wind_day_percentage: float
    severe_wind_days: int
    max_wind_gust_kmh: float | None

    @classmethod
    def from_domain(cls, hub_id: str, m: WeatherMetrics) -> "WeatherMetricsResponse":
        t = m.thresholds
        return cls(
            hub_id=hub_id,
            start_date=m.date_range.start,
            end_date=m.date_range.end,
            days=m.days,
            days_with_missing_values=m.days_with_missing_values,
            thresholds=WeatherThresholdsResponse(
                snowfall_day_cm=t.snowfall_day_cm,
                very_cold_day_c=t.very_cold_day_c,
                hot_day_c=t.hot_day_c,
                extreme_heat_day_c=t.extreme_heat_day_c,
                heavy_precipitation_mm=t.heavy_precipitation_mm,
                high_wind_gust_kmh=t.high_wind_gust_kmh,
                severe_wind_gust_kmh=t.severe_wind_gust_kmh,
            ),
            snowfall_days=m.snowfall_days,
            snowfall_day_percentage=_r(m.snowfall_day_percentage),
            total_snowfall_cm=_r(m.total_snowfall_cm),
            max_daily_snowfall_cm=_r_opt(m.max_daily_snowfall_cm),
            very_cold_days=m.very_cold_days,
            very_cold_day_percentage=_r(m.very_cold_day_percentage),
            min_temperature_c=_r_opt(m.min_temperature_c),
            hot_days=m.hot_days,
            hot_day_percentage=_r(m.hot_day_percentage),
            extreme_heat_days=m.extreme_heat_days,
            extreme_heat_day_percentage=_r(m.extreme_heat_day_percentage),
            max_temperature_c=_r_opt(m.max_temperature_c),
            heavy_precipitation_days=m.heavy_precipitation_days,
            heavy_precipitation_day_percentage=_r(m.heavy_precipitation_day_percentage),
            total_precipitation_mm=_r(m.total_precipitation_mm),
            max_daily_precipitation_mm=_r_opt(m.max_daily_precipitation_mm),
            high_wind_days=m.high_wind_days,
            high_wind_day_percentage=_r(m.high_wind_day_percentage),
            severe_wind_days=m.severe_wind_days,
            max_wind_gust_kmh=_r_opt(m.max_wind_gust_kmh),
        )


# --- Risk ----------------------------------------------------------------------------------


class RiskFactorResponse(BaseModel):
    name: str
    description: str
    raw_value: float
    unit: str
    scale_low: float
    scale_high: float
    normalized_score: float
    weight: float
    contribution: float

    @classmethod
    def from_domain(cls, f: RiskFactor) -> "RiskFactorResponse":
        return cls(
            name=f.name,
            description=f.description,
            raw_value=_r(f.raw_value),
            unit=f.unit,
            scale_low=f.scale_low,
            scale_high=f.scale_high,
            normalized_score=_r(f.normalized_score),
            weight=round(f.weight, 4),
            contribution=_r(f.contribution),
        )


class HazardRiskResponse(BaseModel):
    hazard_type: HazardType
    score: float
    weight_in_overall: float
    contribution_to_overall: float
    factors: list[RiskFactorResponse]
    assumptions: list[str]
    warnings: list[str]

    @classmethod
    def from_domain(
        cls, a: HazardRiskAssessment, overall: OverallRiskAssessment
    ) -> "HazardRiskResponse":
        return cls(
            hazard_type=a.hazard_type,
            score=_r(a.score),
            weight_in_overall=round(overall.applied_weights[a.hazard_type], 4),
            contribution_to_overall=_r(overall.contribution_of(a.hazard_type)),
            factors=[RiskFactorResponse.from_domain(f) for f in a.factors],
            assumptions=list(a.assumptions),
            warnings=list(a.warnings),
        )


class OverallRiskResponse(BaseModel):
    hub_id: str
    hub_name: str
    region: Region
    start_date: dt.date
    end_date: dt.date
    overall_score: float
    hazards: list[HazardRiskResponse]
    assumptions: list[str]
    warnings: list[str]

    @classmethod
    def from_domain(cls, a: OverallRiskAssessment) -> "OverallRiskResponse":
        return cls(
            hub_id=a.hub.id,
            hub_name=a.hub.name,
            region=a.hub.region,
            start_date=a.date_range.start,
            end_date=a.date_range.end,
            overall_score=_r(a.overall_score),
            hazards=[HazardRiskResponse.from_domain(h, a) for h in a.hazard_assessments],
            assumptions=list(a.assumptions),
            warnings=list(a.warnings),
        )


class RankedHubResponse(BaseModel):
    rank: int
    hub_id: str
    hub_name: str
    region: Region
    overall_score: float
    hazard_scores: dict[HazardType, float]

    @classmethod
    def from_domain(cls, r: RankedHubRisk) -> "RankedHubResponse":
        return cls(
            rank=r.rank,
            hub_id=r.hub.id,
            hub_name=r.hub.name,
            region=r.hub.region,
            overall_score=_r(r.overall_score),
            hazard_scores={h: _r(s) for h, s in r.hazard_scores.items()},
        )


class RankingResponse(BaseModel):
    start_date: dt.date
    end_date: dt.date
    region: Region | None
    hazards: list[HazardType]
    applied_weights: dict[HazardType, float]
    rankings: list[RankedHubResponse]

    @classmethod
    def from_result(cls, result: RankHubsResult) -> "RankingResponse":
        ranking = result.rankings
        first = ranking[0].assessment if ranking else None
        return cls(
            start_date=result.date_range.start,
            end_date=result.date_range.end,
            region=result.region,
            hazards=list(first.hazards) if first else [],
            applied_weights=(
                {h: round(w, 4) for h, w in first.applied_weights.items()} if first else {}
            ),
            rankings=[RankedHubResponse.from_domain(r) for r in ranking],
        )


class ScoreDifferenceResponse(BaseModel):
    hub_id: str
    other_hub_id: str
    difference: float

    @classmethod
    def from_domain(cls, d: ScoreDifference) -> "ScoreDifferenceResponse":
        return cls(hub_id=d.hub_id, other_hub_id=d.other_hub_id, difference=_r(d.difference))


class HazardComparisonResponse(BaseModel):
    hazard_type: HazardType
    scores: dict[str, float]
    highest_hub_id: str
    lowest_hub_id: str
    spread: float
    differences: list[ScoreDifferenceResponse]

    @classmethod
    def from_domain(cls, c: HazardComparison) -> "HazardComparisonResponse":
        return cls(
            hazard_type=c.hazard_type,
            scores={hub_id: _r(score) for hub_id, score in c.scores},
            highest_hub_id=c.highest_hub_id,
            lowest_hub_id=c.lowest_hub_id,
            spread=_r(c.spread),
            differences=[ScoreDifferenceResponse.from_domain(d) for d in c.differences],
        )


class ComparisonResponse(BaseModel):
    hub_ids: list[str]
    highest_overall_hub_id: str
    overall_scores: dict[str, float]
    overall_differences: list[ScoreDifferenceResponse]
    hazard_comparisons: list[HazardComparisonResponse]
    assessments: list[OverallRiskResponse]

    @classmethod
    def from_domain(cls, c: HubComparison) -> "ComparisonResponse":
        return cls(
            hub_ids=[a.hub.id for a in c.assessments],
            highest_overall_hub_id=c.highest_overall_hub_id,
            overall_scores={a.hub.id: _r(a.overall_score) for a in c.assessments},
            overall_differences=[
                ScoreDifferenceResponse.from_domain(d) for d in c.overall_differences
            ],
            hazard_comparisons=[
                HazardComparisonResponse.from_domain(h) for h in c.hazard_comparisons
            ],
            assessments=[OverallRiskResponse.from_domain(a) for a in c.assessments],
        )
