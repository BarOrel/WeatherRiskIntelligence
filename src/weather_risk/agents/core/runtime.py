"""ChatRuntime: the conversation orchestrator.

One turn:  history -> ReasoningEngine.plan -> Agent.execute -> (plan again if requested,
bounded) -> ReasoningEngine.synthesize -> save turn.

LLM reasoning always happens before agent execution, and the agent only ever receives a
validated AgentPlan. Nothing here is domain-specific.
"""

import datetime as dt
import uuid
from collections.abc import Callable

from weather_risk.agents.core.agent import (
    ActionRecord,
    Agent,
    AgentResponse,
    Observation,
)
from weather_risk.agents.core.conversation import (
    ActionSummary,
    ConversationMessage,
    ConversationRepository,
    ConversationTurn,
    SessionSummary,
)
from weather_risk.agents.core.llm import LlmRole
from weather_risk.agents.core.reasoning import ReasoningEngine


class ChatRuntime:
    """LLM failures (``LlmError``, ``StructuredOutputError``) propagate and the turn is not
    saved; capability failures are handled by the agent and never abort the turn.

    A turn is saved once, atomically, after the answer exists. ``turn_id`` makes a retry
    idempotent: re-running a question the server already answered replaces that turn
    (and leaves it out of the history the retry reasons over) instead of adding a copy."""

    def __init__(
        self,
        agent: Agent,
        reasoning: ReasoningEngine,
        conversations: ConversationRepository,
        max_iterations: int,
        now: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.UTC),
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")
        self._agent = agent
        self._reasoning = reasoning
        self._conversations = conversations
        self._max_iterations = max_iterations
        self._now = now

    @property
    def agent(self) -> Agent:
        return self._agent

    async def run(
        self, session_id: str, message: str, turn_id: str | None = None
    ) -> AgentResponse:
        definition = self._agent.definition
        turn_id = turn_id or uuid.uuid4().hex
        asked_at = self._now()
        history = [
            m
            for turn in await self._conversations.get_turns(session_id)
            if turn.turn_id != turn_id
            for m in (turn.user, turn.assistant)
        ]
        observations: list[Observation] = []
        records: list[ActionRecord] = []
        warnings: list[str] = []

        for iteration in range(1, self._max_iterations + 1):
            plan = await self._reasoning.plan(
                definition, self._agent.capabilities, history, message, observations
            )
            if not plan.actions:
                break
            result = await self._agent.execute(plan, previous=observations)
            observations.extend(result.observations)
            records.extend(result.records)
            warnings.extend(result.warnings)
            if not plan.continue_after_results:
                break
            if iteration == self._max_iterations:
                warnings.append(
                    f"Reached the maximum of {self._max_iterations} reasoning steps; "
                    "the answer uses the results gathered so far."
                )

        answer = await self._reasoning.synthesize(definition, history, message, observations)
        warnings.extend(w for o in observations for w in o.warnings)

        response = AgentResponse(
            session_id=session_id,
            answer=answer,
            actions_performed=tuple(records),
            warnings=tuple(dict.fromkeys(warnings)),
            results=tuple(o for o in observations if o.succeeded),
        )
        await self._remember(turn_id, message, asked_at, response)
        return response

    async def conversation(self, session_id: str) -> list[ConversationTurn]:
        """Every stored turn of a session, oldest first ([] if unknown)."""
        return await self._conversations.get_conversation(session_id)

    async def sessions(self, limit: int = 50) -> list[SessionSummary]:
        """Stored sessions, most recently active first."""
        return await self._conversations.list_sessions(limit)

    async def _remember(
        self, turn_id: str, message: str, asked_at: dt.datetime, response: AgentResponse
    ) -> None:
        turn = ConversationTurn(
            turn_id=turn_id,
            user=ConversationMessage(LlmRole.USER, message, asked_at),
            assistant=ConversationMessage(
                LlmRole.ASSISTANT,
                response.answer,
                self._now(),
                actions=tuple(ActionSummary(o.capability, o.arguments) for o in response.results),
            ),
            actions_performed=response.actions_performed,
            warnings=response.warnings,
            results=response.results,
        )
        await self._conversations.save_turn(response.session_id, turn)
