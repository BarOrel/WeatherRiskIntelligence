import pytest
from support.risk import overall

from weather_risk.domain.errors import DomainValidationError
from weather_risk.domain.models import HazardType
from weather_risk.domain.risk import compare_assessments, rank_assessments

W, F, HU = HazardType.WINTER, HazardType.FLOOD, HazardType.HURRICANE


class TestRanking:
    def test_orders_by_overall_score_descending(self) -> None:
        ranking = rank_assessments(
            [overall("a", {W: 10}), overall("b", {W: 90}), overall("c", {W: 50})]
        )

        assert [(r.rank, r.hub.id, r.overall_score) for r in ranking] == [
            (1, "b", 90),
            (2, "c", 50),
            (3, "a", 10),
        ]

    def test_ties_are_broken_by_hub_id(self) -> None:
        ranking = rank_assessments(
            [overall("zeta", {W: 50}), overall("alpha", {W: 50}), overall("mid", {W: 50})]
        )

        assert [r.hub.id for r in ranking] == ["alpha", "mid", "zeta"]
        assert [r.rank for r in ranking] == [1, 2, 3]

    def test_is_independent_of_input_order(self) -> None:
        items = [overall("a", {W: 30}), overall("b", {W: 30}), overall("c", {W: 70})]

        assert [r.hub.id for r in rank_assessments(items)] == [
            r.hub.id for r in rank_assessments(list(reversed(items)))
        ]

    def test_exposes_component_scores(self) -> None:
        [ranked] = rank_assessments([overall("a", {W: 20, F: 60})])

        assert ranked.hazard_scores == {W: 20, F: 60}
        assert ranked.overall_score == pytest.approx(40)

    def test_empty(self) -> None:
        assert rank_assessments([]) == ()


class TestComparison:
    def test_preserves_assessments_and_computes_differences(self) -> None:
        miami = overall("miami", {HU: 70, F: 30})
        houston = overall("houston", {HU: 50, F: 60})

        comparison = compare_assessments([miami, houston])

        assert comparison.assessments == (miami, houston)
        assert comparison.highest_overall_hub_id == "houston"  # 55 vs 50
        [diff] = comparison.overall_differences
        assert (diff.hub_id, diff.other_hub_id) == ("miami", "houston")
        assert diff.difference == pytest.approx(50 - 55)

        hurricane, flood = comparison.hazard_comparisons
        assert hurricane.hazard_type is HU
        assert hurricane.scores == (("miami", 70), ("houston", 50))
        assert (hurricane.highest_hub_id, hurricane.lowest_hub_id) == ("miami", "houston")
        assert hurricane.spread == pytest.approx(20)
        assert hurricane.differences[0].difference == pytest.approx(20)
        assert flood.highest_hub_id == "houston"
        assert flood.differences[0].difference == pytest.approx(-30)

    def test_three_hubs_produce_all_pairs_in_input_order(self) -> None:
        comparison = compare_assessments(
            [overall("a", {W: 10}), overall("b", {W: 20}), overall("c", {W: 40})]
        )

        assert [(d.hub_id, d.other_hub_id, d.difference) for d in comparison.overall_differences] == [
            ("a", "b", -10),
            ("a", "c", -30),
            ("b", "c", -20),
        ]

    def test_does_not_rescore(self) -> None:
        a = overall("a", {W: 10})
        b = overall("b", {W: 20})

        comparison = compare_assessments([a, b])

        assert comparison.assessments[0] is a
        assert comparison.assessments[1] is b

    @pytest.mark.parametrize(
        "assessments",
        [
            [overall("a", {W: 1})],
            [overall("a", {W: 1}), overall("a", {W: 2})],
            [overall("a", {W: 1}), overall("b", {F: 1})],
        ],
        ids=["single", "duplicate", "different-hazards"],
    )
    def test_invalid_inputs(self, assessments: list) -> None:
        with pytest.raises(DomainValidationError):
            compare_assessments(assessments)
