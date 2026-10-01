"""WeatherRiskAgent executes validated plans against its own capabilities and returns
structured results. It is constructed without any LLM or conversation dependency."""

import inspect

import pytest
from support.llm import plan
from support.use_cases import Fixture, make_fixture

from weather_risk.agents.core import ActionStatus, Agent, AgentPlan
from weather_risk.agents.weather_risk import WEATHER_RISK_AGENT, WeatherRiskAgent

PERIOD = {"start_date": "2025-01-01", "end_date": "2025-12-31"}


@pytest.fixture
def fx() -> Fixture:
    return make_fixture()


@pytest.fixture
def agent(fx: Fixture) -> WeatherRiskAgent:
    return WeatherRiskAgent(fx.capabilities(), max_actions_per_plan=4)


def make_plan(*actions: tuple[str, dict]) -> AgentPlan:
    return AgentPlan.model_validate_json(plan(*actions))


def test_is_an_agent_with_its_definition_and_capabilities(agent: WeatherRiskAgent) -> None:
    assert isinstance(agent, Agent)
    assert agent.definition is WEATHER_RISK_AGENT
    assert agent.name == "weather-risk-intelligence"
    assert agent.capabilities.names == (
        "list_hubs",
        "get_weather_metrics",
        "get_hazard_data",
        "analyze_hub_risk",
        "rank_hubs",
        "compare_hubs",
    )


def test_has_no_llm_or_conversation_dependencies() -> None:
    parameters = set(inspect.signature(WeatherRiskAgent.__init__).parameters)

    assert parameters == {"self", "capabilities", "max_actions_per_plan", "definition", "timer"}
    assert not hasattr(WeatherRiskAgent, "run")  # the chat lifecycle belongs to ChatRuntime


async def test_executes_plan_and_returns_structured_results(
    agent: WeatherRiskAgent, fx: Fixture
) -> None:
    result = await agent.execute(
        make_plan(
            ("rank_hubs", {"region": "midwest", "hazards": ["winter"], **PERIOD}),
            ("list_hubs", {}),
        )
    )

    assert [r.capability for r in result.records] == ["rank_hubs", "list_hubs"]
    assert [r.status for r in result.records] == [ActionStatus.SUCCESS] * 2
    ranking = result.observations[0].data
    assert ranking is not None
    assert {r["hub_id"] for r in ranking["rankings"]} == {"chicago", "minneapolis"}
    assert fx.flood.calls == fx.hurricane.calls == []  # winter-only: no hazard datasets


async def test_capability_errors_are_returned_not_raised(agent: WeatherRiskAgent) -> None:
    result = await agent.execute(
        make_plan(
            ("analyze_hub_risk", {"hub_id": "atlantis", **PERIOD}),
            ("delete_hub", {"hub_id": "denver"}),
        )
    )

    assert [r.status for r in result.records] == [ActionStatus.ERROR, ActionStatus.ERROR]
    assert result.records[0].error == "Hub 'atlantis' was not found"
    assert "Unknown capability" in (result.records[1].error or "")


async def test_enforces_max_actions_per_plan(fx: Fixture) -> None:
    agent = WeatherRiskAgent(fx.capabilities(), max_actions_per_plan=1)

    result = await agent.execute(make_plan(("list_hubs", {}), ("list_hubs", {"region": "west"})))

    assert len(result.records) == 1
    assert any("first 1 of 2" in w for w in result.warnings)


async def test_skips_calls_already_made_this_turn(agent: WeatherRiskAgent) -> None:
    first = await agent.execute(make_plan(("list_hubs", {})))

    second = await agent.execute(make_plan(("list_hubs", {})), previous=first.observations)

    assert second.records[0].status is ActionStatus.SKIPPED
    assert second.observations == ()
