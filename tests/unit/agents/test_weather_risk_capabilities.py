"""Each capability is a thin adapter: it delegates to the existing application service and
serializes the deterministic result without changing it."""

import datetime as dt
import json

import pytest
from support.use_cases import Fixture, make_fixture

from weather_risk.agents.core import CapabilityRegistry, InvalidCapabilityArgumentsError
from weather_risk.application.use_cases import AnalyzeHubRiskRequest, GetWeatherMetricsRequest
from weather_risk.application.errors import HubNotFoundError, UnsupportedHazardError
from weather_risk.domain.models import HazardType, Region

START, END = "2025-01-01", "2025-12-31"


@pytest.fixture
def fx() -> Fixture:
    return make_fixture()


@pytest.fixture
def registry(fx: Fixture) -> CapabilityRegistry:
    return fx.capabilities()


async def call(registry: CapabilityRegistry, name: str, **arguments: object) -> dict:
    result = await registry.get(name).execute(registry.parse_arguments(name, arguments))
    json.dumps(result.data, default=str)  # must be JSON-serializable for the LLM
    return dict(result.data)


def test_registers_exactly_the_assignment_capabilities(registry: CapabilityRegistry) -> None:
    assert registry.names == (
        "list_hubs",
        "get_weather_metrics",
        "get_hazard_data",
        "analyze_hub_risk",
        "rank_hubs",
        "compare_hubs",
    )


async def test_list_hubs(registry: CapabilityRegistry, fx: Fixture) -> None:
    data = await call(registry, "list_hubs", region="midwest")

    assert [h["hub_id"] for h in data["hubs"]] == [
        h.id for h in fx.hub_service.list_hubs(Region.MIDWEST)
    ]


async def test_get_weather_metrics_delegates_to_its_use_case(
    registry: CapabilityRegistry, fx: Fixture
) -> None:
    data = await call(registry, "get_weather_metrics", hub_id="denver", start_date=START, end_date=END)

    expected = await fx.get_weather_metrics.execute(
        GetWeatherMetricsRequest("denver", dt.date(2025, 1, 1), dt.date(2025, 12, 31))
    )
    assert data["snowfall_days"] == expected.snowfall_days
    assert data["snowfall_day_percentage"] == round(expected.snowfall_day_percentage, 2)
    assert data["thresholds"]["snowfall_day_cm"] == 0.25
    assert len(fx.weather.calls) == 2  # one per call above; the capability added nothing else


async def test_get_hazard_data_flood_and_hurricane(registry: CapabilityRegistry, fx: Fixture) -> None:
    flood = await call(
        registry, "get_hazard_data", hub_id="miami", hazard="flood", start_date=START, end_date=END
    )
    hurricane = await call(
        registry,
        "get_hazard_data",
        hub_id="miami",
        hazard="hurricane",
        start_date=START,
        end_date=END,
    )

    assert flood["hazard"] == "flood" and "max_discharge_m3s" in flood
    assert hurricane["hazard"] == "hurricane" and hurricane["event_count"] == 1
    assert "track" not in hurricane["events"][0]  # bulky tracks are summarized away
    assert len(fx.flood.calls) == len(fx.hurricane.calls) == 1


async def test_get_hazard_data_rejects_weather_derived_hazards(registry: CapabilityRegistry) -> None:
    with pytest.raises(UnsupportedHazardError):
        await call(
            registry, "get_hazard_data", hub_id="miami", hazard="winter", start_date=START, end_date=END
        )


async def test_analyze_hub_risk_preserves_deterministic_values(
    registry: CapabilityRegistry, fx: Fixture
) -> None:
    data = await call(
        registry,
        "analyze_hub_risk",
        hub_id="denver",
        start_date=START,
        end_date=END,
        hazards=["winter", "heat"],
    )

    direct = await fx.analyze.execute(
        AnalyzeHubRiskRequest(
            "denver",
            dt.date(2025, 1, 1),
            dt.date(2025, 12, 31),
            (HazardType.WINTER, HazardType.HEAT),
        )
    )
    assert data["overall_score"] == round(direct.overall_score, 2)
    assert [h["hazard"] for h in data["hazards"]] == ["winter", "heat"]
    winter = data["hazards"][0]
    assert winter["score"] == round(direct.hazard_assessments[0].score, 2)
    assert {f["name"] for f in winter["factors"]} == {
        "snowfall_frequency",
        "snowfall_severity",
        "cold_exposure",
    }
    assert set(winter["factors"][0]) >= {"raw_value", "normalized_score", "weight", "contribution"}


async def test_rank_hubs_delegates_with_filters(registry: CapabilityRegistry, fx: Fixture) -> None:
    data = await call(
        registry, "rank_hubs", start_date=START, end_date=END, hazards=["winter"], region="midwest"
    )

    assert [r["rank"] for r in data["rankings"]] == [1, 2]
    assert {r["hub_id"] for r in data["rankings"]} == {"chicago", "minneapolis"}
    assert data["applied_weights"] == {"winter": 1.0}
    assert fx.flood.calls == fx.hurricane.calls == []


async def test_compare_hubs_delegates(registry: CapabilityRegistry) -> None:
    data = await call(
        registry,
        "compare_hubs",
        hub_ids=["miami", "denver"],
        start_date=START,
        end_date=END,
        hazards=["hurricane", "flood"],
    )

    assert data["hub_ids"] == ["miami", "denver"]
    assert [c["hazard"] for c in data["hazard_comparisons"]] == ["flood", "hurricane"]
    assert len(data["overall_differences"]) == 1


async def test_service_errors_propagate_unchanged(registry: CapabilityRegistry) -> None:
    with pytest.raises(HubNotFoundError):
        await call(registry, "analyze_hub_risk", hub_id="atlantis", start_date=START, end_date=END)


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("compare_hubs", {"hub_ids": ["miami"], "start_date": START, "end_date": END}),
        ("analyze_hub_risk", {"hub_id": "denver", "start_date": "last year", "end_date": END}),
        ("rank_hubs", {"start_date": START, "end_date": END, "hazards": ["tornado"]}),
        ("list_hubs", {"region": "midwest", "unexpected": True}),
    ],
    ids=["one-hub", "bad-date", "bad-hazard", "unknown-field"],
)
def test_invalid_arguments_are_rejected(
    registry: CapabilityRegistry, name: str, arguments: dict
) -> None:
    with pytest.raises(InvalidCapabilityArgumentsError):
        registry.parse_arguments(name, arguments)


async def test_factor_values_carry_an_unambiguous_display_text(registry: CapabilityRegistry) -> None:
    data = await call(
        registry, "analyze_hub_risk", hub_id="denver", start_date=START, end_date=END, hazards=["winter"]
    )

    factors = {f["name"]: f for f in data["hazards"][0]["factors"]}
    frequency = factors["snowfall_frequency"]
    assert frequency["unit"] == "percent"
    assert frequency["display"] == f"{frequency['raw_value']:g}% of days"
    assert factors["snowfall_severity"]["display"].endswith(" cm")
