"""Provider-independent weather models.

Units are fixed and encoded in field names: temperatures in °C, precipitation and rain
in mm, snowfall in cm, wind speed and gusts in km/h. ``None`` means the provider has no
measurement for that day (e.g. very recent days not yet in the archive).
"""

import datetime as dt
from dataclasses import dataclass

from weather_risk.domain.errors import DomainValidationError
from weather_risk.domain.models._validation import require_optional_finite
from weather_risk.domain.models.geo_location import GeoLocation


@dataclass(frozen=True, slots=True)
class WeatherDateRange:
    """Value object: an inclusive range of calendar days."""

    start: dt.date
    end: dt.date

    def __post_init__(self) -> None:
        for name, value in (("start", self.start), ("end", self.end)):
            if not isinstance(value, dt.date) or isinstance(value, dt.datetime):
                raise DomainValidationError(f"{name} must be a date, got {value!r}")
        if self.start > self.end:
            raise DomainValidationError(
                f"start ({self.start}) must not be after end ({self.end})"
            )

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def dates(self) -> list[dt.date]:
        return [self.start + dt.timedelta(days=offset) for offset in range(self.days)]

    def __contains__(self, day: object) -> bool:
        return isinstance(day, dt.date) and self.start <= day <= self.end


@dataclass(frozen=True, slots=True)
class DailyWeatherObservation:
    """Value object: aggregated weather for one local calendar day."""

    date: dt.date
    precipitation_mm: float | None
    rain_mm: float | None
    snowfall_cm: float | None
    temperature_max_c: float | None
    temperature_min_c: float | None
    wind_speed_max_kmh: float | None
    wind_gust_max_kmh: float | None

    def __post_init__(self) -> None:
        if not isinstance(self.date, dt.date) or isinstance(self.date, dt.datetime):
            raise DomainValidationError(f"date must be a date, got {self.date!r}")

        for name in ("temperature_max_c", "temperature_min_c"):
            require_optional_finite(name, getattr(self, name))
        for name in (
            "precipitation_mm",
            "rain_mm",
            "snowfall_cm",
            "wind_speed_max_kmh",
            "wind_gust_max_kmh",
        ):
            value = require_optional_finite(name, getattr(self, name))
            if value is not None and value < 0:
                raise DomainValidationError(f"{name} must not be negative, got {value}")

        if (
            self.temperature_max_c is not None
            and self.temperature_min_c is not None
            and self.temperature_min_c > self.temperature_max_c
        ):
            raise DomainValidationError(
                f"temperature_min_c ({self.temperature_min_c}) must not exceed "
                f"temperature_max_c ({self.temperature_max_c}) on {self.date}"
            )


@dataclass(frozen=True, slots=True)
class WeatherHistory:
    """Value object: daily observations for a location over a date range.

    Dates are local to ``timezone`` (an IANA name such as ``America/Denver``).
    """

    location: GeoLocation
    date_range: WeatherDateRange
    timezone: str
    observations: tuple[DailyWeatherObservation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.location, GeoLocation):
            raise DomainValidationError("location must be a GeoLocation")
        if not isinstance(self.date_range, WeatherDateRange):
            raise DomainValidationError("date_range must be a WeatherDateRange")
        if not isinstance(self.timezone, str) or not self.timezone.strip():
            raise DomainValidationError("timezone must not be blank")

        observations = tuple(self.observations)
        object.__setattr__(self, "observations", observations)

        previous: dt.date | None = None
        for observation in observations:
            if not isinstance(observation, DailyWeatherObservation):
                raise DomainValidationError("observations must be DailyWeatherObservation")
            if observation.date not in self.date_range:
                raise DomainValidationError(
                    f"Observation date {observation.date} is outside {self.date_range}"
                )
            if previous is not None and observation.date <= previous:
                raise DomainValidationError(
                    "Observations must be in strictly ascending date order"
                )
            previous = observation.date

