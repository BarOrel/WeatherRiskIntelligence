from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import ClassVar

from weather_risk.domain.errors import DomainValidationError
from weather_risk.domain.models import HazardType
from weather_risk.domain.risk.models import (
    HazardRiskAssessment,
    RiskAssessmentContext,
    RiskFactor,
)
from weather_risk.domain.risk.normalization import clamp_score, normalize_linear, normalize_weights


@dataclass(frozen=True, slots=True)
class FactorMeasurement:
    """A raw factor value and the scale used to normalize it. ``None`` = no data."""

    name: str
    description: str
    raw_value: float | None
    unit: str
    scale_low: float
    scale_high: float


class RiskStrategy(ABC):
    """Scores ONE hazard's normalized exposure (0..100) for a hub.

    It knows its own factor weights, never the hazard's weight in the overall score.
    """

    factor_names: ClassVar[tuple[str, ...]]
    requires_weather: ClassVar[bool] = True
    required_hazard_data: ClassVar[frozenset[HazardType]] = frozenset()

    def __init__(self, factor_weights: Mapping[str, float]) -> None:
        if set(factor_weights) != set(self.factor_names):
            raise DomainValidationError(
                f"{type(self).__name__} factor weights must be exactly {sorted(self.factor_names)}, "
                f"got {sorted(factor_weights)}"
            )
        normalize_weights(factor_weights)  # validates: >= 0, at least one positive
        self._factor_weights = dict(factor_weights)

    @property
    @abstractmethod
    def hazard_type(self) -> HazardType: ...

    @abstractmethod
    def assess(self, context: RiskAssessmentContext) -> HazardRiskAssessment: ...

    def _score(
        self,
        measurements: Iterable[FactorMeasurement],
        assumptions: Iterable[str] = (),
        warnings: Iterable[str] = (),
    ) -> HazardRiskAssessment:
        """Weighted sum of normalized factors. Factors without data are excluded and the
        remaining weights re-normalized, with a warning."""
        measurements = list(measurements)
        warnings = list(warnings)
        available = [m for m in measurements if m.raw_value is not None]
        for missing in (m for m in measurements if m.raw_value is None):
            warnings.append(
                f"No data for factor '{missing.name}'; it was excluded and the remaining "
                "factor weights were re-normalized."
            )

        try:
            weights = normalize_weights({m.name: self._factor_weights[m.name] for m in available})
        except DomainValidationError:
            warnings.append("No factor with data and positive weight; score defaults to 0.")
            return HazardRiskAssessment(self.hazard_type, 0.0, (), tuple(assumptions), tuple(warnings))

        factors = []
        for m in available:
            assert m.raw_value is not None
            normalized = normalize_linear(m.raw_value, m.scale_low, m.scale_high)
            factors.append(
                RiskFactor(
                    name=m.name,
                    description=m.description,
                    raw_value=m.raw_value,
                    unit=m.unit,
                    scale_low=m.scale_low,
                    scale_high=m.scale_high,
                    normalized_score=normalized,
                    weight=weights[m.name],
                    contribution=weights[m.name] * normalized,
                )
            )
        return HazardRiskAssessment(
            hazard_type=self.hazard_type,
            score=clamp_score(sum(f.contribution for f in factors)),
            factors=tuple(factors),
            assumptions=tuple(assumptions),
            warnings=tuple(warnings),
        )
