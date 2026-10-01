import datetime as dt
from dataclasses import replace

import pytest
from support.fakes import DENVER, make_flood_data, make_hurricane_data, make_track_point

from weather_risk.domain.errors import DomainValidationError
from weather_risk.domain.models import (
    CycloneClassification,
    DailyRiverDischarge,
    HazardType,
    WeatherDateRange,
)

JAN_1 = dt.date(2024, 1, 1)


def test_hazard_types_are_fixed_per_dataset() -> None:
    assert make_flood_data().hazard_type is HazardType.FLOOD
    assert make_hurricane_data().hazard_type is HazardType.HURRICANE


class TestFlood:
    def test_valid_data(self) -> None:
        data = make_flood_data()

        assert [o.discharge_m3s for o in data.observations] == [10.0, 11.0, 12.0]
        assert data.limitations == ("Signal only.",)

    def test_missing_discharge_is_allowed(self) -> None:
        assert DailyRiverDischarge(JAN_1, None).discharge_m3s is None

    def test_rejects_negative_discharge(self) -> None:
        with pytest.raises(DomainValidationError, match="discharge_m3s"):
            DailyRiverDischarge(JAN_1, -1.0)

    def test_rejects_observation_outside_range(self) -> None:
        data = make_flood_data()

        with pytest.raises(DomainValidationError, match="outside"):
            replace(data, observations=(DailyRiverDischarge(dt.date(2023, 12, 31), 1.0),))

    def test_rejects_blank_limitation(self) -> None:
        with pytest.raises(DomainValidationError, match="limitation"):
            replace(make_flood_data(), limitations=(" ",))


class TestHurricane:
    def test_valid_data(self) -> None:
        event = make_hurricane_data().events[0]

        assert event.peak_category == 1
        assert event.track[0].classification is CycloneClassification.HURRICANE

    def test_rejects_non_positive_radius(self) -> None:
        with pytest.raises(DomainValidationError, match="search_radius_km"):
            replace(make_hurricane_data(), search_radius_km=0)

    @pytest.mark.parametrize("category", [0, 6])
    def test_rejects_invalid_category(self, category: int) -> None:
        event = make_hurricane_data().events[0]

        with pytest.raises(DomainValidationError, match="peak_category"):
            replace(event, peak_category=category)

    def test_rejects_event_without_track(self) -> None:
        with pytest.raises(DomainValidationError, match="track point"):
            replace(make_hurricane_data().events[0], track=())

    def test_track_time_must_be_timezone_aware(self) -> None:
        with pytest.raises(DomainValidationError, match="timezone-aware"):
            make_track_point(dt.datetime(2024, 1, 1, 12), DENVER)

    def test_no_events_is_valid(self) -> None:
        data = replace(
            make_hurricane_data(), events=(), date_range=WeatherDateRange(JAN_1, JAN_1)
        )

        assert data.events == ()
