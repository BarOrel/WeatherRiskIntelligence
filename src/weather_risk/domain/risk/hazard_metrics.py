"""Deterministic statistics derived from hazard datasets."""

import statistics
from dataclasses import dataclass

from weather_risk.domain.models import FloodHazardData, HurricaneHazardData

# Saffir-Simpson thresholds (1-minute sustained wind): Category 1 >= 119 km/h (64 kt),
# Category 3 ("major") >= 178 km/h (96 kt).
HURRICANE_WIND_KMH = 119.0
MAJOR_HURRICANE_WIND_KMH = 178.0

# Median discharge floor for the peak ratio, so near-dry channels do not produce huge ratios.
DISCHARGE_FLOOR_M3S = 1.0

DAYS_PER_YEAR = 365.25


@dataclass(frozen=True, slots=True)
class FloodMetrics:
    days: int
    observed_days: int
    max_discharge_m3s: float | None
    median_discharge_m3s: float | None
    mean_discharge_m3s: float | None

    @property
    def peak_to_median_ratio(self) -> float | None:
        """How far the period's peak rose above its typical (median) flow."""
        if self.max_discharge_m3s is None or self.median_discharge_m3s is None:
            return None
        return self.max_discharge_m3s / max(self.median_discharge_m3s, DISCHARGE_FLOOR_M3S)


def calculate_flood_metrics(data: FloodHazardData) -> FloodMetrics:
    values = [o.discharge_m3s for o in data.observations if o.discharge_m3s is not None]
    return FloodMetrics(
        days=data.date_range.days,
        observed_days=len(values),
        max_discharge_m3s=max(values, default=None),
        median_discharge_m3s=statistics.median(values) if values else None,
        mean_discharge_m3s=statistics.fmean(values) if values else None,
    )


@dataclass(frozen=True, slots=True)
class HurricaneMetrics:
    years: float
    event_count: int
    hurricane_strength_event_count: int
    """Events with hurricane-force wind (>= 119 km/h) at closest approach."""
    major_hurricane_event_count: int
    """Events with major-hurricane wind (>= 178 km/h) at closest approach."""
    closest_approach_km: float | None
    max_wind_at_closest_approach_kmh: float | None

    @property
    def event_rate_per_year(self) -> float:
        return self.event_count / self.years


def calculate_hurricane_metrics(data: HurricaneHazardData) -> HurricaneMetrics:
    winds = [
        e.wind_at_closest_approach_kmh
        for e in data.events
        if e.wind_at_closest_approach_kmh is not None
    ]
    return HurricaneMetrics(
        years=data.date_range.days / DAYS_PER_YEAR,
        event_count=len(data.events),
        hurricane_strength_event_count=sum(1 for w in winds if w >= HURRICANE_WIND_KMH),
        major_hurricane_event_count=sum(1 for w in winds if w >= MAJOR_HURRICANE_WIND_KMH),
        closest_approach_km=min((e.closest_approach_km for e in data.events), default=None),
        max_wind_at_closest_approach_kmh=max(winds, default=None),
    )
