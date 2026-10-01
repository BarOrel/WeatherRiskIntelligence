from weather_risk.domain.models import HazardType, TropicalCycloneEvent
from weather_risk.domain.risk.hazard_metrics import (
    HURRICANE_WIND_KMH,
    MAJOR_HURRICANE_WIND_KMH,
    calculate_hurricane_metrics,
)
from weather_risk.domain.risk.models import HazardRiskAssessment, RiskAssessmentContext
from weather_risk.domain.risk.strategies.base import FactorMeasurement, RiskStrategy

CYCLONE_FREQUENCY = "cyclone_frequency"
IMPACT_RATE = "impact_rate"
WORST_EVENT_IMPACT = "worst_event_impact"

DEFAULT_WEIGHTS = {CYCLONE_FREQUENCY: 0.3, IMPACT_RATE: 0.4, WORST_EVENT_IMPACT: 0.3}

CYCLONE_RATE_SCALE = (0.0, 1.5)  # events per year within the search radius
IMPACT_RATE_SCALE = (0.0, 0.5)  # summed event impact per year
WORST_IMPACT_SCALE = (0.0, 1.0)

TROPICAL_STORM_WIND_KMH = 63.0

# Intensity at closest approach (wind, km/h; Saffir-Simpson bands) -> weight.
INTENSITY_BANDS = (
    (MAJOR_HURRICANE_WIND_KMH, 1.0),  # Category 3-5
    (HURRICANE_WIND_KMH, 0.6),  # Category 1-2
    (TROPICAL_STORM_WIND_KMH, 0.3),  # tropical storm
)
WEAK_OR_UNKNOWN_INTENSITY = 0.1  # depression / remnant / no wind recorded

# Distance of the storm centre from the hub (km) -> weight. Beyond the radius: not an event.
PROXIMITY_BANDS = ((50.0, 1.0), (100.0, 0.6))
OUTER_PROXIMITY = 0.3

MIN_RELIABLE_YEARS = 10


def event_intensity(event: TropicalCycloneEvent) -> float:
    wind = event.wind_at_closest_approach_kmh
    if wind is None:
        return WEAK_OR_UNKNOWN_INTENSITY
    for threshold, weight in INTENSITY_BANDS:
        if wind >= threshold:
            return weight
    return WEAK_OR_UNKNOWN_INTENSITY


def event_proximity(event: TropicalCycloneEvent) -> float:
    for max_distance, weight in PROXIMITY_BANDS:
        if event.closest_approach_km <= max_distance:
            return weight
    return OUTER_PROXIMITY


def event_impact(event: TropicalCycloneEvent) -> float:
    """0..1: a Category 3+ storm passing within 50 km scores 1; a distant depression 0.03."""
    return event_intensity(event) * event_proximity(event)


class HurricaneRiskStrategy(RiskStrategy):
    """Tropical cyclone exposure from NOAA/NHC best-track events near the hub.

    Uses official event data only; it does not infer cyclones from local wind observations.
    """

    factor_names = (CYCLONE_FREQUENCY, IMPACT_RATE, WORST_EVENT_IMPACT)
    requires_weather = False
    required_hazard_data = frozenset({HazardType.HURRICANE})

    @property
    def hazard_type(self) -> HazardType:
        return HazardType.HURRICANE

    def assess(self, context: RiskAssessmentContext) -> HazardRiskAssessment:
        data = context.require_hurricane()
        metrics = calculate_hurricane_metrics(data)
        impacts = [event_impact(e) for e in data.events]

        assumptions = []
        if data.date_range != context.date_range:
            assumptions.append(
                f"Tropical cyclone statistics use the period {data.date_range.start} to "
                f"{data.date_range.end} ({metrics.years:.0f} years), not only the requested "
                "period, because cyclone exposure is only meaningful over decades."
            )
        warnings = []
        if metrics.years < MIN_RELIABLE_YEARS:
            warnings.append(
                f"Only {metrics.years:.1f} years analysed; tropical cyclone frequency is noisy "
                f"below {MIN_RELIABLE_YEARS} years."
            )
        if data.data_coverage_end is not None and data.date_range.end > data.data_coverage_end:
            warnings.append(
                f"NHC best-track data only covers storms through {data.data_coverage_end}."
            )

        return self._score(
            [
                FactorMeasurement(
                    CYCLONE_FREQUENCY,
                    f"Tropical cyclones per year passing within {data.search_radius_km:g} km "
                    f"({metrics.event_count} events, {metrics.hurricane_strength_event_count} at "
                    f"hurricane strength, {metrics.major_hurricane_event_count} major)",
                    metrics.event_rate_per_year,
                    "events/year",
                    *CYCLONE_RATE_SCALE,
                ),
                FactorMeasurement(
                    IMPACT_RATE,
                    "Sum of event impacts per year (impact = intensity x proximity weight)",
                    sum(impacts) / metrics.years,
                    "impact/year",
                    *IMPACT_RATE_SCALE,
                ),
                FactorMeasurement(
                    WORST_EVENT_IMPACT,
                    "Highest single-event impact (1 = Category 3+ within 50 km)",
                    max(impacts, default=0.0),
                    "impact",
                    *WORST_IMPACT_SCALE,
                ),
            ],
            assumptions=[
                *assumptions,
                "Events are NOAA/NHC HURDAT2 storms whose centre passed within the search radius.",
                "Intensity weight by wind at closest approach: Category 3+ 1.0, Category 1-2 0.6, "
                "tropical storm 0.3, weaker/unknown 0.1.",
                "Proximity weight by centre distance: <= 50 km 1.0, <= 100 km 0.6, farther 0.3.",
                "Storm surge and inland rainfall flooding are not modelled here.",
            ],
            warnings=warnings,
        )
