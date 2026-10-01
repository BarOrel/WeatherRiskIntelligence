from enum import StrEnum

from weather_risk.domain.errors import DomainValidationError


class Region(StrEnum):
    """US Census Bureau regions."""

    NORTHEAST = "northeast"
    MIDWEST = "midwest"
    SOUTH = "south"
    WEST = "west"

    @classmethod
    def parse(cls, value: str) -> "Region":
        try:
            return cls(value.strip().lower())
        except ValueError as exc:
            allowed = ", ".join(r.value for r in cls)
            raise DomainValidationError(
                f"Unknown region '{value}'. Allowed: {allowed}"
            ) from exc
