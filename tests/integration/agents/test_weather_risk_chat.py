"""Chat turns end to end with a scripted LLM: real ChatRuntime, real WeatherRiskAgent and
capabilities, real application use cases over fake data providers. Verifies conversational
follow-ups get the context they need and that deterministic values reach the answer step
unchanged."""

import datetime as dt
import json

import pytest
from support.llm import ScriptedLlm, plan
from support.use_cases import Fixture, make_fixture

from weather_risk.agents.core import (
    ActionStatus,
    ChatRuntime,
    ReasoningEngine,
    StructuredLlmClient,
)
from weather_risk.agents.weather_risk import WEATHER_RISK_AGENT, WeatherRiskAgent
from weather_risk.agents.weather_risk.definition import SUPPORTED_HAZARDS
from weather_risk.application.use_cases import AnalyzeHubRiskRequest
from weather_risk.domain.models import HazardType
from weather_risk.infrastructure.conversation import InMemoryConversationRepository

PERIOD = {"start_date": "2025-01-01", "end_date": "2025-12-31"}
START, END = dt.date(2025, 1, 1), dt.date(2025, 12, 31)


@pytest.fixture
def fx() -> Fixture:
    return make_fixture()


@pytest.fixture
def llm() -> ScriptedLlm:
    return ScriptedLlm()


@pytest.fixture
def chat(fx: Fixture, llm: ScriptedLlm) -> ChatRuntime:
    return ChatRuntime(
        WeatherRiskAgent(fx.capabilities(), max_actions_per_plan=4),
        ReasoningEngine(StructuredLlmClient(llm, 2), llm, today=lambda: dt.date(2026, 10, 1)),
        InMemoryConversationRepository(max_messages=20, max_sessions=10),
        max_iterations=3,
    )


def test_identity(chat: ChatRuntime) -> None:
    assert chat.agent.name == "weather-risk-intelligence"


async def test_planning_prompt_lists_only_this_agents_capabilities(
    chat: ChatRuntime, llm: ScriptedLlm
) -> None:
    llm.queue(plan(), "Hello! Ask me about hub exposure.")

    response = await chat.run("s", "hello")

    system = llm.calls[0].system
    for name in ("list_hubs", "get_weather_metrics", "get_hazard_data", "analyze_hub_risk",
                 "rank_hubs", "compare_hubs"):
        assert f"- {name}:" in system
    assert "You are the Weather Risk Intelligence Agent." in system
    assert "Never invent scores" in system
    assert "TODAY: 2026-10-01" in system
    assert response.actions_performed == ()


async def test_compare_then_what_about_flooding(
    chat: ChatRuntime, llm: ScriptedLlm, fx: Fixture
) -> None:
    llm.queue(
        plan(("compare_hubs", {"hub_ids": ["miami", "houston"], "hazards": ["hurricane"], **PERIOD})),
        "Miami has the higher hurricane exposure.",
    )
    first = await chat.run("chat-1", "Compare Miami and Houston for hurricane exposure.")

    # The follow-up names neither hub; the LLM must get them from the conversation.
    llm.queue(
        plan(("compare_hubs", {"hub_ids": ["miami", "houston"], "hazards": ["flood"], **PERIOD})),
        "For flooding, ...",
    )
    second = await chat.run("chat-1", "What about flooding?")

    follow_up_plan = llm.calls[2]
    assert "Compare Miami and Houston for hurricane exposure." in follow_up_plan.transcript
    assert '"hub_ids": ["miami", "houston"]' in follow_up_plan.transcript
    assert follow_up_plan.last_user_message == "What about flooding?"

    assert first.actions_performed[0].status is ActionStatus.SUCCESS
    [action] = second.actions_performed
    assert action.capability == "compare_hubs" and action.status is ActionStatus.SUCCESS
    assert {loc for loc, _ in fx.flood.calls} == {
        h.location for h in fx.hub_service.list_hubs() if h.id in ("miami", "houston")
    }


