import math

import pytest

from weather_risk.domain.models import GeoLocation
from weather_risk.domain.models.geo_location import EARTH_MEAN_RADIUS_KM

ONE_DEGREE_KM = EARTH_MEAN_RADIUS_KM * math.pi / 180  # ≈ 111.195 km


def test_same_point_is_zero() -> None:
    point = GeoLocation(25.7617, -80.1918)

    assert point.distance_km(point) == 0.0


def test_one_degree_of_latitude() -> None:
    assert GeoLocation(10, 20).distance_km(GeoLocation(11, 20)) == pytest.approx(ONE_DEGREE_KM)


def test_one_degree_of_longitude_on_equator() -> None:
    assert GeoLocation(0, 0).distance_km(GeoLocation(0, 1)) == pytest.approx(ONE_DEGREE_KM)


def test_longitude_degree_shrinks_with_latitude() -> None:
    at_60 = GeoLocation(60, 0).distance_km(GeoLocation(60, 1))

    assert at_60 == pytest.approx(ONE_DEGREE_KM / 2, rel=1e-3)


def test_known_city_pair() -> None:
    big_ben = GeoLocation(51.5007, -0.1246)
    statue_of_liberty = GeoLocation(40.6892, -74.0445)

    assert big_ben.distance_km(statue_of_liberty) == pytest.approx(5574.8, rel=1e-3)


def test_is_symmetric() -> None:
    miami, houston = GeoLocation(25.7617, -80.1918), GeoLocation(29.7604, -95.3698)

    assert miami.distance_km(houston) == pytest.approx(houston.distance_km(miami))
    assert miami.distance_km(houston) == pytest.approx(1550, rel=0.01)


def test_shortest_path_crosses_antimeridian() -> None:
    assert GeoLocation(0, 179.5).distance_km(GeoLocation(0, -179.5)) == pytest.approx(
        ONE_DEGREE_KM
    )


def test_antipodal_points() -> None:
    assert GeoLocation(0, 0).distance_km(GeoLocation(0, 180)) == pytest.approx(
        math.pi * EARTH_MEAN_RADIUS_KM
    )
    assert GeoLocation(90, 0).distance_km(GeoLocation(-90, 0)) == pytest.approx(
        math.pi * EARTH_MEAN_RADIUS_KM
    )
