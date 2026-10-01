"""SQLite conversation store: chats survive restarts and travel with the database file."""

import asyncio
import datetime as dt
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from weather_risk.agents.core.agent import ActionRecord, ActionStatus, Observation
from weather_risk.agents.core.conversation import (
    ActionSummary,
    ConversationMessage,
    ConversationRepository,
    ConversationTurn,
    SessionSummary,
)
from weather_risk.agents.core.llm import LlmRole

SCHEMA_VERSION = 1
_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id  TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS turns (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL REFERENCES sessions (session_id) ON DELETE CASCADE,
    turn_id      TEXT NOT NULL,
    question     TEXT NOT NULL,
    asked_at     TEXT NOT NULL,
    answer       TEXT NOT NULL,
    answered_at  TEXT NOT NULL,
    response     TEXT NOT NULL,
    UNIQUE (session_id, turn_id)
);
CREATE INDEX IF NOT EXISTS turns_by_session ON turns (session_id, id);
CREATE INDEX IF NOT EXISTS sessions_by_update ON sessions (updated_at);
"""


class SqliteConversationRepository(ConversationRepository):
    """Every turn of every session is kept. ``get_turns`` returns only the last
    ``max_messages // 2`` turns, the context window used for reasoning; ``get_conversation``
    returns them all.

    A turn is written in one transaction (session row and turn row together). A retried
    ``turn_id`` updates its row in place, keeping its position. The database uses the
    default rollback journal, so all data stays in the single ``.db`` file.
    """

    def __init__(self, db_file: Path, max_messages: int) -> None:
        if max_messages < 2:
            raise ValueError("max_messages must be >= 2")
        self._db_file = db_file
        self._max_turns = max_messages // 2
        db_file.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    async def get_turns(self, session_id: str) -> list[ConversationTurn]:
        rows = await asyncio.to_thread(
            self._query,
            "SELECT * FROM (SELECT * FROM turns WHERE session_id = ? ORDER BY id DESC LIMIT ?)"
            " ORDER BY id",
            (session_id, self._max_turns),
        )
        return [_turn(row) for row in rows]

    async def get_conversation(self, session_id: str) -> list[ConversationTurn]:
        rows = await asyncio.to_thread(
            self._query, "SELECT * FROM turns WHERE session_id = ? ORDER BY id", (session_id,)
        )
        return [_turn(row) for row in rows]

    async def list_sessions(self, limit: int) -> list[SessionSummary]:
        rows = await asyncio.to_thread(
            self._query,
            "SELECT s.session_id, s.title, s.created_at, s.updated_at, COUNT(t.id) AS turn_count"
            " FROM sessions s JOIN turns t ON t.session_id = s.session_id"
            " GROUP BY s.session_id ORDER BY s.updated_at DESC, s.session_id LIMIT ?",
            (limit,),
        )
        return [
            SessionSummary(
                session_id=row["session_id"],
                title=row["title"],
                created_at=dt.datetime.fromisoformat(row["created_at"]),
                updated_at=dt.datetime.fromisoformat(row["updated_at"]),
                turn_count=row["turn_count"],
            )
            for row in rows
        ]

    async def save_turn(self, session_id: str, turn: ConversationTurn) -> None:
        await asyncio.to_thread(self._save, session_id, turn)

    def _save(self, session_id: str, turn: ConversationTurn) -> None:
        asked_at = turn.user.timestamp.isoformat()
        answered_at = turn.assistant.timestamp.isoformat()
        with self._connect() as connection:  # one transaction: commits or rolls back as a whole
            connection.execute(
                "INSERT INTO sessions (session_id, title, created_at, updated_at)"
                " VALUES (?, ?, ?, ?)"
                " ON CONFLICT (session_id) DO UPDATE SET updated_at = excluded.updated_at",
                (session_id, turn.user.content, asked_at, answered_at),
            )
            connection.execute(
                "INSERT INTO turns"
                " (session_id, turn_id, question, asked_at, answer, answered_at, response)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT (session_id, turn_id) DO UPDATE SET"
                " question = excluded.question, asked_at = excluded.asked_at,"
                " answer = excluded.answer, answered_at = excluded.answered_at,"
                " response = excluded.response",
                (
                    session_id,
                    turn.turn_id,
                    turn.user.content,
                    asked_at,
                    turn.assistant.content,
                    answered_at,
                    json.dumps(_response(turn), default=str),
                ),
            )

    def _query(self, sql: str, parameters: tuple[Any, ...]) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(sql, parameters).fetchall()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._db_file, timeout=10)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            with connection:
                yield connection
        finally:
            connection.close()


def _response(turn: ConversationTurn) -> dict[str, Any]:
    return {
        "actions": [
            {"capability": a.capability, "arguments": dict(a.arguments)}
            for a in turn.assistant.actions
        ],
        "actions_performed": [
            {
                "capability": r.capability,
                "arguments": dict(r.arguments),
                "status": r.status.value,
                "duration_ms": r.duration_ms,
                "error": r.error,
            }
            for r in turn.actions_performed
        ],
        "warnings": list(turn.warnings),
        "results": [
            {
                "capability": o.capability,
                "arguments": dict(o.arguments),
                "data": dict(o.data or {}),
                "warnings": list(o.warnings),
            }
            for o in turn.results
        ],
    }


def _turn(row: sqlite3.Row) -> ConversationTurn:
    response = json.loads(row["response"])
    return ConversationTurn(
        turn_id=row["turn_id"],
        user=ConversationMessage(
            LlmRole.USER, row["question"], dt.datetime.fromisoformat(row["asked_at"])
        ),
        assistant=ConversationMessage(
            LlmRole.ASSISTANT,
            row["answer"],
            dt.datetime.fromisoformat(row["answered_at"]),
            actions=tuple(ActionSummary(a["capability"], a["arguments"]) for a in response["actions"]),
        ),
        actions_performed=tuple(
            ActionRecord(
                r["capability"], r["arguments"], ActionStatus(r["status"]), r["duration_ms"], r["error"]
            )
            for r in response["actions_performed"]
        ),
        warnings=tuple(response["warnings"]),
        results=tuple(
            Observation(o["capability"], o["arguments"], True, data=o["data"], warnings=tuple(o["warnings"]))
            for o in response["results"]
        ),
    )