async def test_rank_then_why_is_the_first_one_higher(
    chat: ChatRuntime, llm: ScriptedLlm, fx: Fixture
) -> None:
    llm.queue(
        plan(("rank_hubs", {"region": "midwest", "hazards": ["winter"], **PERIOD})),
        "Chicago ranks first, then Minneapolis.",
    )
    await chat.run("chat-2", "Which Midwest hubs are most exposed to winter disruption?")

    llm.queue(
        plan(("compare_hubs", {"hub_ids": ["chicago", "minneapolis"], "hazards": ["winter"], **PERIOD})),
        "Chicago is higher because ...",
    )
    response = await chat.run("chat-2", "Why is the first one higher?")

    follow_up_plan, answer_call = llm.calls[2], llm.calls[3]
    assert 'rank_hubs {"region": "midwest", "hazards": ["winter"]' in follow_up_plan.transcript
    assert "Chicago ranks first" in follow_up_plan.transcript
    # The answer step receives the deterministic factor evidence it must explain.
    results = answer_call.last_user_message
    assert "snowfall_frequency" in results and '"contribution"' in results
    assert response.answer == "Chicago is higher because ..."


async def test_deterministic_values_reach_the_answer_step_unchanged(
    chat: ChatRuntime, llm: ScriptedLlm, fx: Fixture
) -> None:
    llm.queue(plan(("analyze_hub_risk", {"hub_id": "denver", **PERIOD})), "Denver ...")

    await chat.run("s", "Analyze Denver's overall risk for 2025.")

    direct = await fx.analyze.execute(AnalyzeHubRiskRequest("denver", START, END))
    payload = llm.calls[1].last_user_message.split("<capability_results>\n")[1].split("\n</")[0]
    [result] = json.loads(payload)
    assert result["result"]["overall_score"] == round(direct.overall_score, 2)
    assert [h["score"] for h in result["result"]["hazards"]] == [
        round(a.score, 2) for a in direct.hazard_assessments
    ]
    assert "ANSWER TASK" in llm.calls[1].system
    assert "Never recalculate" in llm.calls[1].system


async def test_verification_question_reruns_the_capability(
    chat: ChatRuntime, llm: ScriptedLlm, fx: Fixture
) -> None:
    llm.queue(
        plan(("get_weather_metrics", {"hub_id": "denver", **PERIOD})),
        "Denver had snowfall on 8.49% of days.",
    )
    await chat.run("s", "What percentage of days in Denver last year had snowfall?")

    llm.queue(
        plan(("get_weather_metrics", {"hub_id": "denver", **PERIOD})),
        "Confirmed from the data: ...",
    )
    await chat.run("s", "Was Denver snowfall really 8.49%?")

    assert "Conversation history is CONTEXT, not evidence." in llm.calls[2].system
    assert len(fx.weather.calls) == 2  # verified against data, not the earlier answer text


async def test_invalid_llm_request_does_not_break_the_turn(
    chat: ChatRuntime, llm: ScriptedLlm
) -> None:
    llm.queue(
        plan(("delete_hub", {"hub_id": "denver"}), ("analyze_hub_risk", {"hub_id": "denver"})),
        "I could not complete that request.",
    )

    response = await chat.run("s", "Do something odd.")

    assert [a.status for a in response.actions_performed] == [
        ActionStatus.ERROR,
        ActionStatus.ERROR,
    ]
    assert "Unknown capability" in (response.actions_performed[0].error or "")
    assert "start_date" in (response.actions_performed[1].error or "")
    assert response.answer == "I could not complete that request."


async def test_hurricane_only_question_fetches_no_weather(
    chat: ChatRuntime, llm: ScriptedLlm, fx: Fixture
) -> None:
    llm.queue(
        plan(("analyze_hub_risk", {"hub_id": "miami", "hazards": ["hurricane"], **PERIOD})),
        "Miami ...",
    )

    response = await chat.run("s", "How exposed is Miami to hurricanes?")

    assert response.actions_performed[0].status is ActionStatus.SUCCESS
    assert fx.weather.calls == []
    assert any(HazardType.HURRICANE.value in str(a.arguments) for a in response.actions_performed)


