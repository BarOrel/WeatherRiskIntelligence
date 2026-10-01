import math
from collections.abc import Mapping

from weather_risk.domain.errors import DomainValidationError

MIN_SCORE = 0.0
MAX_SCORE = 100.0


def normalize_linear(value: float, low: float, high: float) -> float:
    """Map ``value`` onto 0..100: ``<= low`` is 0, ``>= high`` is 100, linear in between."""
    for name, number in (("value", value), ("low", low), ("high", high)):
        if not math.isfinite(number):
            raise DomainValidationError(f"{name} must be finite, got {number}")
    if high <= low:
        raise DomainValidationError(f"high ({high}) must be greater than low ({low})")
    if value <= low:
        return MIN_SCORE
    if value >= high:
        return MAX_SCORE
    return (value - low) / (high - low) * MAX_SCORE


def normalize_weights[K](weights: Mapping[K, float]) -> dict[K, float]:
    """Scale non-negative weights to sum to 1. At least one weight must be positive."""
    for key, weight in weights.items():
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            raise DomainValidationError(f"Weight for {key} must be a number, got {weight!r}")
        if not math.isfinite(weight) or weight < 0:
            raise DomainValidationError(f"Weight for {key} must be finite and >= 0, got {weight}")
    total = sum(weights.values())
    if total <= 0:
        raise DomainValidationError("At least one weight must be positive")
    return {key: weight / total for key, weight in weights.items()}


def clamp_score(score: float) -> float:
    return min(MAX_SCORE, max(MIN_SCORE, score))
