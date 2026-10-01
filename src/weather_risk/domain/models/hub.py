import re
from dataclasses import dataclass

from weather_risk.domain.errors import DomainValidationError
from weather_risk.domain.models.geo_location import GeoLocation
from weather_risk.domain.models.region import Region

_HUB_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_STATE_PATTERN = re.compile(r"^[A-Z]{2}$")


@dataclass(frozen=True, slots=True, eq=False)
class Hub:
    """Entity: an operational hub whose weather risk is assessed.

    Identity is defined by ``id``; two hubs with the same id are the same hub.
    """

    id: str
    name: str
    state: str
    location: GeoLocation
    region: Region

    def __post_init__(self) -> None:
        if not _HUB_ID_PATTERN.fullmatch(self.id):
            raise DomainValidationError(
                f"Hub id must be a lowercase slug (e.g. 'new-york'), got {self.id!r}"
            )
        if not self.name.strip():
            raise DomainValidationError("Hub name must not be blank")
        if not _STATE_PATTERN.fullmatch(self.state):
            raise DomainValidationError(
                f"Hub state must be a two-letter uppercase code, got {self.state!r}"
            )
        if not isinstance(self.location, GeoLocation):
            raise DomainValidationError("Hub location must be a GeoLocation")
        if not isinstance(self.region, Region):
            raise DomainValidationError("Hub region must be a Region")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Hub):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
