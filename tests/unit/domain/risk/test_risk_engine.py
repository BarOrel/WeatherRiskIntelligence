from typing import ClassVar

import pytest
from support.risk import DENVER_HUB, days_range, make_metrics

from weather_risk.domain.errors import DomainValidationError
from weather_risk.domain.models import HazardType
from weather_risk.domain.risk import (
    HazardRiskAssessment,
    RiskAssessmentContext,
    RiskScoringEngine,
    RiskStrategy,
)

W, F, HU, HE = HazardType.WINTER, HazardType.FLOOD, HazardType.HURRICANE, HazardType.HEAT


class FixedStrategy(RiskStrategy):
    """Returns a fixed score; lets engine tests focus on weighting."""

    factor_names: ClassVar[tuple[str, ...]] = ("fixed",)

    def __init__(
        self,
        hazard: HazardType,
        score: float,
        requires_weather: bool = True,
        needs: frozenset[HazardType] = frozenset(),
    ) -> None:
        super().__init__({"fixed": 1.0})
        self._hazard, self._fixed = hazard, score
        self.requires_weather = requires_weather  # type: ignore[misc]
        self.required_hazard_data = needs  # type: ignore[misc]
        self.calls = 0

    @property
    def hazard_type(self) -> HazardType:
        return self._hazard

    def assess(self, context: RiskAssessmentContext) -> HazardRiskAssessment:
        self.calls += 1
        return HazardRiskAssessment(self._hazard, self._fixed, ())


SCORES = {W: 40.0, F: 80.0, HU: 20.0, HE: 60.0}
WEIGHTS = {W: 0.25, F: 0.25, HU: 0.30, HE: 0.20}


def make_engine(weights: dict[HazardType, float] = WEIGHTS) -> RiskScoringEngine:
    return RiskScoringEngine([FixedStrategy(h, s) for h, s in SCORES.items()], weights)


CONTEXT = RiskAssessmentContext(hub=DENVER_HUB, date_range=days_range(365), weather=make_metrics())


def test_overall_is_weighted_average() -> None:
    result = make_engine().assess(CONTEXT)

    assert result.overall_score == pytest.approx(0.25 * 40 + 0.25 * 80 + 0.30 * 20 + 0.20 * 60)
    assert dict(result.applied_weights) == pytest.approx(WEIGHTS)
    assert result.hub == DENVER_HUB
    assert result.contribution_of(F) == pytest.approx(20.0)


def test_non_summing_weights_are_normalized() -> None:
    result = make_engine({W: 1, F: 3, HU: 0, HE: 0}).assess(CONTEXT)

    assert result.overall_score == pytest.approx(0.25 * 40 + 0.75 * 80)
    assert result.hazards == (W, F)  # zero-weight hazards are not part of the default selection


def test_selected_hazards_renormalize_only_their_weights() -> None:
    result = make_engine().assess(CONTEXT, [F, HU])

    assert result.hazards == (F, HU)
    assert dict(result.applied_weights) == pytest.approx({F: 0.25 / 0.55, HU: 0.30 / 0.55})
    assert result.overall_score == pytest.approx((0.25 * 80 + 0.30 * 20) / 0.55)


def test_single_hazard_selection_equals_its_score() -> None:
    assert make_engine().assess(CONTEXT, [W]).overall_score == pytest.approx(40.0)


def test_unselected_strategies_are_not_run() -> None:
    strategies = [FixedStrategy(h, s) for h, s in SCORES.items()]
    RiskScoringEngine(strategies, WEIGHTS).assess(CONTEXT, [W])

    assert [s.calls for s in strategies] == [1, 0, 0, 0]


def test_selection_order_does_not_matter() -> None:
    engine = make_engine()

    a, b = engine.assess(CONTEXT, [HE, W, F]), engine.assess(CONTEXT, [F, HE, W, W])

    assert a.hazards == b.hazards == (W, F, HE)
    assert a.overall_score == b.overall_score


def test_strategy_registration_order_does_not_matter() -> None:
    reversed_engine = RiskScoringEngine(
        [FixedStrategy(h, s) for h, s in reversed(SCORES.items())], WEIGHTS
    )

    assert reversed_engine.assess(CONTEXT).overall_score == make_engine().assess(CONTEXT).overall_score


@pytest.mark.parametrize(
    "weights",
    [
        {W: -1, F: 1, HU: 1, HE: 1},
        {W: 0, F: 0, HU: 0, HE: 0},
        {W: 1, F: 1, HU: 1},
    ],
    ids=["negative", "all-zero", "missing-hazard"],
)
def test_invalid_weights(weights: dict[HazardType, float]) -> None:
    with pytest.raises(DomainValidationError):
        make_engine(weights)


def test_duplicate_strategy_is_rejected() -> None:
    with pytest.raises(DomainValidationError, match="more than once"):
        RiskScoringEngine([FixedStrategy(W, 1), FixedStrategy(W, 2)], {W: 1})


def test_unknown_or_empty_selection_is_rejected() -> None:
    engine = RiskScoringEngine([FixedStrategy(W, 1)], {W: 1})

    with pytest.raises(DomainValidationError, match="No risk strategy"):
        engine.assess(CONTEXT, [F])
    with pytest.raises(DomainValidationError, match="at least one"):
        engine.assess(CONTEXT, [])


def test_selection_with_only_zero_weights_is_rejected() -> None:
    with pytest.raises(DomainValidationError, match="positive"):
        make_engine({W: 0, F: 1, HU: 1, HE: 1}).assess(CONTEXT, [W])


def test_data_requirements_follow_selected_strategies() -> None:
    engine = RiskScoringEngine(
        [
            FixedStrategy(W, 1),
            FixedStrategy(F, 1, needs=frozenset({F})),
            FixedStrategy(HU, 1, requires_weather=False, needs=frozenset({HU})),
        ],
        {W: 1, F: 1, HU: 1},
    )

    winter = engine.data_requirements([W])
    assert (winter.weather, winter.hazard_data) == (True, frozenset())
    flood = engine.data_requirements([F])
    assert (flood.weather, flood.hazard_data) == (True, frozenset({F}))
    hurricane = engine.data_requirements([HU])
    assert (hurricane.weather, hurricane.hazard_data) == (False, frozenset({HU}))


def test_short_period_warning_and_disclaimer() -> None:
    short = RiskAssessmentContext(hub=DENVER_HUB, date_range=days_range(90))

    result = make_engine().assess(short, [W])

    assert any("shorter than a year" in w for w in result.warnings)
    assert any("not probabilities" in a for a in result.assumptions)
    assert make_engine().assess(CONTEXT, [W]).warnings == ()
