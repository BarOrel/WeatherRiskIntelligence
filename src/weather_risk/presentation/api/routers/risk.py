import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Query

from weather_risk.application.use_cases import (
    AnalyzeHubRiskRequest,
    CompareHubsRequest,
    RankHubsRequest,
)
from weather_risk.domain.models import HazardType, Region
from weather_risk.presentation.api.dependencies import (
    AnalyzeHubRiskDep,
    CompareHubsDep,
    RankHubsDep,
)
from weather_risk.presentation.api.errors import error_responses
from weather_risk.presentation.api.risk_schemas import (
    ComparisonResponse,
    OverallRiskResponse,
    RankingResponse,
)

router = APIRouter(tags=["risk"], responses=error_responses(404, 422, 500, 502, 503, 504))

Hazards = Annotated[
    list[HazardType] | None,
    Query(description="Hazards to score, repeated: `?hazards=winter&hazards=flood`. Omit for all."),
]


def _hazards(hazards: list[HazardType] | None) -> tuple[HazardType, ...] | None:
    return tuple(dict.fromkeys(hazards)) if hazards else None


def _hub_ids(hubs: list[str] | None) -> tuple[str, ...]:
    return tuple(h.strip().lower() for h in hubs or () if h.strip())


@router.get("/hubs/{hub_id}/risk", response_model=OverallRiskResponse)
async def analyze_hub_risk(
    hub_id: str,
    start_date: dt.date,
    end_date: dt.date,
    handler: AnalyzeHubRiskDep,
    hazards: Hazards = None,
) -> OverallRiskResponse:
    assessment = await handler.execute(
        AnalyzeHubRiskRequest(hub_id, start_date, end_date, _hazards(hazards))
    )
    return OverallRiskResponse.from_domain(assessment)


@router.get("/risk/rank", response_model=RankingResponse)
async def rank_hubs(
    start_date: dt.date,
    end_date: dt.date,
    handler: RankHubsDep,
    region: Region | None = None,
    hubs: Annotated[
        list[str] | None,
        Query(description="Hub ids to rank, repeated: `?hubs=miami&hubs=denver`. Omit for all."),
    ] = None,
    hazards: Hazards = None,
) -> RankingResponse:
    hub_ids = _hub_ids(hubs)
    result = await handler.execute(
        RankHubsRequest(
            start_date=start_date,
            end_date=end_date,
            hazards=_hazards(hazards),
            region=region,
            hub_ids=hub_ids or None,
        )
    )
    return RankingResponse.from_result(result)


@router.get("/risk/compare", response_model=ComparisonResponse)
async def compare_hubs(
    hubs: Annotated[
        list[str],
        Query(description="Two or more hub ids, repeated: `?hubs=miami&hubs=houston`."),
    ],
    start_date: dt.date,
    end_date: dt.date,
    handler: CompareHubsDep,
    hazards: Hazards = None,
) -> ComparisonResponse:
    comparison = await handler.execute(
        CompareHubsRequest(_hub_ids(hubs), start_date, end_date, _hazards(hazards))
    )
    return ComparisonResponse.from_domain(comparison)