class TestUnsupportedHazardScope:
    """Unsupported hazards are answered from the agent's declared scope, generically, with no
    capability call; supported hazards still execute normally."""

    SCOPE_RULE = "Do not say or imply that its data is missing, unavailable"

    @pytest.mark.parametrize(
        ("question", "answer"),
        [
            (
                "Which hub has the worst earthquake risk?",
                "Earthquake risk isn't covered by the current model. "
                "I can analyze winter, flood, hurricane and heat exposure.",
            ),
            (
                "Which hub has the highest volcano risk?",
                "Volcanic risk is outside the current model's scope. "
                "Supported hazards: winter, flood, hurricane and heat.",
            ),
        ],
        ids=["earthquake", "volcano"],
    )
    async def test_unsupported_hazard_runs_no_capability_and_states_the_scope(
        self, chat: ChatRuntime, llm: ScriptedLlm, fx: Fixture, question: str, answer: str
    ) -> None:
        llm.queue(plan(), answer)

        response = await chat.run("s", question)

        assert response.actions_performed == ()
        assert response.results == ()
        assert fx.weather.calls == [] and fx.flood.calls == [] and fx.hurricane.calls == []
        planning, synthesis = llm.calls
        for system in (planning.system, synthesis.system):
            assert "The supported hazards are exactly: winter, flood, hurricane, heat." in system
            assert "say clearly\n  that this hazard is not covered by the current model" in system
            assert self.SCOPE_RULE in system
        assert response.answer == answer

    def test_scope_rule_is_generic_and_derived_from_the_hazard_enum(self) -> None:
        instructions = WEATHER_RISK_AGENT.instructions

        assert SUPPORTED_HAZARDS == ", ".join(h.value for h in HazardType)
        assert "earthquake" not in instructions.lower()
        assert "volcan" not in instructions.lower()
        # The generic "data unavailable" rule no longer applies to unsupported hazards.
        assert "If required data for a supported hazard is unavailable, say so." in instructions

    async def test_supported_hazard_still_executes_capabilities(
        self, chat: ChatRuntime, llm: ScriptedLlm
    ) -> None:
        llm.queue(
            plan(("rank_hubs", {"hazards": ["flood"], **PERIOD})),
            "Houston has the highest flood exposure.",
        )

        response = await chat.run("s", "Which hub has the highest flood exposure?")

        assert [(a.capability, a.status) for a in response.actions_performed] == [
            ("rank_hubs", ActionStatus.SUCCESS)
        ]
        assert response.results[0].data["hazards"] == ["flood"]


class TestFactsComeFromTheCurrentTurn:
    """History resolves references; numeric answers are re-fetched through capabilities."""

    GROUNDING = "Conversation history is CONTEXT, not evidence."
    EMPTY_PLAN = 'An empty "actions" list is valid only when the answer needs no data fact'

    async def test_days_follow_up_re_runs_the_weather_metrics_from_context(
        self, chat: ChatRuntime, llm: ScriptedLlm, fx: Fixture
    ) -> None:
        metrics = ("get_weather_metrics", {"hub_id": "denver", **PERIOD})
        llm.queue(plan(metrics), "Denver had snowfall on 8.49% of days.")
        await chat.run("s", "What percentage of days in Denver last year had snowfall?")

        llm.queue(plan(metrics), "That is 31 days.")
        follow_up = await chat.run("s", "How many days is that?")

        assert [(a.capability, a.status) for a in follow_up.actions_performed] == [
            ("get_weather_metrics", ActionStatus.SUCCESS)
        ]
        assert len(fx.weather.calls) == 2
        assert follow_up.results[0].data["snowfall_days"] is not None
        planning = llm.calls[2]
        # Context still works: the follow-up names no hub or period; the planner gets them
        # from the previous turn's recorded capability call.
        assert "denver" not in planning.last_user_message.lower()
        assert 'get_weather_metrics {"hub_id": "denver", "start_date": "2025-01-01"' in planning.transcript
        assert self.GROUNDING in planning.system
        assert "converting a percentage into days" in planning.system
        # The answer step is told to take numbers from this turn's results only.
        assert "never from earlier messages" in llm.calls[3].system
        assert "<capability_results>" in llm.calls[3].last_user_message

    async def test_score_recall_re_runs_the_assessment(
        self, chat: ChatRuntime, llm: ScriptedLlm
    ) -> None:
        analyze = ("analyze_hub_risk", {"hub_id": "miami", "hazards": ["hurricane"], **PERIOD})
        llm.queue(plan(analyze), "Miami's hurricane score is in the results.")
        await chat.run("s", "What is Miami's hurricane exposure score?")

        llm.queue(plan(analyze), "Same score.")
        recall = await chat.run("s", "What was that score again?")

        assert [a.capability for a in recall.actions_performed] == ["analyze_hub_risk"]
        assert recall.actions_performed[0].status is ActionStatus.SUCCESS  # not skipped
        assert recall.results[0].data["hub_id"] == "miami"
        assert "asking a previous number again" in llm.calls[2].system

    @pytest.mark.parametrize(
        "message",
        ["Which hub has the worst earthquake risk?", "Thanks, that's helpful!"],
        ids=["unsupported-hazard", "acknowledgement"],
    )
    async def test_empty_plan_is_still_allowed_when_no_fact_is_needed(
        self, chat: ChatRuntime, llm: ScriptedLlm, fx: Fixture, message: str
    ) -> None:
        llm.queue(plan(), "Answer without data.")

        response = await chat.run("s", message)

        assert response.actions_performed == ()
        assert fx.weather.calls == [] and fx.flood.calls == [] and fx.hurricane.calls == []
        system = llm.calls[0].system
        assert self.EMPTY_PLAN in system
        assert "questions about the agent's scope (including\n  unsupported hazards)" in system
        assert "greetings and\n  acknowledgements" in system


