import datetime as dt

import pytest

from weather_risk.agents.core import ConversationMessage, ConversationTurn, LlmRole
from weather_risk.infrastructure.conversation import InMemoryConversationRepository

T0 = dt.datetime(2026, 10, 1, tzinfo=dt.UTC)


def turn(turn_id: str, question: str | None = None, answer: str | None = None) -> ConversationTurn:
    return ConversationTurn(
        turn_id,
        ConversationMessage(LlmRole.USER, question or f"q-{turn_id}", T0),
        ConversationMessage(LlmRole.ASSISTANT, answer or f"a-{turn_id}", T0),
    )


async def contents(repo: InMemoryConversationRepository, session_id: str) -> list[str]:
    return [m.content for m in await repo.get_messages(session_id)]


async def test_turns_read_back_as_alternating_messages_in_order() -> None:
    repo = InMemoryConversationRepository(max_messages=10, max_sessions=5)

    await repo.save_turn("s", turn("1", "hi", "hello"))
    await repo.save_turn("s", turn("2", "and?", "more"))

    assert [(m.role, m.content) for m in await repo.get_messages("s")] == [
        (LlmRole.USER, "hi"),
        (LlmRole.ASSISTANT, "hello"),
        (LlmRole.USER, "and?"),
        (LlmRole.ASSISTANT, "more"),
    ]


async def test_unknown_session_is_empty() -> None:
    assert await InMemoryConversationRepository(10, 5).get_turns("nope") == []


async def test_sessions_are_independent() -> None:
    repo = InMemoryConversationRepository(10, 5)

    await repo.save_turn("a", turn("1", "in a"))
    await repo.save_turn("b", turn("1", "in b"))

    assert (await contents(repo, "a"))[0] == "in a"
    assert (await contents(repo, "b"))[0] == "in b"


async def test_saving_the_same_turn_id_replaces_it_in_place() -> None:
    repo = InMemoryConversationRepository(10, 5)
    await repo.save_turn("s", turn("1"))
    await repo.save_turn("s", turn("2"))

    await repo.save_turn("s", turn("1", "q-1", "a-1 retried"))

    assert await contents(repo, "s") == ["q-1", "a-1 retried", "q-2", "a-2"]


@pytest.mark.parametrize("max_messages", [4, 5])
async def test_history_is_bounded_by_whole_turns(max_messages: int) -> None:
    repo = InMemoryConversationRepository(max_messages=max_messages, max_sessions=5)

    for i in range(4):
        await repo.save_turn("s", turn(str(i)))

    assert await contents(repo, "s") == ["q-2", "a-2", "q-3", "a-3"]


async def test_least_recently_used_session_is_evicted() -> None:
    repo = InMemoryConversationRepository(max_messages=6, max_sessions=2)
    await repo.save_turn("a", turn("1"))
    await repo.save_turn("b", turn("1"))
    await repo.get_turns("a")  # touch a: b becomes least recently used

    await repo.save_turn("c", turn("1"))

    assert await repo.get_turns("b") == []
    assert len(await repo.get_turns("a")) == 1


@pytest.mark.parametrize(("max_messages", "max_sessions"), [(1, 1), (2, 0)])
def test_rejects_invalid_bounds(max_messages: int, max_sessions: int) -> None:
    with pytest.raises(ValueError):
        InMemoryConversationRepository(max_messages=max_messages, max_sessions=max_sessions)


class TestConversationTurn:
    def test_rejects_a_blank_answer(self) -> None:
        with pytest.raises(ValueError, match="without an answer"):
            turn("1", "q", "   ")

    def test_rejects_swapped_roles(self) -> None:
        user = ConversationMessage(LlmRole.USER, "q", T0)
        assistant = ConversationMessage(LlmRole.ASSISTANT, "a", T0)

        with pytest.raises(ValueError, match="user message followed by"):
            ConversationTurn("1", assistant, user)


async def test_lists_sessions_most_recent_first_and_returns_whole_conversations() -> None:
    repo = InMemoryConversationRepository(10, 5)
    late = dt.datetime(2026, 10, 2, tzinfo=dt.UTC)
    await repo.save_turn("old", turn("1", "first old"))
    await repo.save_turn(
        "new",
        ConversationTurn(
            "1",
            ConversationMessage(LlmRole.USER, "first new", late),
            ConversationMessage(LlmRole.ASSISTANT, "answer", late),
        ),
    )

    sessions = await repo.list_sessions(10)

    assert [(s.session_id, s.title, s.turn_count) for s in sessions] == [
        ("new", "first new", 1),
        ("old", "first old", 1),
    ]
    assert [t.turn_id for t in await repo.get_conversation("old")] == ["1"]
    assert await repo.get_conversation("missing") == []
