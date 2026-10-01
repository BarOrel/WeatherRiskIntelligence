import datetime as dt

import pytest
from support.fakes import (
    DENVER,
    FakeFloodProvider,
    FakeHurricaneProvider,
    InMemoryHubRepository,
)

from weather_risk.application.errors import (
    HubNotFoundError,
    InvalidDateRangeError,
    UnsupportedHazardError,
)
from weather_risk.application.hazards import (
    FloodHazard,
    HazardDataService,
    HazardRegistry,
    HurricaneHazard,
)
from weather_risk.domain.models import (
    FloodHazardData,
    GeoLocation,
    HazardType,
    Hub,
    HurricaneHazardData,
    Region,
    WeatherDateRange,
)

RANGE = WeatherDateRange(dt.date(2024, 1, 1), dt.date(2024, 1, 3))
TODAY = dt.date(2024, 6, 15)
MIAMI = GeoLocation(25.7617, -80.1918)


class TestHazards:
    async def test_flood_hazard_delegates_to_its_provider(self) -> None:
        provider = FakeFloodProvider()
        hazard = FloodHazard(provider)

        data = await hazard.get_data(DENVER, RANGE)

        assert hazard.hazard_type is HazardType.FLOOD
        assert isinstance(data, FloodHazardData)
        assert provider.calls == [(DENVER, RANGE)]

    async def test_hurricane_hazard_delegates_to_its_provider(self) -> None:
        provider = FakeHurricaneProvider()
        hazard = HurricaneHazard(provider)

        data = await hazard.get_data(MIAMI, RANGE)

        assert hazard.hazard_type is HazardType.HURRICANE
        assert isinstance(data, HurricaneHazardData)
        assert provider.calls == [(MIAMI, RANGE)]


class TestRegistry:
    def test_resolves_each_registered_hazard(self) -> None:
        flood, hurricane = FloodHazard(FakeFloodProvider()), HurricaneHazard(FakeHurricaneProvider())
        registry = HazardRegistry([flood, hurricane])

        assert registry.get(HazardType.FLOOD) is flood
        assert registry.get(HazardType.HURRICANE) is hurricane
        assert registry.supported_types == (HazardType.FLOOD, HazardType.HURRICANE)

    def test_rejects_duplicate_registration(self) -> None:
        with pytest.raises(ValueError, match="more than once"):
            HazardRegistry([FloodHazard(FakeFloodProvider()), FloodHazard(FakeFloodProvider())])

    def test_unregistered_hazard_fails_clearly(self) -> None:
        registry = HazardRegistry([FloodHazard(FakeFloodProvider())])

        with pytest.raises(UnsupportedHazardError, match="hurricane"):
            registry.get(HazardType.HURRICANE)


@pytest.fixture
def flood_provider() -> FakeFloodProvider:
    return FakeFloodProvider()


@pytest.fixture
def hurricane_provider() -> FakeHurricaneProvider:
    return FakeHurricaneProvider()


def make_service(*hazards: FloodHazard | HurricaneHazard) -> HazardDataService:
    hubs = [
        Hub(id="denver", name="Denver", state="CO", location=DENVER, region=Region.WEST),
        Hub(id="miami", name="Miami", state="FL", location=MIAMI, region=Region.SOUTH),
    ]
    return HazardDataService(
        hub_repository=InMemoryHubRepository(hubs),
        registry=HazardRegistry(hazards),
        max_history_days=3660,
        today=lambda: TODAY,
    )


class TestHazardDataService:
    async def test_routes_to_the_right_hazard_with_hub_coordinates(
        self, flood_provider: FakeFloodProvider, hurricane_provider: FakeHurricaneProvider
    ) -> None:
        service = make_service(FloodHazard(flood_provider), HurricaneHazard(hurricane_provider))

        data = await service.get_hub_hazard_data(
            "miami", HazardType.HURRICANE, RANGE.start, RANGE.end
        )

        assert isinstance(data, HurricaneHazardData)
        assert hurricane_provider.calls == [(MIAMI, RANGE)]
        assert flood_provider.calls == []

    async def test_flood_request_uses_flood_provider(
        self, flood_provider: FakeFloodProvider, hurricane_provider: FakeHurricaneProvider
    ) -> None:
        service = make_service(FloodHazard(flood_provider), HurricaneHazard(hurricane_provider))

        data = await service.get_hub_hazard_data("denver", HazardType.FLOOD, RANGE.start, RANGE.end)

        assert isinstance(data, FloodHazardData)
        assert flood_provider.calls == [(DENVER, RANGE)]
        assert hurricane_provider.calls == []

    async def test_missing_hub(self, flood_provider: FakeFloodProvider) -> None:
        service = make_service(FloodHazard(flood_provider))

        with pytest.raises(HubNotFoundError):
            await service.get_hub_hazard_data("atlantis", HazardType.FLOOD, RANGE.start, RANGE.end)
        assert flood_provider.calls == []

    async def test_unsupported_hazard(self, flood_provider: FakeFloodProvider) -> None:
        service = make_service(FloodHazard(flood_provider))

        with pytest.raises(UnsupportedHazardError):
            await service.get_hub_hazard_data(
                "miami", HazardType.HURRICANE, RANGE.start, RANGE.end
            )

    @pytest.mark.parametrize(
        ("start", "end"),
        [
            (dt.date(2024, 1, 5), dt.date(2024, 1, 1)),
            (dt.date(2024, 6, 1), dt.date(2024, 6, 16)),
            (dt.date(2000, 1, 1), dt.date(2024, 1, 1)),
        ],
        ids=["reversed", "future", "too-long"],
    )
    async def test_invalid_date_ranges(
        self, flood_provider: FakeFloodProvider, start: dt.date, end: dt.date
    ) -> None:
        service = make_service(FloodHazard(flood_provider))

        with pytest.raises(InvalidDateRangeError):
            await service.get_hub_hazard_data("denver", HazardType.FLOOD, start, end)
        assert flood_provider.calls == []

    def test_exposes_supported_hazards(self, flood_provider: FakeFloodProvider) -> None:
        assert make_service(FloodHazard(flood_provider)).supported_hazards == (HazardType.FLOOD,)
