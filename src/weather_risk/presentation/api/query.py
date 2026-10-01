"""Parsing of comma-separated query parameters (e.g. ``hazards=winter,flood``)."""

from fastapi import HTTPException

from weather_risk.domain.models import HazardType


def split_csv(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def parse_hazards(value: str | None) -> list[HazardType] | None:
    """``None``/empty means "all configured hazards"."""
    names = split_csv(value)
    if not names:
        return None
    try:
        return [HazardType(name) for name in names]
    except ValueError:
        allowed = ", ".join(h.value for h in HazardType)
        raise HTTPException(
            status_code=422, detail=f"Unknown hazard in '{value}'. Allowed: {allowed}"
        ) from None
