"""Ranking and comparison over already-computed assessments. No scoring happens here."""

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations

from weather_risk.domain.errors import DomainValidationError
from weather_risk.domain.models import HazardType, Hub
from weather_risk.domain.risk.models import OverallRiskAssessment


@dataclass(frozen=True, slots=True)
class RankedHubRisk:
    rank: int
    assessment: OverallRiskAssessment

    @property
    def hub(self) -> Hub:
        return self.assessment.hub

    @property
    def overall_score(self) -> float:
        return self.assessment.overall_score

    @property
    def hazard_scores(self) -> dict[HazardType, float]:
        return {a.hazard_type: a.score for a in self.assessment.hazard_assessments}


def _ranking_key(assessment: OverallRiskAssessment) -> tuple[float, str]:
    return (-assessment.overall_score, assessment.hub.id)


def rank_assessments(assessments: Sequence[OverallRiskAssessment]) -> tuple[RankedHubRisk, ...]:
    """Overall score descending; ties broken by hub id ascending. Ranks are 1..n."""
    ordered = sorted(assessments, key=_ranking_key)
    return tuple(RankedHubRisk(rank=i, assessment=a) for i, a in enumerate(ordered, start=1))


@dataclass(frozen=True, slots=True)
class ScoreDifference:
    """``difference = score(hub_id) - score(other_hub_id)``."""

    hub_id: str
    other_hub_id: str
    difference: float


@dataclass(frozen=True, slots=True)
class HazardComparison:
    hazard_type: HazardType
    scores: tuple[tuple[str, float], ...]
    """(hub_id, score) in comparison order."""
    highest_hub_id: str
    lowest_hub_id: str
    spread: float
    differences: tuple[ScoreDifference, ...]


@dataclass(frozen=True, slots=True)
class HubComparison:
    assessments: tuple[OverallRiskAssessment, ...]
    highest_overall_hub_id: str
    overall_differences: tuple[ScoreDifference, ...]
    hazard_comparisons: tuple[HazardComparison, ...]


def compare_assessments(assessments: Sequence[OverallRiskAssessment]) -> HubComparison:
    """Pairwise differences (in input order) for the overall score and each hazard."""
    if len(assessments) < 2:
        raise DomainValidationError("A comparison needs at least two hubs")
    if len({a.hub.id for a in assessments}) != len(assessments):
        raise DomainValidationError("A comparison needs distinct hubs")
    hazards = assessments[0].hazards
    if any(a.hazards != hazards or a.date_range != assessments[0].date_range for a in assessments):
        raise DomainValidationError("Compared assessments must share hazards and date range")

    overall = [(a.hub.id, a.overall_score) for a in assessments]
    return HubComparison(
        assessments=tuple(assessments),
        highest_overall_hub_id=sorted(assessments, key=_ranking_key)[0].hub.id,
        overall_differences=_pairwise(overall),
        hazard_comparisons=tuple(
            _compare_hazard(h, [(a.hub.id, a.assessment_for(h).score) for a in assessments])
            for h in hazards
        ),
    )


def _compare_hazard(hazard_type: HazardType, scores: list[tuple[str, float]]) -> HazardComparison:
    ordered = sorted(scores, key=lambda item: (-item[1], item[0]))
    return HazardComparison(
        hazard_type=hazard_type,
        scores=tuple(scores),
        highest_hub_id=ordered[0][0],
        lowest_hub_id=ordered[-1][0],
        spread=ordered[0][1] - ordered[-1][1],
        differences=_pairwise(scores),
    )


def _pairwise(scores: list[tuple[str, float]]) -> tuple[ScoreDifference, ...]:
    return tuple(
        ScoreDifference(hub_id=a, other_hub_id=b, difference=score_a - score_b)
        for (a, score_a), (b, score_b) in combinations(scores, 2)
    )
