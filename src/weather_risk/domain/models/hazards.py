"""Provider-independent hazard data models.

These describe *exposure signals* gathered from public sources. They carry no risk score:
interpreting them is a later concern. Each dataset records its source and known limitations
so consumers never mistake a signal for a site-level probability.
"""

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from weather_risk.domain.errors import DomainValidationError
from weather_risk.domain.models._validation import (
    require_date,
    require_optional_non_negative,
    require_text,
)
from weather_risk.domain.models.geo_location import GeoLocation
from weather_risk.domain.models.weather import WeatherDateRange


class HazardType(StrEnum):
    """Every hazard the system reasons about.

    FLOOD and HURRICANE have dedicated hazard datasets; WINTER and HEAT are derived from
    weather observations only.
    """

    WINTER = "winter"
    FLOOD = "flood"
    HURRICANE = "hurricane"
    HEAT = "heat"


@dataclass(frozen=True, slots=True)
class HazardDataSource:
    name: str
    url: str

    def __post_init__(self) -> None:
        require_text("source name", self.name)
        require_text("source url", self.url)


@dataclass(frozen=True)
class HazardData:
    """Common shape of all hazard datasets. Subclasses set ``hazard_type``."""

    hazard_type: ClassVar[HazardType]

    location: GeoLocation
    date_range: WeatherDateRange
    source: HazardDataSource
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.location, GeoLocation):
            raise DomainValidationError("location must be a GeoLocation")
        if not isinstance(self.date_range, WeatherDateRange):
            raise DomainValidationError("date_range must be a WeatherDateRange")
        if not isinstance(self.source, HazardDataSource):
            raise DomainValidationError("source must be a HazardDataSource")
        object.__setattr__(self, "limitations", tuple(self.limitations))
        for limitation in self.limitations:
            require_text("limitation", limitation)


# --- Flood ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DailyRiverDischarge:
    """Daily mean river discharge in m³/s. ``None`` means no value for that day."""

    date: dt.date
    discharge_m3s: float | None

    def __post_init__(self) -> None:
        require_date("date", self.date)
        require_optional_non_negative("discharge_m3s", self.discharge_m3s)


@dataclass(frozen=True)
class FloodHazardData(HazardData):
    hazard_type: ClassVar[HazardType] = HazardType.FLOOD

    cell_location: GeoLocation
    """Centre of the modelled river grid cell the discharge belongs to."""
    observations: tuple[DailyRiverDischarge, ...]

    def __post_init__(self) -> None:
        HazardData.__post_init__(self)
        if not isinstance(self.cell_location, GeoLocation):
            raise DomainValidationError("cell_location must be a GeoLocation")
        observations = tuple(self.observations)
        object.__setattr__(self, "observations", observations)
        _require_ascending_in_range(
            [o.date for o in observations], self.date_range, "observations"
        )


# --- Hurricane / tropical cyclone ----------------------------------------------------------


class CycloneClassification(StrEnum):
    TROPICAL_DEPRESSION = "tropical_depression"
    TROPICAL_STORM = "tropical_storm"
    HURRICANE = "hurricane"
    SUBTROPICAL_DEPRESSION = "subtropical_depression"
    SUBTROPICAL_STORM = "subtropical_storm"
    EXTRATROPICAL = "extratropical"
    LOW = "low"
    TROPICAL_WAVE = "tropical_wave"
    DISTURBANCE = "disturbance"


@dataclass(frozen=True, slots=True)
class CycloneTrackPoint:
    """One best-track fix. ``time`` is timezone-aware (UTC)."""

    time: dt.datetime
    location: GeoLocation
    classification: CycloneClassification
    wind_kmh: float | None
    pressure_hpa: float | None

    def __post_init__(self) -> None:
        if not isinstance(self.time, dt.datetime) or self.time.tzinfo is None:
            raise DomainValidationError("Track point time must be a timezone-aware datetime")
        if not isinstance(self.location, GeoLocation):
            raise DomainValidationError("Track point location must be a GeoLocation")
        if not isinstance(self.classification, CycloneClassification):
            raise DomainValidationError("classification must be a CycloneClassification")
        require_optional_non_negative("wind_kmh", self.wind_kmh)
        require_optional_non_negative("pressure_hpa", self.pressure_hpa)


@dataclass(frozen=True, slots=True)
class TropicalCycloneEvent:
    """A storm whose centre passed within the search radius during the requested range."""

    storm_id: str
    name: str
    start_date: dt.date
    end_date: dt.date
    closest_approach_km: float
    closest_approach_time: dt.datetime
    classification_at_closest_approach: CycloneClassification
    wind_at_closest_approach_kmh: float | None
    peak_classification: CycloneClassification
    peak_category: int | None
    """Saffir-Simpson category (1-5) at peak intensity; None if never a hurricane."""
    max_wind_kmh: float | None
    min_pressure_hpa: float | None
    track: tuple[CycloneTrackPoint, ...]

    def __post_init__(self) -> None:
        require_text("storm_id", self.storm_id)
        require_text("name", self.name)
        require_date("start_date", self.start_date)
        require_date("end_date", self.end_date)
        if self.start_date > self.end_date:
            raise DomainValidationError("Storm start_date must not be after end_date")
        if require_optional_non_negative("closest_approach_km", self.closest_approach_km) is None:
            raise DomainValidationError("closest_approach_km is required")
        if self.peak_category is not None and self.peak_category not in range(1, 6):
            raise DomainValidationError(f"peak_category must be 1-5, got {self.peak_category}")
        require_optional_non_negative("wind_at_closest_approach_kmh", self.wind_at_closest_approach_kmh)
        require_optional_non_negative("max_wind_kmh", self.max_wind_kmh)
        require_optional_non_negative("min_pressure_hpa", self.min_pressure_hpa)
        object.__setattr__(self, "track", tuple(self.track))
        if not self.track:
            raise DomainValidationError("A tropical cyclone event needs at least one track point")


@dataclass(frozen=True)
class HurricaneHazardData(HazardData):
    hazard_type: ClassVar[HazardType] = HazardType.HURRICANE

    search_radius_km: float
    data_coverage_end: dt.date | None
    """Last date covered by the source. Storms after it are not yet in the dataset."""
    events: tuple[TropicalCycloneEvent, ...]

    def __post_init__(self) -> None:
        HazardData.__post_init__(self)
        radius = require_optional_non_negative("search_radius_km", self.search_radius_km)
        if not radius:
            raise DomainValidationError("search_radius_km must be positive")
        if self.data_coverage_end is not None:
            require_date("data_coverage_end", self.data_coverage_end)
        object.__setattr__(self, "events", tuple(self.events))


def _require_ascending_in_range(
    dates: list[dt.date], date_range: WeatherDateRange, name: str
) -> None:
    previous: dt.date | None = None
    for day in dates:
        if day not in date_range:
            raise DomainValidationError(f"{name} date {day} is outside {date_range}")
        if previous is not None and day <= previous:
            raise DomainValidationError(f"{name} must be in strictly ascending date order")
        previous = day