class TestInvestmentPrioritization:
    RULE = "When asked which hub(s) to prioritize for resilience investment"

    async def test_uses_the_deterministic_ranking_and_states_the_limits(
        self, chat: ChatRuntime, llm: ScriptedLlm
    ) -> None:
        llm.queue(plan(("rank_hubs", PERIOD)), "Answer.")

        response = await chat.run("s", "Which hub should we prioritize for resilience investment?")

        assert [(a.capability, a.status) for a in response.actions_performed] == [
            ("rank_hubs", ActionStatus.SUCCESS)
        ]
        ranking = response.results[0].data["rankings"]
        assert [r["rank"] for r in ranking] == list(range(1, len(ranking) + 1))
        for system in (llm.calls[0].system, llm.calls[1].system):
            assert self.RULE in system
            assert "upgrade cost, shipment volume and business\n  criticality, asset value" in system
            assert "Never\n  claim or imply that any of these were assessed." in system

    async def test_scoped_question_keeps_region_and_hazard(
        self, chat: ChatRuntime, llm: ScriptedLlm
    ) -> None:
        llm.queue(plan(("rank_hubs", {"region": "midwest", "hazards": ["winter"], **PERIOD})), "Answer.")

        response = await chat.run("s", "Which Midwest hub should we prioritize for winter resilience?")

        data = response.results[0].data
        assert data["hazards"] == ["winter"]
        assert {r["hub_id"] for r in data["rankings"]} <= {"chicago", "minneapolis"}

    async def test_top_hub_check_follows_the_deterministic_ranking(
        self, chat: ChatRuntime, llm: ScriptedLlm
    ) -> None:
        """The eval check is tied to the ranking result, not to a hard-coded hub."""
        from evals.grader import FAIL, PASS, grade_turn

        llm.queue(plan(("rank_hubs", PERIOD)), "unused")
        response = await chat.run("s", "Which hub should we prioritize for resilience investment?")
        ranking = response.results[0].data["rankings"]
        top, other = ranking[0]["hub_name"], ranking[-1]["hub_name"]
        recorded = {
            "user": "q",
            "actions": [{"capability": "rank_hubs", "arguments": dict(PERIOD), "status": "success"}],
            "results": [{"capability": "rank_hubs", "arguments": dict(PERIOD), "data": response.results[0].data}],
        }
        spec = {"user": "q", "must": {"names_top_ranked_hub_first": True}}

        assert grade_turn(spec, {**recorded, "answer": f"{top} first, then {other}."}).verdict == PASS
        assert grade_turn(spec, {**recorded, "answer": f"{other} first, then {top}."}).verdict == FAIL
