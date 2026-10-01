from weather_risk.domain.models import HazardType
from weather_risk.domain.risk.models import HazardRiskAssessment, RiskAssessmentContext
from weather_risk.domain.risk.strategies.base import FactorMeasurement, RiskStrategy

SNOWFALL_FREQUENCY = "snowfall_frequency"
SNOWFALL_SEVERITY = "snowfall_severity"
COLD_EXPOSURE = "cold_exposure"

DEFAULT_WEIGHTS = {SNOWFALL_FREQUENCY: 0.4, SNOWFALL_SEVERITY: 0.4, COLD_EXPOSURE: 0.2}

# Normalization scales: value at which a factor scores 0 and 100.
SNOW_DAY_PCT_SCALE = (0.0, 15.0)  # ~55 snow days a year
MAX_DAILY_SNOW_CM_SCALE = (0.0, 30.0)  # ~12 in in one day is a major snowstorm
VERY_COLD_DAY_PCT_SCALE = (0.0, 15.0)  # ~55 very cold days a year


class WinterRiskStrategy(RiskStrategy):
    """Winter disruption exposure from snowfall frequency, snowfall severity and cold."""

    factor_names = (SNOWFALL_FREQUENCY, SNOWFALL_SEVERITY, COLD_EXPOSURE)

    @property
    def hazard_type(self) -> HazardType:
        return HazardType.WINTER

    def assess(self, context: RiskAssessmentContext) -> HazardRiskAssessment:
        weather = context.require_weather()
        t = weather.thresholds
        return self._score(
            [
                FactorMeasurement(
                    SNOWFALL_FREQUENCY,
                    f"Share of days with snowfall >= {t.snowfall_day_cm} cm",
                    weather.snowfall_day_percentage,
                    "percent",
                    *SNOW_DAY_PCT_SCALE,
                ),
                FactorMeasurement(
                    SNOWFALL_SEVERITY,
                    "Largest single-day snowfall",
                    weather.max_daily_snowfall_cm,
                    "cm",
                    *MAX_DAILY_SNOW_CM_SCALE,
                ),
                FactorMeasurement(
                    COLD_EXPOSURE,
                    f"Share of days with minimum temperature <= {t.very_cold_day_c} °C",
                    weather.very_cold_day_percentage,
                    "percent",
                    *VERY_COLD_DAY_PCT_SCALE,
                ),
            ],
            assumptions=[
                "Based on modelled daily weather (Open-Meteo reanalysis) at the hub coordinates.",
                "Does not account for ice storms/freezing rain or snow-removal capacity.",
            ],
        )
