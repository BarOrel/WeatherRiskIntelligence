import datetime as dt

import pytest
from support.hurdat2_samples import ATLANTIC, PACIFIC

from weather_risk.application.errors import InvalidHazardDataError
from weather_risk.domain.models import CycloneClassification, GeoLocation, WeatherDateRange
from weather_risk.infrastructure.hazards.hurricane.hurdat2 import (
    parse_hurdat2,
    saffir_simpson_category,
)
from weather_risk.infrastructure.hazards.hurricane.proximity import find_events

MIAMI = GeoLocation(25.7617, -80.1918)
AUGUST_2020 = WeatherDateRange(dt.date(2020, 8, 1), dt.date(2020, 8, 31))
ALL_2020 = WeatherDateRange(dt.date(2020, 1, 1), dt.date(2020, 12, 31))


class TestParser:
    def test_parses_storms_and_points(self) -> None:
        storms = parse_hurdat2(ATLANTIC)

        assert [s.storm_id for s in storms] == ["AL012020", "AL022020", "AL032020"]
        alpha = storms[0]
        assert alpha.name == "ALPHA"
        assert alpha.peak_wind_kt == 90
        assert (alpha.start_date, alpha.end_date) == (dt.date(2020, 8, 1), dt.date(2020, 8, 1))
        first = alpha.points[0]
        assert first.time == dt.datetime(2020, 8, 1, 0, 0, tzinfo=dt.UTC)
        assert first.location == GeoLocation(24.0, -80.0)
        assert first.classification is CycloneClassification.TROPICAL_STORM
        assert first.wind_kmh == 92.6  # 50 kt
        assert first.pressure_hpa == 1000.0

    def test_missing_values_and_antimeridian(self) -> None:
        point = parse_hurdat2(PACIFIC)[0].points[1]

        assert point.wind_kmh is None
        assert point.pressure_hpa is None
        assert point.location.longitude == pytest.approx(179.0)  # 181.0W -> 179.0E
        assert point.classification is CycloneClassification.EXTRATROPICAL  # "ET" alias

    @pytest.mark.parametrize(
        "text",
        [
            "AL012020, ALPHA, 2,\n20200801, 0000,  , TS, 24.0N, 80.0W, 50, 1000,\n",
            "AL012020, ALPHA, x,\n",
            "AL012020, ALPHA, 1,\n20200801, 0000,  , ZZ, 24.0N, 80.0W, 50, 1000,\n",
            "AL012020, ALPHA, 1,\n20200801, 0000,  , TS, 24.0Q, 80.0W, 50, 1000,\n",
            "AL012020, ALPHA, 1,\n20201301, 0000,  , TS, 24.0N, 80.0W, 50, 1000,\n",
            "AL012020, ALPHA, 1,\n20200801, 0000,  , TS, 95.0N, 80.0W, 50, 1000,\n",
            "AL012020, ALPHA, 1,\n20200801, 0000\n",
        ],
        ids=["short", "bad-count", "status", "hemisphere", "date", "latitude", "truncated"],
    )
    def test_malformed_input(self, text: str) -> None:
        with pytest.raises(InvalidHazardDataError, match="HURDAT2 line"):
            parse_hurdat2(text)

    @pytest.mark.parametrize(
        ("wind_kt", "category"),
        [(63, None), (64, 1), (82, 1), (83, 2), (96, 3), (113, 4), (136, 4), (137, 5)],
    )
    def test_saffir_simpson(self, wind_kt: int, category: int | None) -> None:
        assert saffir_simpson_category(wind_kt) == category


class TestProximity:
    def test_finds_storm_within_radius(self) -> None:
        events = find_events(parse_hurdat2(ATLANTIC), MIAMI, AUGUST_2020, 200)

        assert [e.name for e in events] == ["ALPHA"]
        alpha = events[0]
        assert alpha.closest_approach_km == pytest.approx(19.3, abs=1)
        assert alpha.closest_approach_time.date() == dt.date(2020, 8, 1)
        assert alpha.classification_at_closest_approach is CycloneClassification.HURRICANE
        assert alpha.peak_classification is CycloneClassification.HURRICANE
        assert alpha.peak_category == 2  # 90 kt
        assert alpha.max_wind_kmh == pytest.approx(166.7)
        assert alpha.min_pressure_hpa == 980.0
        assert len(alpha.track) == 4

    def test_radius_filters_out_distant_storms(self) -> None:
        assert find_events(parse_hurdat2(ATLANTIC), MIAMI, AUGUST_2020, 10) == []

    def test_date_range_filters_storms(self) -> None:
        september = WeatherDateRange(dt.date(2020, 9, 1), dt.date(2020, 9, 30))

        assert find_events(parse_hurdat2(ATLANTIC), MIAMI, september, 200) == []

    def test_interpolation_catches_pass_between_fixes(self) -> None:
        october = WeatherDateRange(dt.date(2020, 10, 1), dt.date(2020, 10, 1))
        storms = parse_hurdat2(ATLANTIC)

        events = find_events(storms, MIAMI, october, 100)

        assert [e.name for e in events] == ["GAMMA"]
        assert events[0].closest_approach_km < 25
        assert all(
            MIAMI.distance_km(p.location) > 300 for p in storms[2].points
        )  # neither fix is close

    def test_events_sorted_by_closest_approach_time(self) -> None:
        events = find_events(parse_hurdat2(ATLANTIC), MIAMI, ALL_2020, 200)

        assert [e.name for e in events] == ["ALPHA", "GAMMA"]

    def test_storm_never_a_hurricane_has_no_category(self) -> None:
        october = WeatherDateRange(dt.date(2020, 10, 1), dt.date(2020, 10, 1))

        gamma = find_events(parse_hurdat2(ATLANTIC), MIAMI, october, 100)[0]

        assert gamma.peak_category is None
        assert gamma.peak_classification is CycloneClassification.TROPICAL_STORM
