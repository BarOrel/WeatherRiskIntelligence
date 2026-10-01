import math
from dataclasses import dataclass

from weather_risk.domain.errors import DomainValidationError

# IUGG mean Earth radius. Haversine on a sphere is within ~0.5% of ellipsoidal distance.
EARTH_MEAN_RADIUS_KM = 6371.0088


@dataclass(frozen=True, slots=True)
class GeoLocation:
    """Value object: a point on Earth in decimal degrees (WGS84)."""

    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        _require_finite("latitude", self.latitude)
        _require_finite("longitude", self.longitude)
        if not -90.0 <= self.latitude <= 90.0:
            raise DomainValidationError(
                f"Latitude must be between -90 and 90, got {self.latitude}"
            )
        if not -180.0 <= self.longitude <= 180.0:
            raise DomainValidationError(
                f"Longitude must be between -180 and 180, got {self.longitude}"
            )

    def distance_km(self, other: "GeoLocation") -> float:
        """Great-circle (Haversine) distance in kilometres."""
        lat1, lon1 = math.radians(self.latitude), math.radians(self.longitude)
        lat2, lon2 = math.radians(other.latitude), math.radians(other.longitude)
        h = (
            math.sin((lat2 - lat1) / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
        )
        return 2 * EARTH_MEAN_RADIUS_KM * math.asin(min(1.0, math.sqrt(h)))


def _require_finite(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DomainValidationError(f"{name} must be a number, got {value!r}")
    if not math.isfinite(value):
        raise DomainValidationError(f"{name} must be finite, got {value}")
