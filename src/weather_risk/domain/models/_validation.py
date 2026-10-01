import datetime as dt
import math

from weather_risk.domain.errors import DomainValidationError


def require_date(name: str, value: object) -> None:
    if not isinstance(value, dt.date) or isinstance(value, dt.datetime):
        raise DomainValidationError(f"{name} must be a date, got {value!r}")


def require_optional_finite(name: str, value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DomainValidationError(f"{name} must be a number or None, got {value!r}")
    if not math.isfinite(value):
        raise DomainValidationError(f"{name} must be finite, got {value}")
    return float(value)


def require_optional_non_negative(name: str, value: object) -> float | None:
    number = require_optional_finite(name, value)
    if number is not None and number < 0:
        raise DomainValidationError(f"{name} must not be negative, got {number}")
    return number


def require_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise DomainValidationError(f"{name} must not be blank")
