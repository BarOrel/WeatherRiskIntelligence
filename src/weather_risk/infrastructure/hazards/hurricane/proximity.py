"""Find best-track storms whose centre passed within a radius of a location."""

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass

from weather_risk.domain.models import (
    CycloneClassification,
    CycloneTrackPoint,
    GeoLocation,
    TropicalCycloneEvent,
    WeatherDateRange,
)
from weather_risk.infrastructure.hazards.hurricane.hurdat2 import (
    BestTrackStorm,
    saffir_simpson_category,
)

# Positions sampled per 6-hour segment (~30 min apart): a fast storm passing between two
# fixes is not missed, and distance error stays within a few km.
SEGMENT_SAMPLES = 12


@dataclass(frozen=True, slots=True)
class _Approach:
    distance_km: float
    time: dt.datetime
    nearest_fix: CycloneTrackPoint


def find_events(
    storms: Iterable[BestTrackStorm],
    location: GeoLocation,
    date_range: WeatherDateRange,
    radius_km: float,
) -> list[TropicalCycloneEvent]:
    events: list[TropicalCycloneEvent] = []
    for storm in storms:
        if storm.end_date < date_range.start or storm.start_date > date_range.end:
            continue
        approach = closest_approach(storm.points, location, date_range)
        if approach is None or approach.distance_km > radius_km:
            continue
        events.append(_to_event(storm, approach))
    return sorted(events, key=lambda event: event.closest_approach_time)


def closest_approach(
    points: tuple[CycloneTrackPoint, ...], location: GeoLocation, date_range: WeatherDateRange
) -> _Approach | None:
    """Closest distance to the interpolated track, restricted to times inside ``date_range``."""
    best: _Approach | None = None

    def consider(position: GeoLocation, time: dt.datetime, fix: CycloneTrackPoint) -> None:
        nonlocal best
        if time.date() not in date_range:
            return
        distance = location.distance_km(position)
        if best is None or distance < best.distance_km:
            best = _Approach(distance, time, fix)

    for point in points:
        consider(point.location, point.time, point)

    for start, end in zip(points, points[1:]):
        if abs(end.location.longitude - start.location.longitude) > 180:
            continue  # antimeridian crossing: linear interpolation would go the wrong way
        for step in range(1, SEGMENT_SAMPLES):
            fraction = step / SEGMENT_SAMPLES
            position = GeoLocation(
                start.location.latitude
                + (end.location.latitude - start.location.latitude) * fraction,
                start.location.longitude
                + (end.location.longitude - start.location.longitude) * fraction,
            )
            time = start.time + (end.time - start.time) * fraction
            consider(position, time, start if fraction <= 0.5 else end)

    return best


def _to_event(storm: BestTrackStorm, approach: _Approach) -> TropicalCycloneEvent:
    winds = [p.wind_kmh for p in storm.points if p.wind_kmh is not None]
    pressures = [p.pressure_hpa for p in storm.points if p.pressure_hpa is not None]
    peak = max(storm.points, key=lambda p: -1 if p.wind_kmh is None else p.wind_kmh)
    category = (
        saffir_simpson_category(storm.peak_wind_kt)
        if storm.peak_wind_kt is not None and peak.classification is CycloneClassification.HURRICANE
        else None
    )
    return TropicalCycloneEvent(
        storm_id=storm.storm_id,
        name=storm.name,
        start_date=storm.start_date,
        end_date=storm.end_date,
        closest_approach_km=round(approach.distance_km, 1),
        closest_approach_time=approach.time,
        classification_at_closest_approach=approach.nearest_fix.classification,
        wind_at_closest_approach_kmh=approach.nearest_fix.wind_kmh,
        peak_classification=peak.classification,
        peak_category=category,
        max_wind_kmh=max(winds) if winds else None,
        min_pressure_hpa=min(pressures) if pressures else None,
        track=storm.points,
    )
