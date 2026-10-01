"""Open-Meteo archive response DTOs and their mapping to the domain model.

Nothing in this module may be imported outside the Open-Meteo adapter.
"""

import datetime as dt
from typing import Any

from pydantic import BaseModel, ValidationError

from weather_risk.application.errors import InvalidWeatherDataError
from weather_risk.domain.errors import DomainValidationError
from weather_risk.domain.models import (
    DailyWeatherObservation,
    GeoLocation,
    WeatherDateRange,
    WeatherHistory,
)

# Requested daily variable -> unit we require (see request unit parameters).
DAILY_VARIABLE_UNITS: dict[str, str] = {
    "precipitation_sum": "mm",
    "rain_sum": "mm",
    "snowfall_sum": "cm",
    "temperature_2m_max": "°C",
    "temperature_2m_min": "°C",
    "wind_speed_10m_max": "km/h",
    "wind_gusts_10m_max": "km/h",
}


class _Daily(BaseModel):
    time: list[dt.date]
    precipitation_sum: list[float | None]
    rain_sum: list[float | None]
    snowfall_sum: list[float | None]
    temperature_2m_max: list[float | None]
    temperature_2m_min: list[float | None]
    wind_speed_10m_max: list[float | None]
    wind_gusts_10m_max: list[float | None]


class _ArchiveResponse(BaseModel):
    timezone: str
    daily_units: dict[str, str] | None = None
    daily: _Daily


def to_weather_history(
    payload: Any, location: GeoLocation, date_range: WeatherDateRange
) -> WeatherHistory:
    try:
        response = _ArchiveResponse.model_validate(payload)
    except ValidationError as exc:
        raise InvalidWeatherDataError(
            f"Open-Meteo response has an unexpected shape ({exc.error_count()} errors)"
        ) from exc

    _check_units(response.daily_units)
    daily = response.daily
    _check_complete(daily, date_range)

    try:
        observations = tuple(
            DailyWeatherObservation(
                date=day,
                precipitation_mm=daily.precipitation_sum[i],
                rain_mm=daily.rain_sum[i],
                snowfall_cm=daily.snowfall_sum[i],
                temperature_max_c=daily.temperature_2m_max[i],
                temperature_min_c=daily.temperature_2m_min[i],
                wind_speed_max_kmh=daily.wind_speed_10m_max[i],
                wind_gust_max_kmh=daily.wind_gusts_10m_max[i],
            )
            for i, day in enumerate(daily.time)
        )
        return WeatherHistory(
            location=location,
            date_range=date_range,
            timezone=response.timezone,
            observations=observations,
        )
    except DomainValidationError as exc:
        raise InvalidWeatherDataError(f"Open-Meteo returned invalid values: {exc}") from exc


def _check_units(daily_units: dict[str, str] | None) -> None:
    if daily_units is None:
        return
    mismatched = {
        variable: daily_units[variable]
        for variable, expected in DAILY_VARIABLE_UNITS.items()
        if variable in daily_units and daily_units[variable] != expected
    }
    if mismatched:
        raise InvalidWeatherDataError(f"Open-Meteo returned unexpected units: {mismatched}")


def _check_complete(daily: _Daily, date_range: WeatherDateRange) -> None:
    for variable in DAILY_VARIABLE_UNITS:
        if len(getattr(daily, variable)) != len(daily.time):
            raise InvalidWeatherDataError(
                f"Open-Meteo '{variable}' has {len(getattr(daily, variable))} values "
                f"for {len(daily.time)} days"
            )
    if daily.time != date_range.dates():
        raise InvalidWeatherDataError(
            f"Open-Meteo returned {len(daily.time)} days that do not match the requested "
            f"range {date_range.start}..{date_range.end}"
        )
