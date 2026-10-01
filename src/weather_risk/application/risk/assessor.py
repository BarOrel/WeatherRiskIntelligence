import asyncio
import datetime as dt
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from weather_risk.application.date_ranges import historical_date_range
from weather_risk.application.errors import InvalidRiskRequestError, UnsupportedHazardError
from weather_risk.application.hazards import HazardDataService
from weather_risk.application.ports import WeatherProvider
from weather_risk.domain.errors import DomainValidationError
from weather_risk.domain.models import (
    FloodHazardData,
    HazardData,
    HazardType,
    Hub,
    HurricaneHazardData,
    WeatherDateRange,
)
from weather_risk.domain.risk import (
    OverallRiskAssessment,
    RiskAssessmentContext,
    RiskScoringEngine,
    WeatherMetrics,
    WeatherMetricsCalculator,
)


@dataclass(frozen=True, slots=True)
class RiskScope:
    """A validated period and hazard selection, shared by every hub in one request."""

    date_range: WeatherDateRange
    hazards: tuple[HazardType, ...]


class HubRiskAssessor:
    """Shared orchestration behind the risk use cases (analyze, rank, compare).

    Validates the request scope, loads exactly the data the selected strategies need, and
    delegates scoring to the domain RiskScoringEngine. Not a use case itself.
    """

    def __init__(
        self,
        weather_provider: WeatherProvider,
        hazard_data_service: HazardDataService,
        engine: RiskScoringEngine,
        metrics_calculator: WeatherMetricsCalculator,
        max_history_days: int,
        hurricane_climatology_years: int,
        max_concurrent_hubs: int,
        today: Callable[[], dt.date] = dt.date.today,
    ) -> None:
        if hurricane_climatology_years < 1 or max_concurrent_hubs < 1:
            raise ValueError("hurricane_climatology_years and max_concurrent_hubs must be >= 1")
        self._weather = weather_provider
        self._hazard_data = hazard_data_service
        self._engine = engine
        self._metrics = metrics_calculator
        self._max_history_days = max_history_days
        self._hurricane_years = hurricane_climatology_years
        self._max_concurrent_hubs = max_concurrent_hubs
        self._today = today

    @property
    def supported_hazards(self) -> tuple[HazardType, ...]:
        return self._engine.supported_hazards

    def scope(
        self,
        start_date: dt.date,
        end_date: dt.date,
        hazards: Iterable[HazardType] | None = None,
    ) -> RiskScope:
        """Validate the period first, then the hazard selection."""
        date_range = historical_date_range(
            start_date, end_date, today=self._today(), max_days=self._max_history_days
        )
        return RiskScope(date_range, self._select(hazards))

    async def assess(self, hub: Hub, scope: RiskScope) -> OverallRiskAssessment:
        needs = self._engine.data_requirements(scope.hazards)
        hazard_types = sorted(needs.hazard_data)
        date_range = scope.date_range

        weather, *hazard_data = await asyncio.gather(
            self._weather_metrics(hub, date_range) if needs.weather else _none(),
            *(
                self._hazard_data.get_hub_hazard_data(
                    hub.id, hazard_type, *self._hazard_period(hazard_type, date_range)
                )
                for hazard_type in hazard_types
            ),
        )
        by_type: dict[HazardType, HazardData] = dict(zip(hazard_types, hazard_data, strict=True))
        flood, hurricane = by_type.get(HazardType.FLOOD), by_type.get(HazardType.HURRICANE)
        context = RiskAssessmentContext(
            hub=hub,
            date_range=date_range,
            weather=weather,
            flood=flood if isinstance(flood, FloodHazardData) else None,
            hurricane=hurricane if isinstance(hurricane, HurricaneHazardData) else None,
        )
        try:
            return self._engine.assess(context, scope.hazards)
        except DomainValidationError as exc:
            raise InvalidRiskRequestError(str(exc)) from exc

    async def assess_many(
        self, hubs: Sequence[Hub], scope: RiskScope
    ) -> list[OverallRiskAssessment]:
        """Assess hubs concurrently, bounded so upstream APIs are not flooded (rate limits)."""
        semaphore = asyncio.Semaphore(self._max_concurrent_hubs)

        async def bounded(hub: Hub) -> OverallRiskAssessment:
            async with semaphore:
                return await self.assess(hub, scope)

        return list(await asyncio.gather(*(bounded(hub) for hub in hubs)))

    def _hazard_period(
        self, hazard_type: HazardType, date_range: WeatherDateRange
    ) -> tuple[dt.date, dt.date]:
        """Tropical cyclones are rare at any one place, so their exposure is measured over a
        climatology window ending at the requested end date (at least the requested range)."""
        if hazard_type is not HazardType.HURRICANE:
            return date_range.start, date_range.end
        end = date_range.end
        climatology_start = _years_before(end, self._hurricane_years) + dt.timedelta(days=1)
        return min(date_range.start, climatology_start), end

    async def _weather_metrics(self, hub: Hub, date_range: WeatherDateRange) -> WeatherMetrics:
        history = await self._weather.get_history(hub.location, date_range)
        return self._metrics.calculate(history)

    def _select(self, hazards: Iterable[HazardType] | None) -> tuple[HazardType, ...]:
        if hazards is not None:
            hazards = list(hazards)
            for hazard in hazards:
                if hazard not in self._engine.supported_hazards:
                    raise UnsupportedHazardError(hazard)
        try:
            selection = self._engine.select(hazards)
        except DomainValidationError as exc:
            raise InvalidRiskRequestError(str(exc)) from exc
        if sum(self._engine.hazard_weights[h] for h in selection) <= 0:
            raise InvalidRiskRequestError(
                f"All selected hazards {list(map(str, selection))} have zero configured weight"
            )
        return selection


async def _none() -> None:
    return None


def _years_before(day: dt.date, years: int) -> dt.date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 February in a non-leap target year
        return day.replace(year=day.year - years, day=28)
