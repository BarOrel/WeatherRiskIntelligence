import datetime as dt
import math

import pytest
from support.fakes import DENVER, make_history, make_observation

from weather_risk.domain.errors import DomainValidationError
from weather_risk.domain.models import WeatherDateRange, WeatherHistory

JAN_1 = dt.date(2024, 1, 1)
JAN_3 = dt.date(2024, 1, 3)


class TestWeatherDateRange:
    def test_days_and_dates_are_inclusive(self) -> None:
        date_range = WeatherDateRange(JAN_1, JAN_3)

        assert date_range.days == 3
        assert date_range.dates() == [JAN_1, dt.date(2024, 1, 2), JAN_3]

    def test_single_day_range(self) -> None:
        assert WeatherDateRange(JAN_1, JAN_1).days == 1

    def test_rejects_start_after_end(self) -> None:
        with pytest.raises(DomainValidationError, match="must not be after"):
            WeatherDateRange(JAN_3, JAN_1)

    def test_rejects_datetime(self) -> None:
        with pytest.raises(DomainValidationError, match="must be a date"):
            WeatherDateRange(dt.datetime(2024, 1, 1, 12), JAN_3)

    def test_contains(self) -> None:
        date_range = WeatherDateRange(JAN_1, JAN_3)

        assert dt.date(2024, 1, 2) in date_range
        assert dt.date(2024, 1, 4) not in date_range


class TestDailyWeatherObservation:
    def test_valid_observation(self) -> None:
        observation = make_observation(JAN_1)

        assert observation.date == JAN_1
        assert observation.snowfall_cm == 0.0

    def test_missing_measurements_are_allowed(self) -> None:
        observation = make_observation(
            JAN_1, precipitation_mm=None, temperature_max_c=None, wind_gust_max_kmh=None
        )

        assert observation.precipitation_mm is None

    def test_negative_temperatures_are_allowed(self) -> None:
        make_observation(JAN_1, temperature_max_c=-5.0, temperature_min_c=-20.0)

    @pytest.mark.parametrize(
        "field",
        ["precipitation_mm", "rain_mm", "snowfall_cm", "wind_speed_max_kmh", "wind_gust_max_kmh"],
    )
    def test_rejects_negative_amounts(self, field: str) -> None:
        with pytest.raises(DomainValidationError, match=field):
            make_observation(JAN_1, **{field: -0.1})

    @pytest.mark.parametrize("bad", [math.nan, math.inf, "1.0", True])
    def test_rejects_non_finite_or_non_numeric(self, bad: object) -> None:
        with pytest.raises(DomainValidationError, match="rain_mm"):
            make_observation(JAN_1, rain_mm=bad)  # type: ignore[arg-type]

    def test_rejects_min_temperature_above_max(self) -> None:
        with pytest.raises(DomainValidationError, match="temperature_min_c"):
            make_observation(JAN_1, temperature_max_c=1.0, temperature_min_c=2.0)


class TestWeatherHistory:
    def test_valid_history(self) -> None:
        history = make_history()

        assert history.timezone == "America/Denver"
        assert [o.date for o in history.observations] == history.date_range.dates()

    def test_list_of_observations_is_stored_as_tuple(self) -> None:
        date_range = WeatherDateRange(JAN_1, JAN_1)
        history = WeatherHistory(DENVER, date_range, "UTC", [make_observation(JAN_1)])  # type: ignore[arg-type]

        assert isinstance(history.observations, tuple)

    def test_rejects_observation_outside_range(self) -> None:
        with pytest.raises(DomainValidationError, match="outside"):
            WeatherHistory(
                DENVER,
                WeatherDateRange(JAN_1, JAN_3),
                "UTC",
                (make_observation(dt.date(2024, 1, 4)),),
            )

    def test_rejects_unordered_or_duplicate_dates(self) -> None:
        with pytest.raises(DomainValidationError, match="ascending"):
            WeatherHistory(
                DENVER,
                WeatherDateRange(JAN_1, JAN_3),
                "UTC",
                (make_observation(JAN_3), make_observation(JAN_1)),
            )
        with pytest.raises(DomainValidationError, match="ascending"):
            WeatherHistory(
                DENVER,
                WeatherDateRange(JAN_1, JAN_3),
                "UTC",
                (make_observation(JAN_1), make_observation(JAN_1)),
            )

    def test_rejects_blank_timezone(self) -> None:
        with pytest.raises(DomainValidationError, match="timezone"):
            WeatherHistory(DENVER, WeatherDateRange(JAN_1, JAN_1), " ", ())
