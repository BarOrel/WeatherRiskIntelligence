"""Conversation memory port. History resolves references; it is never treated as fact."""

import datetime as dt
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from weather_risk.agents.core.agent import ActionRecord, Observation
from weather_risk.agents.core.llm import LlmRole


@dataclass(frozen=True, slots=True)
class ActionSummary:
    """What an assistant turn executed; lets follow-ups reuse hubs, hazards and dates."""

    capability: str
    arguments: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ConversationMessage:
    role: LlmRole
    content: str
    timestamp: dt.datetime
    actions: tuple[ActionSummary, ...] = field(default=())


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    """A question and its answer, stored together so history never holds half a turn.

    ``actions_performed``, ``warnings`` and ``results`` keep the full response, so a stored
    conversation can be shown again with its trace and evidence. Reasoning only uses the
    two messages.
    """

    turn_id: str
    user: ConversationMessage
    assistant: ConversationMessage
    actions_performed: tuple[ActionRecord, ...] = field(default=())
    warnings: tuple[str, ...] = field(default=())
    results: tuple[Observation, ...] = field(default=())

    def __post_init__(self) -> None:
        if self.user.role is not LlmRole.USER or self.assistant.role is not LlmRole.ASSISTANT:
            raise ValueError("A turn is a user message followed by an assistant message")
        if not self.assistant.content.strip():
            raise ValueError("A turn cannot be saved without an answer")


@dataclass(frozen=True, slots=True)
class SessionSummary:
    session_id: str
    title: str
    """The session's first question."""
    created_at: dt.datetime
    updated_at: dt.datetime
    turn_count: int


class ConversationRepository(ABC):
    @abstractmethod
    async def get_turns(self, session_id: str) -> list[ConversationTurn]:
        """Most recent turns (bounded, for reasoning), oldest first."""

    @abstractmethod
    async def save_turn(self, session_id: str, turn: ConversationTurn) -> None:
        """Store a whole turn atomically. A turn with the same ``turn_id`` (a retry of a
        question the server already answered) is replaced in place, never duplicated."""

    @abstractmethod
    async def get_conversation(self, session_id: str) -> list[ConversationTurn]:
        """Every stored turn of the session, oldest first ([] if unknown)."""

    @abstractmethod
    async def list_sessions(self, limit: int) -> list[SessionSummary]:
        """Sessions with at least one turn, most recently updated first."""

    async def get_messages(self, session_id: str) -> list[ConversationMessage]:
        """History as alternating user/assistant messages, oldest first."""
        turns = await self.get_turns(session_id)
        return [message for turn in turns for message in (turn.user, turn.assistant)]
