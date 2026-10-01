"""Parser for NHC HURDAT2 best-track files.

Format reference: https://www.nhc.noaa.gov/data/hurdat/hurdat2-format-nov2019.pdf

    AL092022,                IAN,     40,              <- header: id, name, row count
    20220928, 1905, L, HU, 26.7N,  82.2W, 130,  941,... <- date, time, record id, status,
                                                           lat, lon, wind (kt), pressure (mb)
"""

import datetime as dt
from dataclasses import dataclass

from weather_risk.application.errors import InvalidHazardDataError
from weather_risk.domain.errors import DomainValidationError
from weather_risk.domain.models import CycloneClassification, CycloneTrackPoint, GeoLocation

KNOTS_TO_KMH = 1.852
_MISSING_WIND = -99
_MISSING_PRESSURE = -999

STATUS_CODES: dict[str, CycloneClassification] = {
    "TD": CycloneClassification.TROPICAL_DEPRESSION,
    "TS": CycloneClassification.TROPICAL_STORM,
    "HU": CycloneClassification.HURRICANE,
    "SD": CycloneClassification.SUBTROPICAL_DEPRESSION,
    "SS": CycloneClassification.SUBTROPICAL_STORM,
    "EX": CycloneClassification.EXTRATROPICAL,
    "ET": CycloneClassification.EXTRATROPICAL,  # undocumented variant seen in nepac (1974)
    "LO": CycloneClassification.LOW,
    "WV": CycloneClassification.TROPICAL_WAVE,
    "DB": CycloneClassification.DISTURBANCE,
}


@dataclass(frozen=True, slots=True)
class BestTrackStorm:
    storm_id: str
    name: str
    points: tuple[CycloneTrackPoint, ...]
    peak_wind_kt: int | None

    @property
    def start_date(self) -> dt.date:
        return self.points[0].time.date()

    @property
    def end_date(self) -> dt.date:
        return self.points[-1].time.date()


def parse_hurdat2(text: str) -> tuple[BestTrackStorm, ...]:
    lines = [(number, line) for number, line in enumerate(text.splitlines(), 1) if line.strip()]
    storms: list[BestTrackStorm] = []
    index = 0
    while index < len(lines):
        number, header = lines[index]
        storm_id, name, count = _parse_header(header, number)
        rows = lines[index + 1 : index + 1 + count]
        if len(rows) != count:
            raise InvalidHazardDataError(
                f"HURDAT2 line {number}: storm {storm_id} declares {count} rows, found {len(rows)}"
            )
        parsed = [_parse_row(row, row_number) for row_number, row in rows]
        winds = [wind for _, wind in parsed if wind is not None]
        storms.append(
            BestTrackStorm(
                storm_id=storm_id,
                name=name,
                points=tuple(point for point, _ in parsed),
                peak_wind_kt=max(winds) if winds else None,
            )
        )
        index += count + 1
    return tuple(storms)


def saffir_simpson_category(wind_kt: int) -> int | None:
    """Category from 1-minute sustained wind in knots (NHC thresholds)."""
    for threshold, category in ((137, 5), (113, 4), (96, 3), (83, 2), (64, 1)):
        if wind_kt >= threshold:
            return category
    return None


def _parse_header(line: str, number: int) -> tuple[str, str, int]:
    fields = [field.strip() for field in line.split(",")]
    try:
        storm_id, name, count = fields[0], fields[1], int(fields[2])
    except (IndexError, ValueError):
        raise InvalidHazardDataError(f"HURDAT2 line {number}: invalid storm header") from None
    if not storm_id or count < 1:
        raise InvalidHazardDataError(f"HURDAT2 line {number}: invalid storm header")
    return storm_id, name or "UNNAMED", count


def _parse_row(line: str, number: int) -> tuple[CycloneTrackPoint, int | None]:
    fields = [field.strip() for field in line.split(",")]
    try:
        time = dt.datetime.strptime(fields[0] + fields[1], "%Y%m%d%H%M").replace(tzinfo=dt.UTC)
        classification = STATUS_CODES[fields[3]]
        location = GeoLocation(_coordinate(fields[4], "N", "S"), _longitude(fields[5]))
        wind_kt = int(fields[6])
        pressure = int(fields[7])
    except (IndexError, ValueError, KeyError, DomainValidationError) as exc:
        raise InvalidHazardDataError(f"HURDAT2 line {number}: invalid track row") from exc

    wind = None if wind_kt == _MISSING_WIND else wind_kt
    point = CycloneTrackPoint(
        time=time,
        location=location,
        classification=classification,
        wind_kmh=None if wind is None else round(wind * KNOTS_TO_KMH, 1),
        pressure_hpa=None if pressure == _MISSING_PRESSURE else float(pressure),
    )
    return point, wind


def _coordinate(value: str, positive: str, negative: str) -> float:
    hemisphere = value[-1]
    if hemisphere not in (positive, negative):
        raise ValueError(f"bad hemisphere in {value!r}")
    number = float(value[:-1])
    return number if hemisphere == positive else -number


def _longitude(value: str) -> float:
    longitude = _coordinate(value, "E", "W")
    # Pacific tracks may cross the antimeridian (e.g. "181.0W"); normalise to [-180, 180].
    if longitude < -180:
        longitude += 360
    elif longitude > 180:
        longitude -= 360
    return longitude
