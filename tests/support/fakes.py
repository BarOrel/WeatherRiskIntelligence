"""Test doubles for application ports. Importable as ``support.fakes``."""

import datetime as dt
from collections.abc import Iterable

from weather_risk.application.ports import (
    FloodHazardProvider,
    HurricaneHazardProvider,
    WeatherProvider,
)
from weather_risk.domain.models import (
    CycloneClassification,
    CycloneTrackPoint,
    DailyRiverDischarge,
    DailyWeatherObservation,
    FloodHazardData,
    GeoLocation,
    HazardDataSource,
    Hub,
    HurricaneHazardData,
    Region,
    TropicalCycloneEvent,
    WeatherDateRange,
    WeatherHistory,
)
from weather_risk.domain.repositories import HubRepository

DENVER = GeoLocation(latitude=39.7392, longitude=-104.9903)


def make_observation(day: dt.date, **overrides: float | None) -> DailyWeatherObservation:
    values: dict[str, float | None] = {
        "precipitation_mm": 1.2,
        "rain_mm": 1.0,
        "snowfall_cm": 0.0,
        "temperature_max_c": 12.5,
        "temperature_min_c": -1.5,
        "wind_speed_max_kmh": 20.0,
        "wind_gust_max_kmh": 45.0,
    }
    values.update(overrides)
    return DailyWeatherObservation(date=day, **values)


def make_history(
    location: GeoLocation = DENVER,
    date_range: WeatherDateRange | None = None,
    timezone: str = "America/Denver",
) -> WeatherHistory:
    date_range = date_range or WeatherDateRange(dt.date(2024, 1, 1), dt.date(2024, 1, 3))
    return WeatherHistory(
        location=location,
        date_range=date_range,
        timezone=timezone,
        observations=tuple(make_observation(day) for day in date_range.dates()),
    )


class FakeWeatherProvider(WeatherProvider):
    """Records calls; raises queued errors in order, then returns generated history."""

    def __init__(self, errors: Iterable[Exception] = ()) -> None:
        self.calls: list[tuple[GeoLocation, WeatherDateRange]] = []
        self._errors = list(errors)

    async def get_history(
        self, location: GeoLocation, date_range: WeatherDateRange
    ) -> WeatherHistory:
        self.calls.append((location, date_range))
        if self._errors:
            raise self._errors.pop(0)
        return make_history(location, date_range)


class InMemoryHubRepository(HubRepository):
    def __init__(self, hubs: Iterable[Hub]) -> None:
        self._hubs = {hub.id: hub for hub in hubs}

    def list_all(self) -> list[Hub]:
        return sorted(self._hubs.values(), key=lambda hub: hub.id)

    def get_by_id(self, hub_id: str) -> Hub | None:
        return self._hubs.get(hub_id)

    def list_by_region(self, region: Region) -> list[Hub]:
        return [hub for hub in self.list_all() if hub.region is region]


class FakeClock:
    def __init__(self, now: float = 1_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# --- Hazards -------------------------------------------------------------------------------

SOURCE = HazardDataSource(name="Fake source", url="https://example.test")


def make_flood_data(
    location: GeoLocation = DENVER, date_range: WeatherDateRange | None = None
) -> FloodHazardData:
    date_range = date_range or WeatherDateRange(dt.date(2024, 1, 1), dt.date(2024, 1, 3))
    return FloodHazardData(
        location=location,
        date_range=date_range,
        source=SOURCE,
        limitations=("Signal only.",),
        cell_location=location,
        observations=tuple(
            DailyRiverDischarge(date=day, discharge_m3s=10.0 + i)
            for i, day in enumerate(date_range.dates())
        ),
    )


def make_track_point(
    time: dt.datetime, location: GeoLocation, wind_kmh: float | None = 150.0
) -> CycloneTrackPoint:
    return CycloneTrackPoint(
        time=time,
        location=location,
        classification=CycloneClassification.HURRICANE,
        wind_kmh=wind_kmh,
        pressure_hpa=970.0,
    )


def make_hurricane_data(
    location: GeoLocation = DENVER, date_range: WeatherDateRange | None = None
) -> HurricaneHazardData:
    date_range = date_range or WeatherDateRange(dt.date(2024, 1, 1), dt.date(2024, 1, 3))
    time = dt.datetime.combine(date_range.start, dt.time(12), tzinfo=dt.UTC)
    return HurricaneHazardData(
        location=location,
        date_range=date_range,
        source=SOURCE,
        limitations=("Signal only.",),
        search_radius_km=200.0,
        data_coverage_end=date_range.end,
        events=(
            TropicalCycloneEvent(
                storm_id="AL012024",
                name="TEST",
                start_date=date_range.start,
                end_date=date_range.start,
                closest_approach_km=42.0,
                closest_approach_time=time,
                classification_at_closest_approach=CycloneClassification.HURRICANE,
                wind_at_closest_approach_kmh=150.0,
                peak_classification=CycloneClassification.HURRICANE,
                peak_category=1,
                max_wind_kmh=150.0,
                min_pressure_hpa=970.0,
                track=(make_track_point(time, location),),
            ),
        ),
    )


class _RecordingProvider:
    def __init__(self, errors: Iterable[Exception] = ()) -> None:
        self.calls: list[tuple[GeoLocation, WeatherDateRange]] = []
        self._errors = list(errors)

    def _record(self, location: GeoLocation, date_range: WeatherDateRange) -> None:
        self.calls.append((location, date_range))
        if self._errors:
            raise self._errors.pop(0)


class FakeFloodProvider(_RecordingProvider, FloodHazardProvider):
    async def get_data(
        self, location: GeoLocation, date_range: WeatherDateRange
    ) -> FloodHazardData:
        self._record(location, date_range)
        return make_flood_data(location, date_range)


class FakeHurricaneProvider(_RecordingProvider, HurricaneHazardProvider):
    async def get_data(
        self, location: GeoLocation, date_range: WeatherDateRange
    ) -> HurricaneHazardData:
        self._record(location, date_range)
        return make_hurricane_data(location, date_range)
