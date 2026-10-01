"""ChatRuntime orchestration: history -> plan (LLM) -> agent.execute -> synthesize -> save.
Uses a scripted LLM and a toy agent that logs when it is called."""

import datetime as dt

import pytest
from support.agents import Add, Fail, ToyAgent
from support.llm import DONE, ScriptedLlm, plan

from weather_risk.agents.core import (
    ActionStatus,
    AgentPlan,
    CapabilityRegistry,
    ChatRuntime,
    LlmMessage,
    LlmResponseError,
    LlmRole,
    LlmTimeoutError,
    LlmUnavailableError,
    ReasoningEngine,
    StructuredLlmClient,
    StructuredOutputError,
)
from weather_risk.infrastructure.conversation import InMemoryConversationRepository


class LoggingLlm(ScriptedLlm):
    """Scripted LLM that also writes 'llm' into the shared event log."""

    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self._events = events

    async def complete(self, system: str, messages: list[LlmMessage]) -> str:  # type: ignore[override]
        self._events.append("plan" if "PLANNING TASK" in system else "synthesize")
        return await super().complete(system, messages)


@pytest.fixture
def events() -> list[str]:
    return []


@pytest.fixture
def add() -> Add:
    return Add()


@pytest.fixture
def agent(add: Add, events: list[str]) -> ToyAgent:
    return ToyAgent(CapabilityRegistry([add, Fail()]), max_actions=4, events=events)


@pytest.fixture
def llm(events: list[str]) -> LoggingLlm:
    return LoggingLlm(events)


@pytest.fixture
def conversations() -> InMemoryConversationRepository:
    return InMemoryConversationRepository(max_messages=20, max_sessions=10)


def make_runtime(
    agent: ToyAgent,
    llm: ScriptedLlm,
    conversations: InMemoryConversationRepository,
    max_iterations: int = 3,
) -> ChatRuntime:
    return ChatRuntime(
        agent,
        ReasoningEngine(StructuredLlmClient(llm, 1), llm, today=lambda: dt.date(2026, 10, 1)),
        conversations,
        max_iterations=max_iterations,
        now=lambda: dt.datetime(2026, 10, 1, tzinfo=dt.UTC),
    )


class TestOrchestration:
    async def test_plan_happens_before_execution_then_synthesis(
        self, agent: ToyAgent, llm: LoggingLlm, conversations: InMemoryConversationRepository,
        events: list[str],
    ) -> None:
        llm.queue(plan(("add", {"a": 2, "b": 3})), "The sum is 5.")

        response = await make_runtime(agent, llm, conversations).run("s", "2+3?")

        assert events == ["plan", "execute", "synthesize"]
        assert response.answer == "The sum is 5."
        assert response.session_id == "s"
        assert [(a.capability, a.status) for a in response.actions_performed] == [
            ("add", ActionStatus.SUCCESS)
        ]
        assert response.warnings == ("approximate",)

    async def test_agent_receives_the_validated_plan(
        self, agent: ToyAgent, llm: LoggingLlm, conversations: InMemoryConversationRepository
    ) -> None:
        llm.queue(f"```json\n{plan(('add', {'a': 2, 'b': 3}))}\n```", "5")

        await make_runtime(agent, llm, conversations).run("s", "2+3?")

        [received] = agent.plans
        assert isinstance(received, AgentPlan)
        assert received.actions[0].capability == "add"
        assert received.actions[0].arguments == {"a": 2, "b": 3}

    async def test_execution_results_reach_synthesis(
        self, agent: ToyAgent, llm: LoggingLlm, conversations: InMemoryConversationRepository
    ) -> None:
        llm.queue(plan(("add", {"a": 2, "b": 3})), "5")

        await make_runtime(agent, llm, conversations).run("s", "2+3?")

        synthesis = llm.calls[1]
        assert "ANSWER TASK" in synthesis.system
        assert '"result": {"sum": 5}' in synthesis.last_user_message

    async def test_no_action_plan_skips_the_agent(
        self, agent: ToyAgent, llm: LoggingLlm, conversations: InMemoryConversationRepository,
        events: list[str],
    ) -> None:
        llm.queue(DONE, "Hello!")

        response = await make_runtime(agent, llm, conversations).run("s", "hi")

        assert events == ["plan", "synthesize"]
        assert response.actions_performed == ()

    async def test_planning_prompt_uses_the_agents_definition_and_capabilities(
        self, agent: ToyAgent, llm: LoggingLlm, conversations: InMemoryConversationRepository
    ) -> None:
        llm.queue(DONE, "ok")

        await make_runtime(agent, llm, conversations).run("s", "hi")

        system = llm.calls[0].system
        assert system.startswith("ROLE: toy agent.")
        assert "TODAY: 2026-10-01" in system
        assert "- add: Add two integers." in system
        assert "OUTPUT FORMAT" in system


