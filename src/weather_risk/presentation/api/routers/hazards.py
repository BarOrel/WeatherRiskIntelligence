import datetime as dt

from fastapi import APIRouter

from weather_risk.domain.models import HazardType
from weather_risk.presentation.api.dependencies import HazardDataServiceDep
from weather_risk.presentation.api.errors import error_responses
from weather_risk.presentation.api.hazard_schemas import HazardResponse, to_hazard_response

router = APIRouter(
    prefix="/hubs",
    tags=["hazards"],
    responses=error_responses(404, 422, 500, 501, 502, 503, 504),
)


@router.get("/{hub_id}/hazards/{hazard}", response_model=HazardResponse)
async def get_hub_hazard_data(
    hub_id: str,
    hazard: HazardType,
    start_date: dt.date,
    end_date: dt.date,
    service: HazardDataServiceDep,
) -> HazardResponse:
    data = await service.get_hub_hazard_data(hub_id, hazard, start_date, end_date)
    return to_hazard_response(hub_id, data)
