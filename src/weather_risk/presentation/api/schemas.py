import datetime as dt

from pydantic import BaseModel

from weather_risk.domain.models import (
    DailyWeatherObservation,
    GeoLocation,
    Hub,
    Region,
    WeatherHistory,
)


class GeoLocationResponse(BaseModel):
    latitude: float
    longitude: float

    @classmethod
    def from_domain(cls, location: GeoLocation) -> "GeoLocationResponse":
        return cls(latitude=location.latitude, longitude=location.longitude)


class HubResponse(BaseModel):
    id: str
    name: str
    state: str
    region: Region
    location: GeoLocationResponse

    @classmethod
    def from_domain(cls, hub: Hub) -> "HubResponse":
        return cls(
            id=hub.id,
            name=hub.name,
            state=hub.state,
            region=hub.region,
            location=GeoLocationResponse.from_domain(hub.location),
        )


class DailyWeatherResponse(BaseModel):
    date: dt.date
    precipitation_mm: float | None
    rain_mm: float | None
    snowfall_cm: float | None
    temperature_max_c: float | None
    temperature_min_c: float | None
    wind_speed_max_kmh: float | None
    wind_gust_max_kmh: float | None

    @classmethod
    def from_domain(cls, observation: DailyWeatherObservation) -> "DailyWeatherResponse":
        return cls(
            date=observation.date,
            precipitation_mm=observation.precipitation_mm,
            rain_mm=observation.rain_mm,
            snowfall_cm=observation.snowfall_cm,
            temperature_max_c=observation.temperature_max_c,
            temperature_min_c=observation.temperature_min_c,
            wind_speed_max_kmh=observation.wind_speed_max_kmh,
            wind_gust_max_kmh=observation.wind_gust_max_kmh,
        )


class WeatherHistoryResponse(BaseModel):
    hub_id: str
    location: GeoLocationResponse
    timezone: str
    start_date: dt.date
    end_date: dt.date
    days: list[DailyWeatherResponse]

    @classmethod
    def from_domain(cls, hub_id: str, history: WeatherHistory) -> "WeatherHistoryResponse":
        return cls(
            hub_id=hub_id,
            location=GeoLocationResponse.from_domain(history.location),
            timezone=history.timezone,
            start_date=history.date_range.start,
            end_date=history.date_range.end,
            days=[DailyWeatherResponse.from_domain(o) for o in history.observations],
        )
