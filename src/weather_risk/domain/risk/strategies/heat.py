from weather_risk.domain.models import HazardType
from weather_risk.domain.risk.models import HazardRiskAssessment, RiskAssessmentContext
from weather_risk.domain.risk.strategies.base import FactorMeasurement, RiskStrategy

HOT_DAY_FREQUENCY = "hot_day_frequency"
EXTREME_HEAT_FREQUENCY = "extreme_heat_frequency"
PEAK_TEMPERATURE = "peak_temperature"

DEFAULT_WEIGHTS = {HOT_DAY_FREQUENCY: 0.4, EXTREME_HEAT_FREQUENCY: 0.3, PEAK_TEMPERATURE: 0.3}

HOT_DAY_PCT_SCALE = (0.0, 35.0)  # ~128 hot days a year
EXTREME_HEAT_DAY_PCT_SCALE = (0.0, 5.0)  # ~18 extreme-heat days a year
PEAK_TEMPERATURE_C_SCALE = (30.0, 43.0)


class HeatRiskStrategy(RiskStrategy):
    """Heat exposure from hot-day frequency, extreme-heat frequency and peak temperature."""

    factor_names = (HOT_DAY_FREQUENCY, EXTREME_HEAT_FREQUENCY, PEAK_TEMPERATURE)

    @property
    def hazard_type(self) -> HazardType:
        return HazardType.HEAT

    def assess(self, context: RiskAssessmentContext) -> HazardRiskAssessment:
        weather = context.require_weather()
        t = weather.thresholds
        return self._score(
            [
                FactorMeasurement(
                    HOT_DAY_FREQUENCY,
                    f"Share of days with maximum temperature >= {t.hot_day_c} °C",
                    weather.hot_day_percentage,
                    "percent",
                    *HOT_DAY_PCT_SCALE,
                ),
                FactorMeasurement(
                    EXTREME_HEAT_FREQUENCY,
                    f"Share of days with maximum temperature >= {t.extreme_heat_day_c} °C",
                    weather.extreme_heat_day_percentage,
                    "percent",
                    *EXTREME_HEAT_DAY_PCT_SCALE,
                ),
                FactorMeasurement(
                    PEAK_TEMPERATURE,
                    "Highest daily maximum temperature",
                    weather.max_temperature_c,
                    "°C",
                    *PEAK_TEMPERATURE_C_SCALE,
                ),
            ],
            assumptions=[
                "Based on modelled daily air temperature; humidity/heat index is not included.",
            ],
        )