class TestMultiStep:
    async def test_plan_execute_plan_execute_synthesize(
        self, agent: ToyAgent, add: Add, llm: LoggingLlm,
        conversations: InMemoryConversationRepository, events: list[str],
    ) -> None:
        llm.queue(
            plan(("add", {"a": 1, "b": 2}), continue_after_results=True),
            plan(("add", {"a": 3, "b": 3})),
            "Done.",
        )

        await make_runtime(agent, llm, conversations).run("s", "chain")

        assert events == ["plan", "execute", "plan", "execute", "synthesize"]
        assert len(add.calls) == 2
        assert '"sum": 3' in llm.calls[1].last_user_message  # second plan saw the first result

    async def test_max_iterations_is_enforced(
        self, agent: ToyAgent, add: Add, llm: LoggingLlm,
        conversations: InMemoryConversationRepository, events: list[str],
    ) -> None:
        llm.queue(
            plan(("add", {"a": 1, "b": 1}), continue_after_results=True),
            plan(("add", {"a": 2, "b": 2}), continue_after_results=True),
            "Partial answer.",
        )

        response = await make_runtime(agent, llm, conversations, max_iterations=2).run(
            "s", "loop"
        )

        assert events == ["plan", "execute", "plan", "execute", "synthesize"]
        assert llm.remaining == 0
        assert any("maximum of 2 reasoning steps" in w for w in response.warnings)

    async def test_agent_cap_warning_is_reported(
        self, add: Add, llm: LoggingLlm, conversations: InMemoryConversationRepository
    ) -> None:
        agent = ToyAgent(CapabilityRegistry([add]), max_actions=2)
        llm.queue(plan(*[("add", {"a": i, "b": 0}) for i in range(5)]), "ok")

        response = await make_runtime(agent, llm, conversations).run("s", "many")

        assert len(add.calls) == 2
        assert any("first 2 of 5" in w for w in response.warnings)

    async def test_llm_can_correct_after_a_capability_error(
        self, agent: ToyAgent, llm: LoggingLlm, conversations: InMemoryConversationRepository
    ) -> None:
        llm.queue(
            plan(("add", {"a": 1}), continue_after_results=True),
            plan(("add", {"a": 1, "b": 1})),
            "2",
        )

        response = await make_runtime(agent, llm, conversations).run("s", "1+1")

        assert [a.status for a in response.actions_performed] == [
            ActionStatus.ERROR,
            ActionStatus.SUCCESS,
        ]
        assert "Invalid arguments" in llm.calls[1].last_user_message


class TestErrors:
    async def test_capability_failure_does_not_abort_the_turn(
        self, agent: ToyAgent, llm: LoggingLlm, conversations: InMemoryConversationRepository
    ) -> None:
        llm.queue(plan(("fail", {"kind": "boom"})), "That failed.")

        response = await make_runtime(agent, llm, conversations).run("s", "x")

        assert response.answer == "That failed."
        assert response.actions_performed[0].status is ActionStatus.ERROR
        assert len(await conversations.get_messages("s")) == 2

    async def test_plan_failure_raises_and_nothing_is_executed_or_saved(
        self, agent: ToyAgent, llm: LoggingLlm, conversations: InMemoryConversationRepository,
        events: list[str],
    ) -> None:
        llm.queue("garbage", "more garbage")

        with pytest.raises(StructuredOutputError):
            await make_runtime(agent, llm, conversations).run("s", "x")

        assert "execute" not in events
        assert await conversations.get_messages("s") == []

    async def test_synthesis_failure_raises_and_turn_is_not_saved(
        self, agent: ToyAgent, llm: LoggingLlm, conversations: InMemoryConversationRepository
    ) -> None:
        llm.queue(plan(("add", {"a": 1, "b": 1})), LlmTimeoutError("slow"))

        with pytest.raises(LlmTimeoutError):
            await make_runtime(agent, llm, conversations).run("s", "x")

        assert await conversations.get_messages("s") == []

    async def test_llm_unavailable_propagates(
        self, agent: ToyAgent, llm: LoggingLlm, conversations: InMemoryConversationRepository
    ) -> None:
        llm.queue(LlmUnavailableError("down"))

        with pytest.raises(LlmUnavailableError):
            await make_runtime(agent, llm, conversations).run("s", "x")

    def test_rejects_invalid_iterations(
        self, agent: ToyAgent, llm: LoggingLlm, conversations: InMemoryConversationRepository
    ) -> None:
        with pytest.raises(ValueError):
            make_runtime(agent, llm, conversations, max_iterations=0)


