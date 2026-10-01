"""Deterministic weather statistics, shared by the risk strategies and the metrics endpoint."""

from collections.abc import Iterable
from dataclasses import dataclass

from weather_risk.domain.errors import DomainValidationError
from weather_risk.domain.models import WeatherDateRange, WeatherHistory


@dataclass(frozen=True, slots=True)
class WeatherThresholds:
    """What counts as a notable day. Operational choices, documented in the README."""

    snowfall_day_cm: float = 0.25  # NWS "measurable" snowfall is 0.1 in (0.254 cm)
    very_cold_day_c: float = -15.0  # daily minimum at or below
    hot_day_c: float = 32.0  # daily maximum at or above (~90 °F)
    extreme_heat_day_c: float = 38.0  # daily maximum at or above (~100 °F)
    heavy_precipitation_mm: float = 25.0  # daily total at or above (~1 in)
    high_wind_gust_kmh: float = 72.0  # ~45 mph, typical NWS Wind Advisory gust
    severe_wind_gust_kmh: float = 93.0  # 58 mph, NWS severe-thunderstorm wind criterion

    def __post_init__(self) -> None:
        for name in ("snowfall_day_cm", "heavy_precipitation_mm", "high_wind_gust_kmh"):
            if getattr(self, name) <= 0:
                raise DomainValidationError(f"{name} must be positive")
        if self.extreme_heat_day_c <= self.hot_day_c:
            raise DomainValidationError("extreme_heat_day_c must be above hot_day_c")
        if self.severe_wind_gust_kmh <= self.high_wind_gust_kmh:
            raise DomainValidationError("severe_wind_gust_kmh must be above high_wind_gust_kmh")


@dataclass(frozen=True, slots=True)
class WeatherMetrics:
    """Counts are days meeting a threshold. Percentages use every day in the range as the
    denominator; a day with a missing value counts as not meeting the threshold."""

    date_range: WeatherDateRange
    thresholds: WeatherThresholds
    days: int
    days_with_missing_values: int

    snowfall_days: int
    total_snowfall_cm: float
    max_daily_snowfall_cm: float | None
    very_cold_days: int
    min_temperature_c: float | None

    hot_days: int
    extreme_heat_days: int
    max_temperature_c: float | None

    heavy_precipitation_days: int
    total_precipitation_mm: float
    max_daily_precipitation_mm: float | None

    high_wind_days: int
    severe_wind_days: int
    max_wind_gust_kmh: float | None

    def percentage(self, count: int) -> float:
        return count / self.days * 100.0

    @property
    def snowfall_day_percentage(self) -> float:
        return self.percentage(self.snowfall_days)

    @property
    def very_cold_day_percentage(self) -> float:
        return self.percentage(self.very_cold_days)

    @property
    def hot_day_percentage(self) -> float:
        return self.percentage(self.hot_days)

    @property
    def extreme_heat_day_percentage(self) -> float:
        return self.percentage(self.extreme_heat_days)

    @property
    def heavy_precipitation_day_percentage(self) -> float:
        return self.percentage(self.heavy_precipitation_days)

    @property
    def high_wind_day_percentage(self) -> float:
        return self.percentage(self.high_wind_days)


class WeatherMetricsCalculator:
    def __init__(self, thresholds: WeatherThresholds) -> None:
        self._thresholds = thresholds

    @property
    def thresholds(self) -> WeatherThresholds:
        return self._thresholds

    def calculate(self, history: WeatherHistory) -> WeatherMetrics:
        t = self._thresholds
        obs = history.observations
        snowfall = _present(o.snowfall_cm for o in obs)
        precipitation = _present(o.precipitation_mm for o in obs)
        t_max = _present(o.temperature_max_c for o in obs)
        t_min = _present(o.temperature_min_c for o in obs)
        gusts = _present(o.wind_gust_max_kmh for o in obs)
        incomplete = sum(
            1
            for o in obs
            if None
            in (
                o.snowfall_cm,
                o.precipitation_mm,
                o.temperature_max_c,
                o.temperature_min_c,
                o.wind_gust_max_kmh,
            )
        )

        return WeatherMetrics(
            date_range=history.date_range,
            thresholds=t,
            days=history.date_range.days,
            days_with_missing_values=incomplete + history.date_range.days - len(obs),
            snowfall_days=_count_at_least(snowfall, t.snowfall_day_cm),
            total_snowfall_cm=sum(snowfall),
            max_daily_snowfall_cm=max(snowfall, default=None),
            very_cold_days=sum(1 for v in t_min if v <= t.very_cold_day_c),
            min_temperature_c=min(t_min, default=None),
            hot_days=_count_at_least(t_max, t.hot_day_c),
            extreme_heat_days=_count_at_least(t_max, t.extreme_heat_day_c),
            max_temperature_c=max(t_max, default=None),
            heavy_precipitation_days=_count_at_least(precipitation, t.heavy_precipitation_mm),
            total_precipitation_mm=sum(precipitation),
            max_daily_precipitation_mm=max(precipitation, default=None),
            high_wind_days=_count_at_least(gusts, t.high_wind_gust_kmh),
            severe_wind_days=_count_at_least(gusts, t.severe_wind_gust_kmh),
            max_wind_gust_kmh=max(gusts, default=None),
        )


def _present(values: Iterable[float | None]) -> list[float]:
    return [v for v in values if v is not None]


def _count_at_least(values: list[float], threshold: float) -> int:
    return sum(1 for v in values if v >= threshold)
