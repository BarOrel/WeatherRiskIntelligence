import math

import pytest

from weather_risk.domain.errors import DomainValidationError
from weather_risk.domain.models import GeoLocation


def test_creates_valid_location() -> None:
    location = GeoLocation(latitude=32.7767, longitude=-96.797)

    assert location.latitude == 32.7767
    assert location.longitude == -96.797


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(-90, -180), (90, 180), (0, 0)],
)
def test_accepts_boundary_values(latitude: float, longitude: float) -> None:
    GeoLocation(latitude=latitude, longitude=longitude)


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(-90.01, 0), (90.01, 0), (0, -180.01), (0, 180.01)],
)
def test_rejects_out_of_range_coordinates(latitude: float, longitude: float) -> None:
    with pytest.raises(DomainValidationError):
        GeoLocation(latitude=latitude, longitude=longitude)


@pytest.mark.parametrize("bad", [math.nan, math.inf, "32.7", None, True])
def test_rejects_non_numeric_or_non_finite(bad: object) -> None:
    with pytest.raises(DomainValidationError):
        GeoLocation(latitude=bad, longitude=0)  # type: ignore[arg-type]


def test_is_a_value_object() -> None:
    a = GeoLocation(latitude=10.0, longitude=20.0)
    b = GeoLocation(latitude=10.0, longitude=20.0)

    assert a == b
    assert hash(a) == hash(b)
    with pytest.raises(AttributeError):
        a.latitude = 11.0  # type: ignore[misc]
