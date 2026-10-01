import pytest
from support.risk import history_from

from weather_risk.domain.errors import DomainValidationError
from weather_risk.domain.risk import WeatherMetrics, WeatherMetricsCalculator, WeatherThresholds

# Ten hand-checkable days (defaults: 0 snow, 0 precip, Tmax 15, Tmin 5, gust 20).
ROWS: list[dict[str, float | None]] = [
    {"snowfall_cm": 0.2},  # trace: below 0.25 cm
    {"snowfall_cm": 0.25, "temperature_max_c": -2, "temperature_min_c": -15},  # snow, very cold
    {"snowfall_cm": 5.0, "temperature_max_c": -8, "temperature_min_c": -20},  # snow, very cold
    {"snowfall_cm": 12.0, "temperature_max_c": -3, "temperature_min_c": -14.9},  # snow
    {"temperature_max_c": 32.0, "temperature_min_c": 20},  # hot
    {"temperature_max_c": 38.0, "temperature_min_c": 22},  # hot + extreme
    {"temperature_max_c": 40.0, "temperature_min_c": 25, "precipitation_mm": 24.9},
    {"precipitation_mm": 25.0, "wind_gust_max_kmh": 72.0},  # heavy rain, high wind
    {"precipitation_mm": 30.0, "wind_gust_max_kmh": 93.0},  # heavy rain, severe wind
    {"snowfall_cm": None, "wind_gust_max_kmh": 100.0},  # missing snowfall, severe wind
]


@pytest.fixture
def metrics() -> WeatherMetrics:
    return WeatherMetricsCalculator(WeatherThresholds()).calculate(history_from(ROWS))


def test_snowfall(metrics: WeatherMetrics) -> None:
    assert metrics.days == 10
    assert metrics.snowfall_days == 3
    assert metrics.snowfall_day_percentage == pytest.approx(30.0)
    assert metrics.total_snowfall_cm == pytest.approx(17.45)
    assert metrics.max_daily_snowfall_cm == 12.0


def test_cold(metrics: WeatherMetrics) -> None:
    assert metrics.very_cold_days == 2
    assert metrics.very_cold_day_percentage == pytest.approx(20.0)
    assert metrics.min_temperature_c == -20.0


def test_heat(metrics: WeatherMetrics) -> None:
    assert metrics.hot_days == 3
    assert metrics.extreme_heat_days == 2
    assert metrics.hot_day_percentage == pytest.approx(30.0)
    assert metrics.max_temperature_c == 40.0


def test_precipitation(metrics: WeatherMetrics) -> None:
    assert metrics.heavy_precipitation_days == 2
    assert metrics.heavy_precipitation_day_percentage == pytest.approx(20.0)
    assert metrics.max_daily_precipitation_mm == 30.0
    assert metrics.total_precipitation_mm == pytest.approx(79.9)


def test_wind(metrics: WeatherMetrics) -> None:
    assert metrics.high_wind_days == 3
    assert metrics.severe_wind_days == 2
    assert metrics.max_wind_gust_kmh == 100.0


def test_missing_values_are_counted_and_never_meet_thresholds(metrics: WeatherMetrics) -> None:
    assert metrics.days_with_missing_values == 1


def test_thresholds_are_configurable() -> None:
    calculator = WeatherMetricsCalculator(WeatherThresholds(snowfall_day_cm=10.0, hot_day_c=35.0))

    metrics = calculator.calculate(history_from(ROWS))

    assert metrics.snowfall_days == 1
    assert metrics.hot_days == 2


def test_all_missing_values() -> None:
    metrics = WeatherMetricsCalculator(WeatherThresholds()).calculate(
        history_from([{"snowfall_cm": None, "temperature_max_c": None}])
    )

    assert metrics.max_daily_snowfall_cm is None
    assert metrics.max_temperature_c is None
    assert metrics.snowfall_day_percentage == 0.0


@pytest.mark.parametrize(
    "overrides",
    [
        {"snowfall_day_cm": 0},
        {"hot_day_c": 38.0, "extreme_heat_day_c": 38.0},
        {"high_wind_gust_kmh": 100.0, "severe_wind_gust_kmh": 90.0},
    ],
)
def test_invalid_thresholds(overrides: dict) -> None:
    with pytest.raises(DomainValidationError):
        WeatherThresholds(**overrides)
