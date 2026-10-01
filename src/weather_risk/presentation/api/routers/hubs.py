from fastapi import APIRouter, Response

from weather_risk.domain.models import Region
from weather_risk.presentation.api.dependencies import HubServiceDep
from weather_risk.presentation.api.schemas import HubResponse

router = APIRouter(prefix="/hubs", tags=["hubs"])

# hubs.json is the live source of truth; browsers must always ask the API again.
NO_STORE = "no-store"


@router.get("", response_model=list[HubResponse])
def list_hubs(
    service: HubServiceDep, response: Response, region: Region | None = None
) -> list[HubResponse]:
    response.headers["Cache-Control"] = NO_STORE
    return [HubResponse.from_domain(hub) for hub in service.list_hubs(region)]


@router.get("/{hub_id}", response_model=HubResponse)
def get_hub(hub_id: str, service: HubServiceDep, response: Response) -> HubResponse:
    response.headers["Cache-Control"] = NO_STORE
    return HubResponse.from_domain(service.get_hub(hub_id))
