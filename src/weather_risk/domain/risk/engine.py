from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from weather_risk.domain.errors import DomainValidationError
from weather_risk.domain.models import HazardType
from weather_risk.domain.risk.models import OverallRiskAssessment, RiskAssessmentContext
from weather_risk.domain.risk.normalization import clamp_score, normalize_weights
from weather_risk.domain.risk.strategies import RiskStrategy

SHORT_PERIOD_DAYS = 365

EXPOSURE_DISCLAIMER = (
    "Scores (0-100) express RELATIVE weather/hazard operational exposure for comparing hubs "
    "over the same period. They are not probabilities of closure or financial loss, not "
    "actuarial estimates and not official (e.g. FEMA) risk scores."
)


@dataclass(frozen=True, slots=True)
class DataRequirements:
    weather: bool
    hazard_data: frozenset[HazardType]


class RiskScoringEngine:
    """Runs the selected strategies and combines them with configured hazard weights."""

    def __init__(
        self, strategies: Iterable[RiskStrategy], hazard_weights: Mapping[HazardType, float]
    ) -> None:
        self._strategies: dict[HazardType, RiskStrategy] = {}
        for strategy in strategies:
            if strategy.hazard_type in self._strategies:
                raise DomainValidationError(
                    f"Strategy for '{strategy.hazard_type}' is registered more than once"
                )
            self._strategies[strategy.hazard_type] = strategy
        if set(hazard_weights) != set(self._strategies):
            raise DomainValidationError(
                f"Hazard weights must cover exactly the registered strategies "
                f"{sorted(self._strategies)}, got {sorted(hazard_weights)}"
            )
        normalize_weights(hazard_weights)  # validates: >= 0, at least one positive
        self._weights = dict(hazard_weights)

    @property
    def supported_hazards(self) -> tuple[HazardType, ...]:
        return tuple(h for h in HazardType if h in self._strategies)

    @property
    def hazard_weights(self) -> Mapping[HazardType, float]:
        return dict(self._weights)

    def select(self, hazards: Iterable[HazardType] | None = None) -> tuple[HazardType, ...]:
        """Canonical, de-duplicated selection. ``None`` = every hazard with a positive weight."""
        if hazards is None:
            return tuple(h for h in self.supported_hazards if self._weights[h] > 0)
        requested = set(hazards)
        unknown = requested - set(self._strategies)
        if unknown:
            raise DomainValidationError(f"No risk strategy for {sorted(unknown)}")
        if not requested:
            raise DomainValidationError("Select at least one hazard")
        return tuple(h for h in self.supported_hazards if h in requested)

    def data_requirements(self, hazards: Iterable[HazardType] | None = None) -> DataRequirements:
        strategies = [self._strategies[h] for h in self.select(hazards)]
        return DataRequirements(
            weather=any(s.requires_weather for s in strategies),
            hazard_data=frozenset().union(*(s.required_hazard_data for s in strategies)),
        )

    def assess(
        self, context: RiskAssessmentContext, hazards: Iterable[HazardType] | None = None
    ) -> OverallRiskAssessment:
        selection = self.select(hazards)
        weights = normalize_weights({h: self._weights[h] for h in selection})
        assessments = tuple(self._strategies[h].assess(context) for h in selection)

        warnings = []
        if context.date_range.days < SHORT_PERIOD_DAYS:
            warnings.append(
                f"The period is {context.date_range.days} days; scores for periods shorter "
                "than a year reflect seasonal conditions, not annual exposure."
            )
        return OverallRiskAssessment(
            hub=context.hub,
            date_range=context.date_range,
            overall_score=clamp_score(sum(weights[a.hazard_type] * a.score for a in assessments)),
            hazard_assessments=assessments,
            applied_weights=weights,
            assumptions=(
                EXPOSURE_DISCLAIMER,
                "Overall score = weighted mean of the selected hazard scores; configured hazard "
                "weights are re-normalized over the selected hazards.",
            ),
            warnings=tuple(warnings),
        )
