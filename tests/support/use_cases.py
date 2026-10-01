"""Use-case handlers wired with fakes (no network). Importable as ``support.use_cases``."""

import datetime as dt
from dataclasses import dataclass

from support.fakes import (
    DENVER,
    FakeFloodProvider,
    FakeHurricaneProvider,
    FakeWeatherProvider,
    InMemoryHubRepository,
)

from weather_risk.agents.core import CapabilityRegistry
from weather_risk.agents.weather_risk import build_capabilities
from weather_risk.application.hazards import (
    FloodHazard,
    HazardDataService,
    HazardRegistry,
    HurricaneHazard,
)
from weather_risk.application.hubs import HubService
from weather_risk.application.risk import HubRiskAssessor
from weather_risk.application.use_cases import (
    AnalyzeHubRiskHandler,
    CompareHubsHandler,
    GetWeatherMetricsHandler,
    RankHubsHandler,
)
from weather_risk.application.weather import WeatherService
from weather_risk.domain.models import GeoLocation, HazardType, Hub, Region
from weather_risk.domain.risk import (
    FloodRiskStrategy,
    HeatRiskStrategy,
    HurricaneRiskStrategy,
    RiskScoringEngine,
    WeatherMetricsCalculator,
    WeatherThresholds,
    WinterRiskStrategy,
)
from weather_risk.domain.risk.strategies import flood, heat, hurricane, winter

TODAY = dt.date(2026, 6, 1)
START, END = dt.date(2025, 1, 1), dt.date(2025, 12, 31)
W, F, HU, HE = HazardType.WINTER, HazardType.FLOOD, HazardType.HURRICANE, HazardType.HEAT

HUBS = [
    Hub("chicago", "Chicago", "IL", GeoLocation(41.88, -87.63), Region.MIDWEST),
    Hub("minneapolis", "Minneapolis", "MN", GeoLocation(44.98, -93.27), Region.MIDWEST),
    Hub("denver", "Denver", "CO", DENVER, Region.WEST),
    Hub("miami", "Miami", "FL", GeoLocation(25.76, -80.19), Region.SOUTH),
    Hub("houston", "Houston", "TX", GeoLocation(29.76, -95.37), Region.SOUTH),
]


@dataclass
class Fixture:
    analyze: AnalyzeHubRiskHandler
    rank: RankHubsHandler
    compare: CompareHubsHandler
    get_weather_metrics: GetWeatherMetricsHandler
    weather: FakeWeatherProvider
    flood: FakeFloodProvider
    hurricane: FakeHurricaneProvider
    hub_service: HubService
    weather_service: WeatherService
    hazard_service: HazardDataService

    def capabilities(self) -> CapabilityRegistry:
        return build_capabilities(
            hub_service=self.hub_service,
            hazard_data_service=self.hazard_service,
            get_weather_metrics=self.get_weather_metrics,
            analyze_hub_risk=self.analyze,
            rank_hubs=self.rank,
            compare_hubs=self.compare,
        )


def make_fixture(
    hazard_weights: dict[HazardType, float] | None = None,
    engine: RiskScoringEngine | None = None,
) -> Fixture:
    weather = FakeWeatherProvider()
    flood_p, hurricane_p = FakeFloodProvider(), FakeHurricaneProvider()
    repo = InMemoryHubRepository(HUBS)
    hub_service = HubService(repo)
    calculator = WeatherMetricsCalculator(WeatherThresholds())
    hazard_service = HazardDataService(
        hub_repository=repo,
        registry=HazardRegistry([FloodHazard(flood_p), HurricaneHazard(hurricane_p)]),
        max_history_days=11000,
        today=lambda: TODAY,
    )
    engine = engine or RiskScoringEngine(
        [
            WinterRiskStrategy(winter.DEFAULT_WEIGHTS),
            FloodRiskStrategy(flood.DEFAULT_WEIGHTS),
            HurricaneRiskStrategy(hurricane.DEFAULT_WEIGHTS),
            HeatRiskStrategy(heat.DEFAULT_WEIGHTS),
        ],
        hazard_weights or {W: 0.25, F: 0.25, HU: 0.30, HE: 0.20},
    )
    assessor = HubRiskAssessor(
        weather_provider=weather,
        hazard_data_service=hazard_service,
        engine=engine,
        metrics_calculator=calculator,
        max_history_days=3660,
        hurricane_climatology_years=30,
        max_concurrent_hubs=2,
        today=lambda: TODAY,
    )
    weather_service = WeatherService(repo, weather, max_history_days=366, today=lambda: TODAY)
    return Fixture(
        analyze=AnalyzeHubRiskHandler(hub_service, assessor),
        rank=RankHubsHandler(hub_service, assessor),
        compare=CompareHubsHandler(hub_service, assessor),
        get_weather_metrics=GetWeatherMetricsHandler(weather_service, calculator),
        weather=weather,
        flood=flood_p,
        hurricane=hurricane_p,
        hub_service=hub_service,
        weather_service=weather_service,
        hazard_service=hazard_service,
    )
