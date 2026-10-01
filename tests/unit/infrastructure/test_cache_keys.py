import datetime as dt
import uuid
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum, StrEnum

import pytest

from weather_risk.infrastructure.cache import canonicalize, digest, join_key_parts


class Color(Enum):
    RED = 1


class Kind(StrEnum):
    A = "a"


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@pytest.mark.parametrize(
    "value",
    [
        None,
        "text",
        42,
        1.5,
        True,
        dt.date(2024, 1, 1),
        dt.datetime(2024, 1, 1, 12, tzinfo=dt.UTC),
        dt.time(8, 30),
        Color.RED,
        Kind.A,
        Point(1.0, 2.0),
        (1, "a"),
        [1, [2, 3]],
        {"b": 1, "a": [dt.date(2024, 1, 1)]},
        {3, 1, 2},
        Decimal("1.10"),
        uuid.UUID("12345678-1234-5678-1234-567812345678"),
    ],
)
def test_digest_is_stable_for_supported_types(value: object) -> None:
    assert digest(value) == digest(value)
    assert len(digest(value)) == 64


def test_digest_is_a_fixed_known_value() -> None:
    """Guards against accidental changes to the canonical form (keys must stay stable
    across processes and releases, unlike hash())."""
    assert (
        digest({"a": 1, "b": [dt.date(2024, 1, 1)]})
        == "8a4bc097d4cbf7a4af50be3645bd0146d6a4b87b04443c7a86b13874f0802e47"
    )


def test_dict_and_set_ordering_does_not_matter() -> None:
    assert digest({"a": 1, "b": 2}) == digest({"b": 2, "a": 1})
    assert digest({1, 2, 3}) == digest({3, 2, 1})


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("2024-01-01", dt.date(2024, 1, 1)),
        (1, True),
        (1, 1.0),
        (1, "1"),
        ((1, 2), [1, 2]),
        (Kind.A, "a"),
        (Color.RED, 1),
        (dt.date(2024, 1, 1), dt.datetime(2024, 1, 1)),
        (None, "None"),
    ],
)
def test_different_types_with_similar_values_do_not_collide(left: object, right: object) -> None:
    assert digest(left) != digest(right)


def test_negative_zero_equals_zero() -> None:
    assert digest(-0.0) == digest(0.0)


def test_dataclass_is_canonicalized_by_fields() -> None:
    assert canonicalize(Point(1.0, 2.0))[2] == {"x": 1.0, "y": 2.0}
    assert digest(Point(1.0, 2.0)) != digest(Point(2.0, 1.0))


def test_unsupported_type_raises() -> None:
    with pytest.raises(TypeError, match="key_builder"):
        digest(object())


def test_join_key_parts_is_sorted() -> None:
    assert join_key_parts({"b": 2, "a": "x"}) == "a=x&b=2"


def test_join_key_parts_rejects_reserved_characters() -> None:
    with pytest.raises(ValueError, match="reserved"):
        join_key_parts({"a": "1&b=2"})
