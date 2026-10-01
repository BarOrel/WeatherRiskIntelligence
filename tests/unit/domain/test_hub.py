from typing import Any

import pytest

from weather_risk.domain.errors import DomainValidationError
from weather_risk.domain.models import GeoLocation, Hub, Region


def make_hub(**overrides: Any) -> Hub:
    fields: dict[str, Any] = {
        "id": "dallas",
        "name": "Dallas",
        "state": "TX",
        "location": GeoLocation(latitude=32.7767, longitude=-96.797),
        "region": Region.SOUTH,
    }
    fields.update(overrides)
    return Hub(**fields)


def test_creates_valid_hub() -> None:
    hub = make_hub()

    assert hub.id == "dallas"
    assert hub.region is Region.SOUTH
    assert hub.location.latitude == 32.7767


def test_accepts_hyphenated_slug_id() -> None:
    assert make_hub(id="salt-lake-city").id == "salt-lake-city"


@pytest.mark.parametrize("bad_id", ["", "Dallas", "dallas tx", "-dallas", "dallas_1"])
def test_rejects_invalid_id(bad_id: str) -> None:
    with pytest.raises(DomainValidationError, match="id"):
        make_hub(id=bad_id)


def test_rejects_blank_name() -> None:
    with pytest.raises(DomainValidationError, match="name"):
        make_hub(name="   ")


@pytest.mark.parametrize("bad_state", ["tx", "TEX", "T", ""])
def test_rejects_invalid_state(bad_state: str) -> None:
    with pytest.raises(DomainValidationError, match="state"):
        make_hub(state=bad_state)


def test_rejects_wrong_location_type() -> None:
    with pytest.raises(DomainValidationError, match="location"):
        make_hub(location=(32.7, -96.8))


def test_rejects_wrong_region_type() -> None:
    with pytest.raises(DomainValidationError, match="region"):
        make_hub(region="south")


def test_equality_is_based_on_identity() -> None:
    original = make_hub()
    renamed = make_hub(name="Dallas–Fort Worth")
    other = make_hub(id="houston", name="Houston")

    assert original == renamed
    assert hash(original) == hash(renamed)
    assert original != other


def test_is_immutable() -> None:
    hub = make_hub()

    with pytest.raises(AttributeError):
        hub.name = "Other"  # type: ignore[misc]
