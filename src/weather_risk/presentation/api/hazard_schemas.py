"""Response schemas for hazard data. Mapping from domain models happens here only."""

import datetime as dt
from collections.abc import Callable
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from weather_risk.domain.models import (
    CycloneClassification,
    CycloneTrackPoint,
    FloodHazardData,
    HazardData,
    HurricaneHazardData,
    TropicalCycloneEvent,
)
from weather_risk.presentation.api.schemas import GeoLocationResponse


class HazardSourceResponse(BaseModel):
    name: str
    url: str


class _HazardResponseBase(BaseModel):
    hub_id: str
    location: GeoLocationResponse
    start_date: dt.date
    end_date: dt.date
    source: HazardSourceResponse
    limitations: list[str]

    @staticmethod
    def common_fields(hub_id: str, data: HazardData) -> dict[str, Any]:
        return {
            "hub_id": hub_id,
            "location": GeoLocationResponse.from_domain(data.location),
            "start_date": data.date_range.start,
            "end_date": data.date_range.end,
            "source": HazardSourceResponse(name=data.source.name, url=data.source.url),
            "limitations": list(data.limitations),
        }


class RiverDischargeResponse(BaseModel):
    date: dt.date
    discharge_m3s: float | None


class FloodHazardResponse(_HazardResponseBase):
    hazard_type: Literal["flood"] = "flood"
    cell_location: GeoLocationResponse
    days: list[RiverDischargeResponse]

    @classmethod
    def from_domain(cls, hub_id: str, data: FloodHazardData) -> "FloodHazardResponse":
        return cls(
            **cls.common_fields(hub_id, data),
            cell_location=GeoLocationResponse.from_domain(data.cell_location),
            days=[
                RiverDischargeResponse(date=o.date, discharge_m3s=o.discharge_m3s)
                for o in data.observations
            ],
        )


class TrackPointResponse(BaseModel):
    time: dt.datetime
    latitude: float
    longitude: float
    classification: CycloneClassification
    wind_kmh: float | None
    pressure_hpa: float | None

    @classmethod
    def from_domain(cls, point: CycloneTrackPoint) -> "TrackPointResponse":
        return cls(
            time=point.time,
            latitude=point.location.latitude,
            longitude=point.location.longitude,
            classification=point.classification,
            wind_kmh=point.wind_kmh,
            pressure_hpa=point.pressure_hpa,
        )


class TropicalCycloneEventResponse(BaseModel):
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
    max_wind_kmh: float | None
    min_pressure_hpa: float | None
    track: list[TrackPointResponse]

    @classmethod
    def from_domain(cls, event: TropicalCycloneEvent) -> "TropicalCycloneEventResponse":
        return cls(
            storm_id=event.storm_id,
            name=event.name,
            start_date=event.start_date,
            end_date=event.end_date,
            closest_approach_km=event.closest_approach_km,
            closest_approach_time=event.closest_approach_time,
            classification_at_closest_approach=event.classification_at_closest_approach,
            wind_at_closest_approach_kmh=event.wind_at_closest_approach_kmh,
            peak_classification=event.peak_classification,
            peak_category=event.peak_category,
            max_wind_kmh=event.max_wind_kmh,
            min_pressure_hpa=event.min_pressure_hpa,
            track=[TrackPointResponse.from_domain(p) for p in event.track],
        )


class HurricaneHazardResponse(_HazardResponseBase):
    hazard_type: Literal["hurricane"] = "hurricane"
    search_radius_km: float
    data_coverage_end: dt.date | None
    events: list[TropicalCycloneEventResponse]

    @classmethod
    def from_domain(cls, hub_id: str, data: HurricaneHazardData) -> "HurricaneHazardResponse":
        return cls(
            **cls.common_fields(hub_id, data),
            search_radius_km=data.search_radius_km,
            data_coverage_end=data.data_coverage_end,
            events=[TropicalCycloneEventResponse.from_domain(e) for e in data.events],
        )


HazardResponse = Annotated[
    FloodHazardResponse | HurricaneHazardResponse, Field(discriminator="hazard_type")
]

_MAPPERS: dict[type[HazardData], Callable[[str, Any], BaseModel]] = {
    FloodHazardData: FloodHazardResponse.from_domain,
    HurricaneHazardData: HurricaneHazardResponse.from_domain,
}


def to_hazard_response(hub_id: str, data: HazardData) -> FloodHazardResponse | HurricaneHazardResponse:
    try:
        mapper = _MAPPERS[type(data)]
    except KeyError:
        raise TypeError(f"No response schema for {type(data).__name__}") from None
    return mapper(hub_id, data)  # type: ignore[return-value]
