from weather_risk.domain.models import HazardType
from weather_risk.domain.risk.hazard_metrics import DISCHARGE_FLOOR_M3S, calculate_flood_metrics
from weather_risk.domain.risk.models import HazardRiskAssessment, RiskAssessmentContext
from weather_risk.domain.risk.strategies.base import FactorMeasurement, RiskStrategy

HEAVY_PRECIPITATION_FREQUENCY = "heavy_precipitation_frequency"
PEAK_DAILY_PRECIPITATION = "peak_daily_precipitation"
RIVER_DISCHARGE_PEAK_RATIO = "river_discharge_peak_ratio"

DEFAULT_WEIGHTS = {
    HEAVY_PRECIPITATION_FREQUENCY: 0.35,
    PEAK_DAILY_PRECIPITATION: 0.25,
    RIVER_DISCHARGE_PEAK_RATIO: 0.4,
}

HEAVY_PRECIPITATION_DAY_PCT_SCALE = (0.0, 6.0)  # ~22 heavy-rain days a year
PEAK_DAILY_PRECIPITATION_MM_SCALE = (25.0, 150.0)
DISCHARGE_PEAK_RATIO_SCALE = (1.0, 50.0)  # 1 = peak equals typical flow


class FloodRiskStrategy(RiskStrategy):
    """Flood exposure from heavy rainfall (weather) and river discharge (GloFAS)."""

    factor_names = (
        HEAVY_PRECIPITATION_FREQUENCY,
        PEAK_DAILY_PRECIPITATION,
        RIVER_DISCHARGE_PEAK_RATIO,
    )
    required_hazard_data = frozenset({HazardType.FLOOD})

    @property
    def hazard_type(self) -> HazardType:
        return HazardType.FLOOD

    def assess(self, context: RiskAssessmentContext) -> HazardRiskAssessment:
        weather = context.require_weather()
        flood = calculate_flood_metrics(context.require_flood())
        warnings = []
        if flood.observed_days < flood.days:
            warnings.append(
                f"River discharge available for {flood.observed_days} of {flood.days} days."
            )
        return self._score(
            [
                FactorMeasurement(
                    HEAVY_PRECIPITATION_FREQUENCY,
                    f"Share of days with precipitation >= "
                    f"{weather.thresholds.heavy_precipitation_mm} mm",
                    weather.heavy_precipitation_day_percentage,
                    "percent",
                    *HEAVY_PRECIPITATION_DAY_PCT_SCALE,
                ),
                FactorMeasurement(
                    PEAK_DAILY_PRECIPITATION,
                    "Largest single-day precipitation",
                    weather.max_daily_precipitation_mm,
                    "mm",
                    *PEAK_DAILY_PRECIPITATION_MM_SCALE,
                ),
                FactorMeasurement(
                    RIVER_DISCHARGE_PEAK_RATIO,
                    f"Peak river discharge divided by the period's median discharge "
                    f"(median floored at {DISCHARGE_FLOOR_M3S} m³/s)",
                    flood.peak_to_median_ratio,
                    "ratio",
                    *DISCHARGE_PEAK_RATIO_SCALE,
                ),
            ],
            assumptions=[
                "River discharge (Copernicus GloFAS via Open-Meteo) is a flood-hazard signal for "
                "the nearest modelled river cell, not a site-level flood damage probability.",
                "Discharge is judged relative to the same river's median over the period, so "
                "large and small rivers are comparable; longer periods give a steadier baseline.",
                "Snowmelt-fed rivers have a regular seasonal peak, which raises the peak ratio "
                "without implying flooding.",
                "Does not account for drainage, elevation, storm surge or flood defences.",
            ],
            warnings=warnings,
        )
