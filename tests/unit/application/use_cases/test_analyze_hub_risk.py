import datetime as dt

import pytest
from support.fakes import DENVER
from support.use_cases import END, HE, HU, START, F, Fixture, W, make_fixture

from weather_risk.application.errors import (
    HubNotFoundError,
    InvalidDateRangeError,
    InvalidRiskRequestError,
    UnsupportedHazardError,
)
from weather_risk.application.use_cases import AnalyzeHubRiskRequest
from weather_risk.domain.models import GeoLocation, HazardType
from weather_risk.domain.risk import OverallRiskAssessment, RiskScoringEngine, WinterRiskStrategy
from weather_risk.domain.risk.strategies import winter


@pytest.fixture
def fx() -> Fixture:
    return make_fixture()


async def analyze(
    fx: Fixture,
    hub_id: str,
    hazards: list[HazardType] | None = None,
    start: dt.date = START,
    end: dt.date = END,
) -> OverallRiskAssessment:
    return await fx.analyze.execute(
        AnalyzeHubRiskRequest(hub_id, start, end, None if hazards is None else tuple(hazards))
    )


class TestDataLoading:
    """Only the data the selected strategies need is fetched."""

    async def test_winter_fetches_weather_only(self, fx: Fixture) -> None:
        result = await analyze(fx, "denver", [W])

        assert result.hazards == (W,)
        assert [loc for loc, _ in fx.weather.calls] == [DENVER]
        assert fx.flood.calls == []
        assert fx.hurricane.calls == []

    async def test_flood_fetches_weather_and_flood(self, fx: Fixture) -> None:
        await analyze(fx, "denver", [F])

        assert len(fx.weather.calls) == 1
        assert len(fx.flood.calls) == 1
        assert fx.hurricane.calls == []

    async def test_hurricane_fetches_no_weather(self, fx: Fixture) -> None:
        await analyze(fx, "miami", [HU])

        assert fx.weather.calls == []
        assert fx.flood.calls == []
        assert len(fx.hurricane.calls) == 1

    async def test_hurricane_uses_climatology_window(self, fx: Fixture) -> None:
        await analyze(fx, "miami", [HU])

        [(location, date_range)] = fx.hurricane.calls
        assert location == GeoLocation(25.76, -80.19)
        assert (date_range.start, date_range.end) == (dt.date(1996, 1, 1), END)

    async def test_heat_fetches_no_hazard_data(self, fx: Fixture) -> None:
        await analyze(fx, "denver", [HE])

        assert len(fx.weather.calls) == 1
        assert fx.flood.calls == fx.hurricane.calls == []

    async def test_all_hazards_by_default(self, fx: Fixture) -> None:
        result = await analyze(fx, "denver")

        assert result.hazards == (W, F, HU, HE)
        assert len(fx.weather.calls) == 1  # shared by winter, flood and heat
        assert (len(fx.flood.calls), len(fx.hurricane.calls)) == (1, 1)
        assert sum(result.applied_weights.values()) == pytest.approx(1.0)

    async def test_weather_requested_for_exact_range(self, fx: Fixture) -> None:
        await analyze(fx, "denver", [W])

        [(_, date_range)] = fx.weather.calls
        assert (date_range.start, date_range.end) == (START, END)


class TestValidation:
    async def test_unknown_hub(self, fx: Fixture) -> None:
        with pytest.raises(HubNotFoundError):
            await analyze(fx, "atlantis")

    async def test_invalid_dates(self, fx: Fixture) -> None:
        with pytest.raises(InvalidDateRangeError):
            await analyze(fx, "denver", start=END, end=START)
        with pytest.raises(InvalidDateRangeError):
            await analyze(fx, "denver", end=dt.date(2026, 7, 1))

    async def test_zero_weight_selection(self) -> None:
        fx = make_fixture({W: 0, F: 1, HU: 1, HE: 1})

        with pytest.raises(InvalidRiskRequestError, match="zero configured weight"):
            await analyze(fx, "denver", [W])

    async def test_unsupported_hazard(self) -> None:
        winter_only = RiskScoringEngine([WinterRiskStrategy(winter.DEFAULT_WEIGHTS)], {W: 1})
        fx = make_fixture(engine=winter_only)

        with pytest.raises(UnsupportedHazardError):
            await analyze(fx, "denver", [HE])

    def test_request_normalizes_hazards_to_a_tuple(self) -> None:
        request = AnalyzeHubRiskRequest("denver", START, END, [W, F])  # type: ignore[arg-type]

        assert request.hazards == (W, F)