class TestMemory:
    async def test_turn_is_saved_with_executed_actions(
        self, agent: ToyAgent, llm: LoggingLlm, conversations: InMemoryConversationRepository
    ) -> None:
        llm.queue(plan(("add", {"a": 2, "b": 3})), "5")

        await make_runtime(agent, llm, conversations).run("s", "2+3?")

        user, assistant = await conversations.get_messages("s")
        assert (user.role, user.content) == (LlmRole.USER, "2+3?")
        assert (assistant.role, assistant.content) == (LlmRole.ASSISTANT, "5")
        assert [(a.capability, dict(a.arguments)) for a in assistant.actions] == [
            ("add", {"a": 2, "b": 3})
        ]

    async def test_history_and_previous_actions_reach_the_next_plan(
        self, agent: ToyAgent, llm: LoggingLlm, conversations: InMemoryConversationRepository
    ) -> None:
        llm.queue(plan(("add", {"a": 2, "b": 3})), "5", DONE, "Still 5.")
        runtime = make_runtime(agent, llm, conversations)

        await runtime.run("s", "2+3?")
        await runtime.run("s", "and again?")

        follow_up_plan = llm.calls[2]
        assert [m.content.split("\n")[0] for m in follow_up_plan.messages] == [
            "2+3?",
            "5",
            "and again?",
        ]
        assert 'add {"a": 2, "b": 3}' in follow_up_plan.messages[1].content

    async def test_sessions_are_isolated(
        self, agent: ToyAgent, llm: LoggingLlm, conversations: InMemoryConversationRepository
    ) -> None:
        llm.queue(DONE, "A", DONE, "B")
        runtime = make_runtime(agent, llm, conversations)

        await runtime.run("one", "secret")
        await runtime.run("two", "hi")

        assert "secret" not in llm.calls[2].transcript


class TestTurnIntegrity:
    """A failed or retried turn never leaves half a turn or a duplicate in history."""

    @pytest.mark.parametrize("blank", ["", "   \n "])
    async def test_blank_answer_raises_and_nothing_is_saved(
        self, agent: ToyAgent, llm: LoggingLlm, conversations: InMemoryConversationRepository,
        blank: str,
    ) -> None:
        llm.queue(plan(("add", {"a": 1, "b": 1})), blank)

        with pytest.raises(LlmResponseError, match="no text"):
            await make_runtime(agent, llm, conversations).run("s", "1+1?", turn_id="t1")

        assert await conversations.get_turns("s") == []

    async def test_blank_plan_raises_and_nothing_is_saved(
        self, agent: ToyAgent, llm: LoggingLlm, conversations: InMemoryConversationRepository,
        events: list[str],
    ) -> None:
        llm.queue(LlmResponseError("The language model returned no text"))

        with pytest.raises(LlmResponseError):
            await make_runtime(agent, llm, conversations).run("s", "1+1?", turn_id="t1")

        assert "execute" not in events
        assert await conversations.get_turns("s") == []

    async def test_retry_after_a_failure_saves_exactly_one_turn(
        self, agent: ToyAgent, llm: LoggingLlm, conversations: InMemoryConversationRepository
    ) -> None:
        runtime = make_runtime(agent, llm, conversations)
        llm.queue(plan(("add", {"a": 1, "b": 1})), "")
        with pytest.raises(LlmResponseError):
            await runtime.run("s", "1+1?", turn_id="t1")

        llm.queue(plan(("add", {"a": 1, "b": 1})), "2")
        await runtime.run("s", "1+1?", turn_id="t1")

        assert [(m.role, m.content) for m in await conversations.get_messages("s")] == [
            (LlmRole.USER, "1+1?"),
            (LlmRole.ASSISTANT, "2"),
        ]
        assert len(llm.calls[2].messages) == 1  # the retry's plan saw no leftover history

    async def test_retry_of_an_already_answered_turn_replaces_it(
        self, agent: ToyAgent, llm: LoggingLlm, conversations: InMemoryConversationRepository
    ) -> None:
        runtime = make_runtime(agent, llm, conversations)
        llm.queue(DONE, "first", DONE, "second", DONE, "second again")
        await runtime.run("s", "q1", turn_id="t1")
        await runtime.run("s", "q2", turn_id="t2")

        await runtime.run("s", "q2", turn_id="t2")

        assert [m.content for m in await conversations.get_messages("s")] == [
            "q1", "first", "q2", "second again",
        ]
        retry_plan = llm.calls[4]
        assert [m.content for m in retry_plan.messages[:-1]] == ["q1", "first"]

    async def test_turns_without_an_id_are_never_merged(
        self, agent: ToyAgent, llm: LoggingLlm, conversations: InMemoryConversationRepository
    ) -> None:
        runtime = make_runtime(agent, llm, conversations)
        llm.queue(DONE, "a", DONE, "b")

        await runtime.run("s", "same question")
        await runtime.run("s", "same question")

        assert len(await conversations.get_turns("s")) == 2


class TestStoredConversation:
    async def test_saved_turn_keeps_the_full_response_for_replay(
        self, agent: ToyAgent, llm: LoggingLlm, conversations: InMemoryConversationRepository
    ) -> None:
        llm.queue(plan(("add", {"a": 2, "b": 3}), ("fail", {"kind": "boom"})), "5")
        runtime = make_runtime(agent, llm, conversations)

        response = await runtime.run("s", "2+3?", turn_id="t1")

        [stored] = await runtime.conversation("s")
        assert stored.turn_id == "t1"
        assert stored.actions_performed == response.actions_performed
        assert stored.results == response.results
        assert stored.warnings == response.warnings
        assert [s.session_id for s in await runtime.sessions()] == ["s"]
        assert await runtime.conversation("unknown") == []
