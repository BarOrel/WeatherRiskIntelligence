from collections.abc import Iterable

from weather_risk.application.errors import UnsupportedHazardError
from weather_risk.application.hazards.hazard import Hazard
from weather_risk.domain.models import HazardType


class HazardRegistry:
    """Maps each HazardType to the single Hazard that handles it."""

    def __init__(self, hazards: Iterable[Hazard]) -> None:
        self._hazards: dict[HazardType, Hazard] = {}
        for hazard in hazards:
            if hazard.hazard_type in self._hazards:
                raise ValueError(f"Hazard '{hazard.hazard_type}' is registered more than once")
            self._hazards[hazard.hazard_type] = hazard

    def get(self, hazard_type: HazardType) -> Hazard:
        try:
            return self._hazards[hazard_type]
        except KeyError:
            raise UnsupportedHazardError(hazard_type) from None

    @property
    def supported_types(self) -> tuple[HazardType, ...]:
        return tuple(self._hazards)
