from dataclasses import replace

import pytest
from support.risk import (
    DENVER_HUB,
    TEN_YEARS,
    days_range,
    flood_data,
    hurricane_data,
    make_event,
    make_metrics,
)

from weather_risk.domain.errors import DomainValidationError
from weather_risk.domain.models import HazardType, TropicalCycloneEvent
from weather_risk.domain.risk import (
    FloodRiskStrategy,
    HazardRiskAssessment,
    HeatRiskStrategy,
    HurricaneRiskStrategy,
    RiskAssessmentContext,
    WinterRiskStrategy,
)
from weather_risk.domain.risk.strategies import flood, heat, hurricane, winter
from weather_risk.domain.risk.strategies.hurricane import event_impact


def context(**kwargs: object) -> RiskAssessmentContext:
    kwargs.setdefault("date_range", days_range(100))
    return RiskAssessmentContext(hub=DENVER_HUB, **kwargs)  # type: ignore[arg-type]


def factors(assessment: HazardRiskAssessment) -> dict[str, tuple[float, float, float]]:
    """name -> (normalized_score, weight, contribution)"""
    return {f.name: (f.normalized_score, f.weight, f.contribution) for f in assessment.factors}


def assert_factors(
    assessment: HazardRiskAssessment, expected: dict[str, tuple[float, float, float]]
) -> None:
    actual = factors(assessment)
    assert actual.keys() == expected.keys()
    for name, values in expected.items():
        assert actual[name] == pytest.approx(values), name


class TestFactorWeights:
    def test_must_match_factor_names_exactly(self) -> None:
        with pytest.raises(DomainValidationError, match="factor weights"):
            WinterRiskStrategy({"snowfall_frequency": 1.0})

    def test_must_have_a_positive_weight(self) -> None:
        with pytest.raises(DomainValidationError, match="positive"):
            WinterRiskStrategy({name: 0 for name in WinterRiskStrategy.factor_names})

    def test_are_normalized(self) -> None:
        strategy = WinterRiskStrategy(
            {"snowfall_frequency": 2, "snowfall_severity": 2, "cold_exposure": 1}
        )

        result = strategy.assess(context(weather=make_metrics()))

        assert [f.weight for f in result.factors] == pytest.approx([0.4, 0.4, 0.2])


class TestWinter:
    strategy = WinterRiskStrategy(winter.DEFAULT_WEIGHTS)

    def test_exact_contributions(self) -> None:
        # 6% snow days -> 40; 15 cm max -> 50; 3% very cold days -> 20
        weather = make_metrics(snowfall_days=6, max_daily_snowfall_cm=15.0, very_cold_days=3)

        result = self.strategy.assess(context(weather=weather))

        assert result.hazard_type is HazardType.WINTER
        assert_factors(
            result,
            {
                "snowfall_frequency": (40.0, 0.4, 16.0),
                "snowfall_severity": (50.0, 0.4, 20.0),
                "cold_exposure": (20.0, 0.2, 4.0),
            }
        )
        assert result.score == pytest.approx(40.0)
        assert sum(f.contribution for f in result.factors) == pytest.approx(result.score)

    def test_low_exposure(self) -> None:
        assert self.strategy.assess(context(weather=make_metrics())).score == 0.0

    def test_high_exposure_is_capped_at_100(self) -> None:
        weather = make_metrics(snowfall_days=50, max_daily_snowfall_cm=80.0, very_cold_days=40)

        assert self.strategy.assess(context(weather=weather)).score == 100.0

    def test_factor_evidence(self) -> None:
        weather = make_metrics(snowfall_days=6)

        factor = self.strategy.assess(context(weather=weather)).factors[0]

        assert (factor.raw_value, factor.unit) == (6.0, "percent")
        assert (factor.scale_low, factor.scale_high) == winter.SNOW_DAY_PCT_SCALE
        assert "0.25 cm" in factor.description

    def test_missing_measurement_is_excluded_with_warning(self) -> None:
        weather = make_metrics(snowfall_days=6, max_daily_snowfall_cm=None)

        result = self.strategy.assess(context(weather=weather))

        assert [f.name for f in result.factors] == ["snowfall_frequency", "cold_exposure"]
        assert [f.weight for f in result.factors] == pytest.approx([2 / 3, 1 / 3])
        assert any("snowfall_severity" in w for w in result.warnings)

    def test_requires_weather(self) -> None:
        with pytest.raises(DomainValidationError, match="weather"):
            self.strategy.assess(context())


class TestHeat:
    strategy = HeatRiskStrategy(heat.DEFAULT_WEIGHTS)

    def test_exact_contributions(self) -> None:
        # 14% hot -> 40; 2% extreme -> 40; 36.5 °C -> 50
        weather = make_metrics(hot_days=14, extreme_heat_days=2, max_temperature_c=36.5)

        result = self.strategy.assess(context(weather=weather))

        assert_factors(
            result,
            {
                "hot_day_frequency": (40.0, 0.4, 16.0),
                "extreme_heat_frequency": (40.0, 0.3, 12.0),
                "peak_temperature": (50.0, 0.3, 15.0),
            }
        )
        assert result.score == pytest.approx(43.0)

    def test_low_and_high_exposure(self) -> None:
        cool = make_metrics(max_temperature_c=25.0)
        scorching = make_metrics(hot_days=60, extreme_heat_days=20, max_temperature_c=47.0)

        assert self.strategy.assess(context(weather=cool)).score == 0.0
        assert self.strategy.assess(context(weather=scorching)).score == 100.0


