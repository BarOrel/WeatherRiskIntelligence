"""Builders for deterministic risk-scoring tests. Importable as ``support.risk``."""

import datetime as dt
from dataclasses import replace
from typing import Any

from support.fakes import DENVER, SOURCE, make_hurricane_data, make_track_point

from weather_risk.domain.models import (
    CycloneClassification,
    DailyRiverDischarge,
    DailyWeatherObservation,
    FloodHazardData,
    GeoLocation,
    HazardType,
    Hub,
    HurricaneHazardData,
    Region,
    TropicalCycloneEvent,
    WeatherDateRange,
    WeatherHistory,
)
from weather_risk.domain.risk import (
    HazardRiskAssessment,
    OverallRiskAssessment,
    WeatherMetrics,
    WeatherThresholds,
)

START = dt.date(2024, 1, 1)
DENVER_HUB = Hub(id="denver", name="Denver", state="CO", location=DENVER, region=Region.WEST)


def days_range(days: int, start: dt.date = START) -> WeatherDateRange:
    return WeatherDateRange(start, start + dt.timedelta(days=days - 1))


def history_from(rows: list[dict[str, float | None]], location: GeoLocation = DENVER) -> WeatherHistory:
    """One observation per row; unspecified fields default to an unremarkable mild day."""
    date_range = days_range(len(rows))
    base: dict[str, float | None] = {
        "precipitation_mm": 0.0,
        "rain_mm": 0.0,
        "snowfall_cm": 0.0,
        "temperature_max_c": 15.0,
        "temperature_min_c": 5.0,
        "wind_speed_max_kmh": 10.0,
        "wind_gust_max_kmh": 20.0,
    }
    return WeatherHistory(
        location=location,
        date_range=date_range,
        timezone="UTC",
        observations=tuple(
            DailyWeatherObservation(date=day, **(base | row))
            for day, row in zip(date_range.dates(), rows, strict=True)
        ),
    )


def make_metrics(days: int = 100, **overrides: Any) -> WeatherMetrics:
    values: dict[str, Any] = {
        "date_range": days_range(days),
        "thresholds": WeatherThresholds(),
        "days": days,
        "days_with_missing_values": 0,
        "snowfall_days": 0,
        "total_snowfall_cm": 0.0,
        "max_daily_snowfall_cm": 0.0,
        "very_cold_days": 0,
        "min_temperature_c": 0.0,
        "hot_days": 0,
        "extreme_heat_days": 0,
        "max_temperature_c": 20.0,
        "heavy_precipitation_days": 0,
        "total_precipitation_mm": 0.0,
        "max_daily_precipitation_mm": 0.0,
        "high_wind_days": 0,
        "severe_wind_days": 0,
        "max_wind_gust_kmh": 30.0,
    }
    values.update(overrides)
    return WeatherMetrics(**values)


def flood_data(discharges: list[float | None], location: GeoLocation = DENVER) -> FloodHazardData:
    date_range = days_range(len(discharges))
    return FloodHazardData(
        location=location,
        date_range=date_range,
        source=SOURCE,
        limitations=("Signal only.",),
        cell_location=location,
        observations=tuple(
            DailyRiverDischarge(date=day, discharge_m3s=value)
            for day, value in zip(date_range.dates(), discharges, strict=True)
        ),
    )


TEN_YEARS = WeatherDateRange(dt.date(2000, 1, 1), dt.date(2009, 12, 31))


def make_event(
    wind_kmh: float | None, distance_km: float, storm_id: str = "AL012005"
) -> TropicalCycloneEvent:
    time = dt.datetime(2005, 8, 1, 12, tzinfo=dt.UTC)
    return TropicalCycloneEvent(
        storm_id=storm_id,
        name="TEST",
        start_date=time.date(),
        end_date=time.date(),
        closest_approach_km=distance_km,
        closest_approach_time=time,
        classification_at_closest_approach=CycloneClassification.HURRICANE,
        wind_at_closest_approach_kmh=wind_kmh,
        peak_classification=CycloneClassification.HURRICANE,
        peak_category=None,
        max_wind_kmh=wind_kmh,
        min_pressure_hpa=None,
        track=(make_track_point(time, DENVER, wind_kmh),),
    )


def hurricane_data(
    *events: TropicalCycloneEvent, date_range: WeatherDateRange = TEN_YEARS
) -> HurricaneHazardData:
    return replace(
        make_hurricane_data(date_range=date_range),
        events=events,
        data_coverage_end=date_range.end,
    )


def make_hub(hub_id: str, region: Region = Region.SOUTH) -> Hub:
    return Hub(id=hub_id, name=hub_id.title(), state="TX", location=DENVER, region=region)


def overall(
    hub: Hub | str, scores: dict[HazardType, float], weights: dict[HazardType, float] | None = None
) -> OverallRiskAssessment:
    """An OverallRiskAssessment with given hazard scores (factors omitted)."""
    hub = make_hub(hub) if isinstance(hub, str) else hub
    weights = weights or {h: 1 / len(scores) for h in scores}
    return OverallRiskAssessment(
        hub=hub,
        date_range=days_range(365),
        overall_score=sum(weights[h] * s for h, s in scores.items()),
        hazard_assessments=tuple(HazardRiskAssessment(h, s, ()) for h, s in scores.items()),
        applied_weights=weights,
    )
