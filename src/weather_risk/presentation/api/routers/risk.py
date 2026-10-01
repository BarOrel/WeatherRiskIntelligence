import datetime as dt

from fastapi import APIRouter

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
from weather_risk.presentation.api.query import parse_hazards, split_csv
from weather_risk.presentation.api.risk_schemas import (
    ComparisonResponse,
    OverallRiskResponse,
    RankingResponse,
)

router = APIRouter(tags=["risk"])


def _hazards(value: str | None) -> tuple[HazardType, ...] | None:
    hazards = parse_hazards(value)
    return None if hazards is None else tuple(hazards)


@router.get("/hubs/{hub_id}/risk", response_model=OverallRiskResponse)
async def analyze_hub_risk(
    hub_id: str,
    start_date: dt.date,
    end_date: dt.date,
    handler: AnalyzeHubRiskDep,
    hazards: str | None = None,
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
    hubs: str | None = None,
    hazards: str | None = None,
) -> RankingResponse:
    hub_ids = split_csv(hubs)
    result = await handler.execute(
        RankHubsRequest(
            start_date=start_date,
            end_date=end_date,
            hazards=_hazards(hazards),
            region=region,
            hub_ids=tuple(hub_ids) if hub_ids else None,
        )
    )
    return RankingResponse.from_result(result)


@router.get("/risk/compare", response_model=ComparisonResponse)
async def compare_hubs(
    hubs: str,
    start_date: dt.date,
    end_date: dt.date,
    handler: CompareHubsDep,
    hazards: str | None = None,
) -> ComparisonResponse:
    comparison = await handler.execute(
        CompareHubsRequest(tuple(split_csv(hubs)), start_date, end_date, _hazards(hazards))
    )
    return ComparisonResponse.from_domain(comparison)
