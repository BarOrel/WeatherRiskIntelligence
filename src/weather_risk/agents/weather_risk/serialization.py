"""Compact, JSON-ready views of domain results for the LLM.

Values are rounded to 2 decimals (the same precision as the HTTP API) so the LLM can quote
them verbatim. Bulky data (daily series of long periods, storm tracks) is summarized.
"""

from collections.abc import Callable
from typing import Any

from weather_risk.domain.models import (
    FloodHazardData,
    HazardData,
    Hub,
    HurricaneHazardData,
    TropicalCycloneEvent,
)
from weather_risk.domain.risk import (
    HazardRiskAssessment,
    HubComparison,
    OverallRiskAssessment,
    RankedHubRisk,
    WeatherMetrics,
)
from weather_risk.domain.risk.hazard_metrics import calculate_flood_metrics

MAX_DAILY_VALUES = 62


_DISPLAY_UNITS = {
    "percent": "% of days",
    "ratio": "x normal flow",
    "events/year": " storms per year",
    "impact/year": " impact per year",
    "impact": " (0-1 scale)",
}


def _display(value: float, unit: str) -> str:
    """Unambiguous text for a factor value, e.g. 0.55 percent -> "0.55% of days"."""
    suffix = _DISPLAY_UNITS.get(unit, f" {unit}")
    return f"{round(value, 2):g}{suffix}"


