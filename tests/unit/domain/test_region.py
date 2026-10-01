import pytest

from weather_risk.domain.errors import DomainValidationError
from weather_risk.domain.models import Region


@pytest.mark.parametrize("raw", ["south", "SOUTH", " South "])
def test_parse_is_case_and_whitespace_insensitive(raw: str) -> None:
    assert Region.parse(raw) is Region.SOUTH


def test_parse_rejects_unknown_region() -> None:
    with pytest.raises(DomainValidationError, match="Unknown region"):
        Region.parse("atlantis")
