"""LLM interaction only: a structured plan and the final answer.

Turns the agent definition, capability catalogue, conversation and capability results into
LLM requests. Never executes capabilities and never calls application code.
"""

import datetime as dt
import json
import logging
from collections.abc import Callable, Sequence

from weather_risk.agents.core.agent import AgentDefinition, Observation
from weather_risk.agents.core.capabilities import CapabilityRegistry
from weather_risk.agents.core.conversation import ConversationMessage
from weather_risk.agents.core.llm import (
    LlmError,
    LlmMessage,
    LlmProvider,
    LlmResponseError,
    LlmRole,
)
from weather_risk.agents.core.plan import AgentPlan
from weather_risk.agents.core.structured import StructuredLlmClient

logger = logging.getLogger(__name__)


PLANNING_TASK = """\
PLANNING TASK:
Decide which capabilities to call to answer the latest user message.
- List the calls needed now in "actions"; they run in order. Put independent calls together.
- Set "continue_after_results" to true only if you must see these results before choosing
  more calls. Otherwise the final answer is written right after the calls run.
- Use only the listed capability names and their argument schemas.
- Conversation history is CONTEXT, not evidence. Use it to resolve entities, pronouns, the
  previous scope, hazards, the date range and the user's intent ("what about flooding?", "why
  is the first one higher?"), including the capabilities and arguments used in earlier turns.
  Never use it as the source of measurements, scores, rankings, counts, percentages, hazard
  events or factor values. If the answer needs any such value, call the capability that
  provides it in this turn, even if an earlier answer already stated it (results are cached,
  so this is cheap).
- An empty "actions" list is valid only when the answer needs no data fact: greetings and
  acknowledgements, clarifying questions, questions about the agent's scope (including
  unsupported hazards) or the methodology, or when the <capability_results> of THIS turn
  already contain every value needed. It is not valid for asking a previous number again,
  converting a percentage into days, explaining why one hub outranks another, or any score,
  ranking or metric.
- Do not repeat a call whose result is already listed in this turn's <capability_results>."""

ANSWER_TASK = """\
ANSWER TASK:
Write the final answer to the latest user message for a business analyst (not a data
scientist). The full numeric evidence is shown next to your answer, so summarize, don't dump.
- Start with a one-sentence direct answer.
- Then at most 5 short bullets with the key drivers in plain words, e.g. "far more very cold
  days (12.6% vs 3.84% of days)". Do not list every factor.
- Use ONLY this turn's capability results for facts; the conversation is context only. Take
  every number from those results, never from earlier messages. If a value you need is not in
  them, say it was not retrieved instead of repeating an earlier figure.
- Quote numbers exactly as given; when a "display" text is provided, use it as written.
  Never recalculate, re-weight, re-rank or invent values. If something is missing or a
  capability failed, say it is unavailable.
- Call a score high or low only relative to the other hubs or the 0-100 scale, never just
  because the question says so.
- End with one short line on the most relevant caveat (scores are relative exposure, not
  the probability of closure or loss; mention data gaps if any).
- Use plain words: "score", "points", "days". Never use field names such as
  normalized_score, contribution_to_overall or raw_value.
- Refer to hubs and other entities by their names, never by internal ids.
- Do not mention capability names, JSON or internal processing. Keep it under about 150
  words unless the user asks for more detail."""


# Repeated after the data: smaller models follow the most recent instruction most reliably.
ANSWER_REMINDER = """Now write the answer: one direct sentence, then at most 5 short plain-language bullets, then
one caveat line. About 150 words maximum. Use "display" texts for values. No field names
(normalized_score, contribution_to_overall, raw_value, overall_score), no ids, no JSON."""


class ReasoningEngine:
    def __init__(
        self,
        structured_client: StructuredLlmClient,
        llm: LlmProvider,
        today: Callable[[], dt.date] = dt.date.today,
    ) -> None:
        self._structured = structured_client
        self._llm = llm
        self._today = today

    async def plan(
        self,
        definition: AgentDefinition,
        registry: CapabilityRegistry,
        history: Sequence[ConversationMessage],
        message: str,
        observations: Sequence[Observation],
    ) -> AgentPlan:
        system = "\n\n".join(
            [
                definition.instructions,
                f"TODAY: {self._today().isoformat()}",
                f"CAPABILITIES:\n{registry.describe()}",
                PLANNING_TASK,
            ]
        )
        try:
            return await self._structured.generate(
                system, self._messages(history, message, observations), AgentPlan
            )
        except LlmError as exc:
            logger.warning("LLM call failed during planning: %s", exc)
            raise

    async def synthesize(
        self,
        definition: AgentDefinition,
        history: Sequence[ConversationMessage],
        message: str,
        observations: Sequence[Observation],
    ) -> str:
        system = "\n\n".join(
            [definition.instructions, f"TODAY: {self._today().isoformat()}", ANSWER_TASK]
        )
        messages = self._messages(history, message, observations)
        messages[-1] = LlmMessage(LlmRole.USER, f"{messages[-1].content}\n\n{ANSWER_REMINDER}")
        try:
            answer = (await self._llm.complete(system, messages)).strip()
            if not answer:
                # Providers already reject blank text; this keeps the guarantee for any provider.
                raise LlmResponseError("The language model returned no text")
        except LlmError as exc:
            logger.warning("LLM call failed during synthesis: %s", exc)
            raise
        return answer

    @staticmethod
    def _messages(
        history: Sequence[ConversationMessage],
        message: str,
        observations: Sequence[Observation],
    ) -> list[LlmMessage]:
        messages = [LlmMessage(m.role, _render_history(m)) for m in history]
        latest = message
        if observations:
            results = json.dumps([o.to_prompt() for o in observations], default=str)
            latest += f"\n\n<capability_results>\n{results}\n</capability_results>"
        messages.append(LlmMessage(LlmRole.USER, latest))
        return messages


def _render_history(message: ConversationMessage) -> str:
    if not message.actions:
        return message.content
    used = "; ".join(
        f"{a.capability} {json.dumps(a.arguments, default=str)}" for a in message.actions
    )
    return f"{message.content}\n\n[Capabilities used for this answer: {used}]"
