import pytest
from support.use_cases import END, HU, START, F, Fixture, make_fixture

from weather_risk.application.errors import HubNotFoundError, InvalidRiskRequestError
from weather_risk.application.use_cases import AnalyzeHubRiskRequest, CompareHubsRequest


@pytest.fixture
def fx() -> Fixture:
    return make_fixture()


async def test_compares_deterministic_assessments(fx: Fixture) -> None:
    comparison = await fx.compare.execute(CompareHubsRequest(("miami", "denver"), START, END, (HU, F)))

    assert [a.hub.id for a in comparison.assessments] == ["miami", "denver"]
    assert [c.hazard_type for c in comparison.hazard_comparisons] == [F, HU]
    assert len(comparison.overall_differences) == 1


async def test_scores_match_the_single_hub_use_case(fx: Fixture) -> None:
    comparison = await fx.compare.execute(CompareHubsRequest(("miami", "denver"), START, END, (HU, F)))

    direct = await fx.analyze.execute(AnalyzeHubRiskRequest("miami", START, END, (HU, F)))
    assert comparison.assessments[0].overall_score == direct.overall_score


@pytest.mark.parametrize("hub_ids", [("denver", "denver"), ("denver",)])
async def test_needs_two_distinct_hubs(fx: Fixture, hub_ids: tuple[str, ...]) -> None:
    with pytest.raises(InvalidRiskRequestError, match="two distinct"):
        await fx.compare.execute(CompareHubsRequest(hub_ids, START, END))


async def test_unknown_hub(fx: Fixture) -> None:
    with pytest.raises(HubNotFoundError):
        await fx.compare.execute(CompareHubsRequest(("miami", "atlantis"), START, END))