class TestFlood:
    strategy = FloodRiskStrategy(flood.DEFAULT_WEIGHTS)
    # median 10 m³/s, peak 255 -> ratio 25.5 -> 50
    river = flood_data([10.0] * 98 + [255.0, 10.0])

    def test_exact_contributions(self) -> None:
        # 3% heavy-rain days -> 50; 87.5 mm -> 50
        weather = make_metrics(heavy_precipitation_days=3, max_daily_precipitation_mm=87.5)

        result = self.strategy.assess(context(weather=weather, flood=self.river))

        assert result.hazard_type is HazardType.FLOOD
        assert_factors(
            result,
            {
                "heavy_precipitation_frequency": (50.0, 0.35, 17.5),
                "peak_daily_precipitation": (50.0, 0.25, 12.5),
                "river_discharge_peak_ratio": (50.0, 0.4, 20.0),
            }
        )
        assert result.score == pytest.approx(50.0)

    def test_weather_input_influences_score(self) -> None:
        wet = make_metrics(heavy_precipitation_days=6, max_daily_precipitation_mm=150.0)

        result = self.strategy.assess(context(weather=wet, flood=self.river))

        assert result.score == pytest.approx(0.35 * 100 + 0.25 * 100 + 0.4 * 50)

    def test_river_input_influences_score(self) -> None:
        steady = flood_data([10.0] * 100)

        result = self.strategy.assess(context(weather=make_metrics(), flood=steady))

        assert factors(result)["river_discharge_peak_ratio"][0] == 0.0
        assert result.score == 0.0

    def test_missing_discharge_is_excluded_with_warning(self) -> None:
        weather = make_metrics(heavy_precipitation_days=3, max_daily_precipitation_mm=87.5)

        result = self.strategy.assess(context(weather=weather, flood=flood_data([None] * 100)))

        assert "river_discharge_peak_ratio" not in factors(result)
        assert result.score == pytest.approx(50.0)
        assert any("River discharge available for 0 of 100" in w for w in result.warnings)

    def test_states_glofas_limitation(self) -> None:
        result = self.strategy.assess(context(weather=make_metrics(), flood=self.river))

        assert any("not a site-level flood damage probability" in a for a in result.assumptions)

    def test_requires_flood_data(self) -> None:
        with pytest.raises(DomainValidationError, match="flood"):
            self.strategy.assess(context(weather=make_metrics()))


class TestHurricane:
    strategy = HurricaneRiskStrategy(hurricane.DEFAULT_WEIGHTS)

    def assess(self, *events: TropicalCycloneEvent) -> HazardRiskAssessment:
        return self.strategy.assess(
            context(date_range=TEN_YEARS, hurricane=hurricane_data(*events, date_range=TEN_YEARS))
        )

    def test_does_not_need_weather(self) -> None:
        assert HurricaneRiskStrategy.requires_weather is False
        assert self.assess().hazard_type is HazardType.HURRICANE

    def test_no_events_scores_zero(self) -> None:
        assert self.assess().score == 0.0

    @pytest.mark.parametrize(
        ("wind_kmh", "distance_km", "impact"),
        [
            (50.0, 20.0, 0.1),  # tropical depression, close
            (100.0, 20.0, 0.3),  # tropical storm, close
            (150.0, 20.0, 0.6),  # Category 1-2, close
            (210.0, 20.0, 1.0),  # Category 3+, close
            (210.0, 80.0, 0.6),  # Category 3+, 50-100 km
            (210.0, 180.0, 0.3),  # Category 3+, beyond 100 km
            (None, 20.0, 0.1),  # unknown wind
        ],
    )
    def test_event_impact_bands(
        self, wind_kmh: float | None, distance_km: float, impact: float
    ) -> None:
        assert event_impact(make_event(wind_kmh, distance_km)) == pytest.approx(impact)

    def test_depression_contributes_far_less_than_major_hurricane(self) -> None:
        depression = self.assess(make_event(50.0, 20.0))
        major = self.assess(make_event(230.0, 20.0))

        assert major.score > depression.score * 3
        assert factors(depression)["cyclone_frequency"] == factors(major)["cyclone_frequency"]

    def test_closer_storm_scores_higher(self) -> None:
        assert self.assess(make_event(230.0, 30.0)).score > self.assess(make_event(230.0, 150.0)).score

    def test_exact_contributions(self) -> None:
        events = [make_event(210.0, 20.0, "AL01"), make_event(100.0, 80.0, "AL02")]
        years = TEN_YEARS.days / 365.25
        # impacts 1.0 and 0.3*0.6=0.18 -> rate 1.18/years; frequency 2/years
        result = self.assess(*events)

        expected_frequency = (2 / years) / 1.5 * 100
        expected_rate = (1.18 / years) / 0.5 * 100
        assert_factors(
            result,
            {
                "cyclone_frequency": (expected_frequency, 0.3, 0.3 * expected_frequency),
                "impact_rate": (expected_rate, 0.4, 0.4 * expected_rate),
                "worst_event_impact": (100.0, 0.3, 30.0),
            }
        )

    def test_warns_on_short_periods(self) -> None:
        short = days_range(365)
        result = self.strategy.assess(
            context(date_range=short, hurricane=hurricane_data(date_range=short))
        )

        assert any("noisy" in w for w in result.warnings)

    def test_states_when_climatology_period_differs_from_request(self) -> None:
        result = self.strategy.assess(
            context(date_range=days_range(365), hurricane=hurricane_data(date_range=TEN_YEARS))
        )

        assert any("not only the requested period" in a for a in result.assumptions)

    def test_warns_when_range_exceeds_dataset_coverage(self) -> None:
        data = replace(hurricane_data(), data_coverage_end=TEN_YEARS.start)

        result = self.strategy.assess(context(date_range=TEN_YEARS, hurricane=data))

        assert any("only covers storms through" in w for w in result.warnings)
