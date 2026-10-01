"""SqliteConversationRepository against a real SQLite file in tmp_path."""

import datetime as dt
import json
import sqlite3
from pathlib import Path

import pytest

from weather_risk.agents.core import (
    ActionRecord,
    ActionStatus,
    ActionSummary,
    ConversationMessage,
    ConversationTurn,
    LlmRole,
    Observation,
)
from weather_risk.infrastructure.conversation import SqliteConversationRepository
from weather_risk.infrastructure.conversation import sqlite as sqlite_module

T0 = dt.datetime(2026, 10, 1, 12, 0, tzinfo=dt.UTC)


def turn(turn_id: str, question: str = "", answer: str = "", minute: int = 0) -> ConversationTurn:
    asked = T0 + dt.timedelta(minutes=minute)
    arguments = {"hub_ids": ["miami", "houston"], "hazards": ["flood"]}
    return ConversationTurn(
        turn_id,
        ConversationMessage(LlmRole.USER, question or f"q-{turn_id}", asked),
        ConversationMessage(
            LlmRole.ASSISTANT,
            answer or f"a-{turn_id}",
            asked + dt.timedelta(seconds=5),
            actions=(ActionSummary("compare_hubs", arguments),),
        ),
        actions_performed=(ActionRecord("compare_hubs", arguments, ActionStatus.SUCCESS, 12),),
        warnings=("NHC best-track data only covers storms through 2025-10-29.",),
        results=(
            Observation(
                "compare_hubs",
                arguments,
                True,
                data={"overall_scores": {"miami": 23.04, "houston": 45.08}},
                warnings=("w",),
            ),
        ),
    )


@pytest.fixture
def db_file(tmp_path: Path) -> Path:
    return tmp_path / "chats" / "weather_risk.db"


@pytest.fixture
def repo(db_file: Path) -> SqliteConversationRepository:
    return SqliteConversationRepository(db_file, max_messages=4)  # 2 turns of context


async def test_creates_the_file_and_schema(repo: SqliteConversationRepository, db_file: Path) -> None:
    assert db_file.exists()
    with sqlite3.connect(db_file) as connection:
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    assert {"sessions", "turns"} <= tables
    assert version == sqlite_module.SCHEMA_VERSION


async def test_a_turn_round_trips_with_its_full_response(repo: SqliteConversationRepository) -> None:
    original = turn("t1", "Compare Miami and Houston for flood exposure.")
    await repo.save_turn("s1", original)

    [stored] = await repo.get_conversation("s1")

    assert stored == original


async def test_conversations_survive_a_new_repository_on_the_same_file(db_file: Path) -> None:
    """What 'running on another PC with the same database file' amounts to."""
    await SqliteConversationRepository(db_file, 20).save_turn("s1", turn("t1"))

    reopened = SqliteConversationRepository(db_file, 20)

    assert [t.turn_id for t in await reopened.get_conversation("s1")] == ["t1"]
    assert [s.session_id for s in await reopened.list_sessions(10)] == ["s1"]


async def test_retry_with_the_same_turn_id_replaces_in_place(repo: SqliteConversationRepository) -> None:
    await repo.save_turn("s1", turn("t1"))
    await repo.save_turn("s1", turn("t2", minute=1))

    await repo.save_turn("s1", turn("t1", answer="a-t1 retried", minute=2))

    turns = await repo.get_conversation("s1")
    assert [(t.turn_id, t.assistant.content) for t in turns] == [("t1", "a-t1 retried"), ("t2", "a-t2")]


async def test_reasoning_context_is_bounded_but_the_conversation_is_complete(
    repo: SqliteConversationRepository,
) -> None:
    for i in range(5):
        await repo.save_turn("s1", turn(f"t{i}", minute=i))

    assert [t.turn_id for t in await repo.get_turns("s1")] == ["t3", "t4"]
    assert [t.turn_id for t in await repo.get_conversation("s1")] == ["t0", "t1", "t2", "t3", "t4"]
    assert [m.content for m in await repo.get_messages("s1")] == ["q-t3", "a-t3", "q-t4", "a-t4"]


async def test_sessions_are_listed_most_recent_first_with_title_and_count(
    repo: SqliteConversationRepository,
) -> None:
    await repo.save_turn("old", turn("t1", "First question of old", minute=0))
    await repo.save_turn("new", turn("t1", "First question of new", minute=5))
    await repo.save_turn("old", turn("t2", "Second question of old", minute=10))

    sessions = await repo.list_sessions(10)

    assert [(s.session_id, s.title, s.turn_count) for s in sessions] == [
        ("old", "First question of old", 2),
        ("new", "First question of new", 1),
    ]
    assert sessions[0].created_at == T0
    assert sessions[0].updated_at == T0 + dt.timedelta(minutes=10, seconds=5)
    assert [s.session_id for s in await repo.list_sessions(1)] == ["old"]


async def test_unknown_session_is_empty(repo: SqliteConversationRepository) -> None:
    assert await repo.get_turns("nope") == []
    assert await repo.get_conversation("nope") == []
    assert await repo.list_sessions(10) == []


async def test_sessions_are_independent(repo: SqliteConversationRepository) -> None:
    await repo.save_turn("a", turn("t1", "in a"))
    await repo.save_turn("b", turn("t1", "in b"))

    assert [t.user.content for t in await repo.get_conversation("a")] == ["in a"]
    assert [t.user.content for t in await repo.get_conversation("b")] == ["in b"]


async def test_a_failed_write_leaves_nothing_behind(
    repo: SqliteConversationRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_dumps(*args: object, **kwargs: object) -> str:
        raise RuntimeError("disk full")

    monkeypatch.setattr(sqlite_module.json, "dumps", broken_dumps)

    with pytest.raises(RuntimeError):
        await repo.save_turn("s1", turn("t1"))

    monkeypatch.setattr(sqlite_module.json, "dumps", json.dumps)
    assert await repo.list_sessions(10) == []  # the session row was rolled back too
    assert await repo.get_conversation("s1") == []


def test_rejects_an_invalid_bound(db_file: Path) -> None:
    with pytest.raises(ValueError):
        SqliteConversationRepository(db_file, max_messages=1)
