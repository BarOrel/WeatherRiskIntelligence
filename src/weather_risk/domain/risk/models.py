"""Risk assessment results. Every score carries the structured evidence that produced it."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from weather_risk.domain.errors import DomainValidationError
from weather_risk.domain.models import (
    FloodHazardData,
    HazardType,
    Hub,
    HurricaneHazardData,
    WeatherDateRange,
)
from weather_risk.domain.risk.weather_metrics import WeatherMetrics


@dataclass(frozen=True, slots=True)
class RiskAssessmentContext:
    """Inputs for the strategies. Only the data the selected strategies need is present."""

    hub: Hub
    date_range: WeatherDateRange
    weather: WeatherMetrics | None = None
    flood: FloodHazardData | None = None
    hurricane: HurricaneHazardData | None = None

    def __post_init__(self) -> None:
        if self.flood is not None and not isinstance(self.flood, FloodHazardData):
            raise DomainValidationError("flood must be FloodHazardData")
        if self.hurricane is not None and not isinstance(self.hurricane, HurricaneHazardData):
            raise DomainValidationError("hurricane must be HurricaneHazardData")

    def require_weather(self) -> WeatherMetrics:
        if self.weather is None:
            raise DomainValidationError("This strategy requires weather metrics")
        return self.weather

    def require_flood(self) -> FloodHazardData:
        if self.flood is None:
            raise DomainValidationError("This strategy requires flood hazard data")
        return self.flood

    def require_hurricane(self) -> HurricaneHazardData:
        if self.hurricane is None:
            raise DomainValidationError("This strategy requires hurricane hazard data")
        return self.hurricane


@dataclass(frozen=True, slots=True)
class RiskFactor:
    """One input to a hazard score.

    ``normalized_score = normalize_linear(raw_value, scale_low, scale_high)`` (0..100) and
    ``contribution = weight * normalized_score``; contributions sum to the hazard score.
    """

    name: str
    description: str
    raw_value: float
    unit: str
    scale_low: float
    scale_high: float
    normalized_score: float
    weight: float
    contribution: float


@dataclass(frozen=True, slots=True)
class HazardRiskAssessment:
    hazard_type: HazardType
    score: float
    factors: tuple[RiskFactor, ...]
    assumptions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 100.0:
            raise DomainValidationError(f"Hazard score must be 0..100, got {self.score}")


@dataclass(frozen=True)
class OverallRiskAssessment:
    """Relative weather/hazard operational exposure (0..100) of one hub over a period.

    Not a probability of closure or loss, not actuarial, not an official (e.g. FEMA) score.
    """

    hub: Hub
    date_range: WeatherDateRange
    overall_score: float
    hazard_assessments: tuple[HazardRiskAssessment, ...]
    applied_weights: Mapping[HazardType, float]
    assumptions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        if not 0.0 <= self.overall_score <= 100.0:
            raise DomainValidationError(f"Overall score must be 0..100, got {self.overall_score}")

    @property
    def hazards(self) -> tuple[HazardType, ...]:
        return tuple(a.hazard_type for a in self.hazard_assessments)

    def assessment_for(self, hazard_type: HazardType) -> HazardRiskAssessment:
        for assessment in self.hazard_assessments:
            if assessment.hazard_type is hazard_type:
                return assessment
        raise KeyError(hazard_type)

    def contribution_of(self, hazard_type: HazardType) -> float:
        return self.applied_weights[hazard_type] * self.assessment_for(hazard_type).score
