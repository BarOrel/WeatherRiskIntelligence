import asyncio
from collections import OrderedDict, deque

from weather_risk.agents.core.conversation import (
    ConversationRepository,
    ConversationTurn,
    SessionSummary,
)


class InMemoryConversationRepository(ConversationRepository):
    """Process-local, bounded conversation memory (used by tests and the evaluation runner).

    Each session keeps its last ``max_messages // 2`` turns (whole question/answer pairs);
    at most ``max_sessions`` sessions are kept, evicting the least recently used. Each read
    and write runs under one lock with no await inside, so a turn is stored all at once or
    not at all. Lost on restart, by design.
    """

    def __init__(self, max_messages: int, max_sessions: int) -> None:
        if max_messages < 2 or max_sessions < 1:
            raise ValueError("max_messages must be >= 2 and max_sessions >= 1")
        self._max_turns = max_messages // 2
        self._max_sessions = max_sessions
        self._sessions: OrderedDict[str, deque[ConversationTurn]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def get_turns(self, session_id: str) -> list[ConversationTurn]:
        async with self._lock:
            turns = self._sessions.get(session_id)
            if turns is None:
                return []
            self._sessions.move_to_end(session_id)
            return list(turns)

    async def get_conversation(self, session_id: str) -> list[ConversationTurn]:
        async with self._lock:
            return list(self._sessions.get(session_id, ()))

    async def list_sessions(self, limit: int) -> list[SessionSummary]:
        async with self._lock:
            summaries = [
                SessionSummary(
                    session_id=session_id,
                    title=turns[0].user.content,
                    created_at=turns[0].user.timestamp,
                    updated_at=turns[-1].assistant.timestamp,
                    turn_count=len(turns),
                )
                for session_id, turns in self._sessions.items()
                if turns
            ]
        summaries.sort(key=lambda s: s.updated_at, reverse=True)
        return summaries[:limit]

    async def save_turn(self, session_id: str, turn: ConversationTurn) -> None:
        async with self._lock:
            turns = self._sessions.get(session_id)
            if turns is None:
                turns = deque(maxlen=self._max_turns)
                self._sessions[session_id] = turns
                while len(self._sessions) > self._max_sessions:
                    self._sessions.popitem(last=False)
            self._sessions.move_to_end(session_id)
            for index, existing in enumerate(turns):
                if existing.turn_id == turn.turn_id:
                    turns[index] = turn
                    return
            turns.append(turn)
