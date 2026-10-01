import math

import pytest

from weather_risk.domain.errors import DomainValidationError
from weather_risk.domain.risk import normalize_linear, normalize_weights


class TestNormalizeLinear:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [(0.0, 0.0), (10.0, 0.0), (15.0, 50.0), (20.0, 100.0), (17.5, 75.0)],
    )
    def test_bounds_and_interpolation(self, value: float, expected: float) -> None:
        assert normalize_linear(value, 10.0, 20.0) == pytest.approx(expected)

    @pytest.mark.parametrize(("value", "expected"), [(-1e9, 0.0), (1e9, 100.0)])
    def test_clamps(self, value: float, expected: float) -> None:
        assert normalize_linear(value, 0.0, 1.0) == expected

    def test_negative_scale(self) -> None:
        assert normalize_linear(-5.0, -10.0, 0.0) == pytest.approx(50.0)

    @pytest.mark.parametrize(("low", "high"), [(1.0, 1.0), (2.0, 1.0)])
    def test_invalid_range(self, low: float, high: float) -> None:
        with pytest.raises(DomainValidationError, match="greater than low"):
            normalize_linear(1.0, low, high)

    @pytest.mark.parametrize("bad", [math.nan, math.inf])
    def test_rejects_non_finite(self, bad: float) -> None:
        with pytest.raises(DomainValidationError, match="finite"):
            normalize_linear(bad, 0.0, 1.0)


class TestNormalizeWeights:
    def test_scales_to_one(self) -> None:
        assert normalize_weights({"a": 1, "b": 3}) == {"a": 0.25, "b": 0.75}

    def test_already_normalized_is_unchanged(self) -> None:
        assert normalize_weights({"a": 0.4, "b": 0.6}) == pytest.approx({"a": 0.4, "b": 0.6})

    def test_zero_weight_is_allowed_if_another_is_positive(self) -> None:
        assert normalize_weights({"a": 0, "b": 2}) == {"a": 0.0, "b": 1.0}

    @pytest.mark.parametrize(
        "weights", [{"a": -0.1, "b": 1}, {"a": 0, "b": 0}, {}, {"a": math.nan}, {"a": True}]
    )
    def test_invalid(self, weights: dict) -> None:
        with pytest.raises(DomainValidationError):
            normalize_weights(weights)