def _r(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def hub(h: Hub) -> dict[str, Any]:
    return {
        "hub_id": h.id,
        "name": h.name,
        "state": h.state,
        "region": h.region.value,
        "latitude": h.location.latitude,
        "longitude": h.location.longitude,
    }


def weather_metrics(hub_id: str, m: WeatherMetrics) -> dict[str, Any]:
    t = m.thresholds
    return {
        "hub_id": hub_id,
        "period": {"start": m.date_range.start, "end": m.date_range.end, "days": m.days},
        "days_with_missing_values": m.days_with_missing_values,
        "thresholds": {
            "snowfall_day_cm": t.snowfall_day_cm,
            "very_cold_day_min_temperature_c": t.very_cold_day_c,
            "hot_day_c": t.hot_day_c,
            "extreme_heat_day_c": t.extreme_heat_day_c,
            "heavy_precipitation_mm": t.heavy_precipitation_mm,
            "high_wind_gust_kmh": t.high_wind_gust_kmh,
            "severe_wind_gust_kmh": t.severe_wind_gust_kmh,
        },
        "snowfall_days": m.snowfall_days,
        "snowfall_day_percentage": _r(m.snowfall_day_percentage),
        "total_snowfall_cm": _r(m.total_snowfall_cm),
        "max_daily_snowfall_cm": _r(m.max_daily_snowfall_cm),
        "very_cold_days": m.very_cold_days,
        "min_temperature_c": _r(m.min_temperature_c),
        "hot_days": m.hot_days,
        "hot_day_percentage": _r(m.hot_day_percentage),
        "extreme_heat_days": m.extreme_heat_days,
        "max_temperature_c": _r(m.max_temperature_c),
        "heavy_precipitation_days": m.heavy_precipitation_days,
        "total_precipitation_mm": _r(m.total_precipitation_mm),
        "max_daily_precipitation_mm": _r(m.max_daily_precipitation_mm),
        "high_wind_days": m.high_wind_days,
        "severe_wind_days": m.severe_wind_days,
        "max_wind_gust_kmh": _r(m.max_wind_gust_kmh),
    }


def _hazard_common(hub_id: str, data: HazardData) -> dict[str, Any]:
    return {
        "hub_id": hub_id,
        "hazard": data.hazard_type.value,
        "period": {"start": data.date_range.start, "end": data.date_range.end},
        "source": data.source.name,
        "limitations": list(data.limitations),
    }


def flood_data(hub_id: str, data: FloodHazardData) -> dict[str, Any]:
    stats = calculate_flood_metrics(data)
    result = _hazard_common(hub_id, data) | {
        "river_cell": {
            "latitude": data.cell_location.latitude,
            "longitude": data.cell_location.longitude,
        },
        "observed_days": stats.observed_days,
        "max_discharge_m3s": _r(stats.max_discharge_m3s),
        "median_discharge_m3s": _r(stats.median_discharge_m3s),
        "mean_discharge_m3s": _r(stats.mean_discharge_m3s),
        "peak_to_median_ratio": _r(stats.peak_to_median_ratio),
    }
    if len(data.observations) <= MAX_DAILY_VALUES:
        result["daily_discharge_m3s"] = {
            o.date.isoformat(): _r(o.discharge_m3s) for o in data.observations
        }
    return result


def _event(e: TropicalCycloneEvent) -> dict[str, Any]:
    return {
        "storm_id": e.storm_id,
        "name": e.name,
        "start_date": e.start_date,
        "end_date": e.end_date,
        "closest_approach_km": _r(e.closest_approach_km),
        "closest_approach_time_utc": e.closest_approach_time,
        "classification_at_closest_approach": e.classification_at_closest_approach.value,
        "wind_at_closest_approach_kmh": _r(e.wind_at_closest_approach_kmh),
        "peak_classification": e.peak_classification.value,
        "peak_saffir_simpson_category": e.peak_category,
        "max_wind_kmh": _r(e.max_wind_kmh),
        "min_pressure_hpa": _r(e.min_pressure_hpa),
    }


def hurricane_data(hub_id: str, data: HurricaneHazardData) -> dict[str, Any]:
    return _hazard_common(hub_id, data) | {
        "search_radius_km": data.search_radius_km,
        "data_coverage_end": data.data_coverage_end,
        "event_count": len(data.events),
        "events": [_event(e) for e in data.events],
    }


HAZARD_DATA: dict[type[HazardData], Callable[[str, Any], dict[str, Any]]] = {
    FloodHazardData: flood_data,
    HurricaneHazardData: hurricane_data,
}


def hazard_data(hub_id: str, data: HazardData) -> dict[str, Any]:
    return HAZARD_DATA[type(data)](hub_id, data)


def _hazard_assessment(a: HazardRiskAssessment, overall: OverallRiskAssessment) -> dict[str, Any]:
    return {
        "hazard": a.hazard_type.value,
        "score": _r(a.score),
        "weight_in_overall": round(overall.applied_weights[a.hazard_type], 4),
        "contribution_to_overall": _r(overall.contribution_of(a.hazard_type)),
        "factors": [
            {
                "name": f.name,
                "description": f.description,
                "raw_value": _r(f.raw_value),
                "unit": f.unit,
                "display": _display(f.raw_value, f.unit),
                "scale": [f.scale_low, f.scale_high],
                "normalized_score": _r(f.normalized_score),
                "weight": round(f.weight, 4),
                "contribution": _r(f.contribution),
            }
            for f in a.factors
        ],
        "assumptions": list(a.assumptions),
        "warnings": list(a.warnings),
    }


def overall(a: OverallRiskAssessment) -> dict[str, Any]:
    return {
        "hub_id": a.hub.id,
        "hub_name": a.hub.name,
        "region": a.hub.region.value,
        "period": {"start": a.date_range.start, "end": a.date_range.end},
        "overall_score": _r(a.overall_score),
        "hazards": [_hazard_assessment(h, a) for h in a.hazard_assessments],
        "assumptions": list(a.assumptions),
        "warnings": list(a.warnings),
    }


def ranking(items: tuple[RankedHubRisk, ...]) -> dict[str, Any]:
    first = items[0].assessment if items else None
    return {
        "hazards": [h.value for h in first.hazards] if first else [],
        "applied_weights": (
            {h.value: round(w, 4) for h, w in first.applied_weights.items()} if first else {}
        ),
        "rankings": [
            {
                "rank": r.rank,
                "hub_id": r.hub.id,
                "hub_name": r.hub.name,
                "overall_score": _r(r.overall_score),
                "hazard_scores": {h.value: _r(s) for h, s in r.hazard_scores.items()},
            }
            for r in items
        ],
        "assessments": [overall(r.assessment) for r in items],
    }


def comparison(c: HubComparison) -> dict[str, Any]:
    return {
        "hub_ids": [a.hub.id for a in c.assessments],
        "highest_overall_hub_id": c.highest_overall_hub_id,
        "overall_scores": {a.hub.id: _r(a.overall_score) for a in c.assessments},
        "overall_differences": [
            {"hub_id": d.hub_id, "other_hub_id": d.other_hub_id, "difference": _r(d.difference)}
            for d in c.overall_differences
        ],
        "hazard_comparisons": [
            {
                "hazard": h.hazard_type.value,
                "scores": {hub_id: _r(score) for hub_id, score in h.scores},
                "highest_hub_id": h.highest_hub_id,
                "lowest_hub_id": h.lowest_hub_id,
                "spread": _r(h.spread),
            }
            for h in c.hazard_comparisons
        ],
        "assessments": [overall(a) for a in c.assessments],
    }


def assessment_warnings(a: OverallRiskAssessment) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys([*a.warnings, *(w for h in a.hazard_assessments for w in h.warnings)])
    )
