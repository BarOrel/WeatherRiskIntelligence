import pytest
from support.use_cases import END, HE, START, W, Fixture, make_fixture

from weather_risk.application.errors import HubNotFoundError, InvalidDateRangeError
from weather_risk.application.use_cases import RankHubsRequest
from weather_risk.domain.models import Region


@pytest.fixture
def fx() -> Fixture:
    return make_fixture()


async def test_region_filter_and_order(fx: Fixture) -> None:
    result = await fx.rank.execute(RankHubsRequest(START, END, (W,), region=Region.MIDWEST))

    ranking = result.rankings
    assert {r.hub.id for r in ranking} == {"chicago", "minneapolis"}
    assert [r.rank for r in ranking] == [1, 2]
    scores = [r.overall_score for r in ranking]
    assert scores == sorted(scores, reverse=True)
    assert all(r.assessment.hazards == (W,) for r in ranking)
    assert fx.flood.calls == fx.hurricane.calls == []


async def test_result_carries_request_context(fx: Fixture) -> None:
    result = await fx.rank.execute(RankHubsRequest(START, END, (W,), region=Region.MIDWEST))

    assert (result.date_range.start, result.date_range.end) == (START, END)
    assert result.region is Region.MIDWEST


async def test_ties_broken_by_hub_id(fx: Fixture) -> None:
    # Fake weather is identical everywhere, so every hub ties.
    result = await fx.rank.execute(RankHubsRequest(START, END, (W,)))

    assert [r.hub.id for r in result.rankings] == [
        "chicago",
        "denver",
        "houston",
        "miami",
        "minneapolis",
    ]


async def test_explicit_hub_list(fx: Fixture) -> None:
    result = await fx.rank.execute(RankHubsRequest(START, END, (HE,), hub_ids=("miami", "denver")))

    assert {r.hub.id for r in result.rankings} == {"miami", "denver"}


async def test_region_filters_an_explicit_hub_list(fx: Fixture) -> None:
    result = await fx.rank.execute(
        RankHubsRequest(START, END, (HE,), region=Region.SOUTH, hub_ids=("miami", "denver"))
    )

    assert [r.hub.id for r in result.rankings] == ["miami"]


async def test_unknown_hub_in_list(fx: Fixture) -> None:
    with pytest.raises(HubNotFoundError):
        await fx.rank.execute(RankHubsRequest(START, END, (W,), hub_ids=("atlantis",)))


async def test_invalid_dates(fx: Fixture) -> None:
    with pytest.raises(InvalidDateRangeError):
        await fx.rank.execute(RankHubsRequest(END, START, (W,)))
