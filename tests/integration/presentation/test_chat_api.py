from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from support.llm import ScriptedLlm, plan

from weather_risk.agents.core import LlmTimeoutError, LlmUnavailableError
from weather_risk.infrastructure.config import Settings
from weather_risk.presentation.api import create_app


@pytest.fixture
def settings(seed_hubs_file: Path) -> Settings:
    return Settings(environment="test", hubs_file=seed_hubs_file, _env_file=None)


@pytest.fixture
def llm() -> ScriptedLlm:
    return ScriptedLlm()


@pytest.fixture
def client(settings: Settings, llm: ScriptedLlm) -> Iterator[TestClient]:
    with TestClient(create_app(settings, llm_provider=llm)) as client:
        yield client


def test_new_session_is_created(client: TestClient, llm: ScriptedLlm) -> None:
    llm.queue(plan(("list_hubs", {"region": "midwest"})), "Chicago and Minneapolis.")

    response = client.post("/chat", json={"message": "Which hubs are in the Midwest?"})

    assert response.status_code == 200
    body = response.json()
    assert len(body["session_id"]) == 32
    assert body["answer"] == "Chicago and Minneapolis."
    [action] = body["actions_performed"]
    assert action["capability"] == "list_hubs"
    assert action["arguments"] == {"region": "midwest"}
    assert action["status"] == "success"
    assert isinstance(action["duration_ms"], int)
    assert set(body) == {"session_id", "answer", "actions_performed", "warnings", "results"}
    [result] = body["results"]
    assert result["capability"] == "list_hubs"
    assert result["arguments"] == {"region": "midwest"}
    assert [h["hub_id"] for h in result["data"]["hubs"]] == ["chicago", "minneapolis"]


def test_existing_session_keeps_context(client: TestClient, llm: ScriptedLlm) -> None:
    llm.queue(plan(), "Hi!", plan(), "You said hello.")

    first = client.post("/chat", json={"message": "hello"}).json()
    second = client.post(
        "/chat", json={"session_id": first["session_id"], "message": "What did I say?"}
    ).json()

    assert second["session_id"] == first["session_id"]
    assert "hello" in llm.calls[2].transcript
    assert "Hi!" in llm.calls[2].transcript


def test_separate_sessions_do_not_share_history(client: TestClient, llm: ScriptedLlm) -> None:
    llm.queue(plan(), "A", plan(), "B")

    client.post("/chat", json={"session_id": "alpha", "message": "secret alpha"})
    client.post("/chat", json={"session_id": "beta", "message": "hi"})

    assert "secret alpha" not in llm.calls[2].transcript


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"message": ""},
        {"message": "x" * 4001},
        {"message": "hi", "session_id": "../etc"},
        {"message": "hi", "turn_id": "a b"},
    ],
    ids=["missing", "empty", "too-long", "bad-session-id", "bad-turn-id"],
)
def test_invalid_requests(client: TestClient, payload: dict) -> None:
    assert client.post("/chat", json=payload).status_code == 422


@pytest.mark.parametrize(
    ("script", "status"),
    [
        ([LlmUnavailableError("The language model is rate limited")], 503),
        ([LlmTimeoutError("The language model did not respond in time")], 504),
        (["not json", "still not json", "nope"], 502),
    ],
    ids=["unavailable", "timeout", "malformed-plan"],
)
def test_llm_failures(client: TestClient, llm: ScriptedLlm, script: list, status: int) -> None:
    llm.queue(*script)

    response = client.post("/chat", json={"message": "hi"})

    assert response.status_code == status
    assert "Traceback" not in response.text


def test_without_credentials_chat_returns_503_but_api_works(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)

    with TestClient(create_app(settings)) as client:
        chat = client.post("/chat", json={"message": "hi"})
        hubs = client.get("/hubs")

    assert chat.status_code == 503
    assert "WRI_LLM__API_KEY" in chat.json()["detail"]
    assert hubs.status_code == 200


def test_results_contain_only_successful_structured_data(client: TestClient, llm: ScriptedLlm) -> None:
    llm.queue(
        plan(
            ("get_weather_metrics", {"hub_id": "denver", "start_date": "2999-01-01", "end_date": "2999-01-02"}),
            ("list_hubs", {}),
        ),
        "Partial answer.",
    )

    body = client.post("/chat", json={"message": "x"}).json()

    assert [a["status"] for a in body["actions_performed"]] == ["error", "success"]
    assert [r["capability"] for r in body["results"]] == ["list_hubs"]


def test_built_ui_is_served_at_root_without_shadowing_the_api(
    seed_hubs_file: Path, tmp_path: Path, llm: ScriptedLlm
) -> None:
    (tmp_path / "index.html").write_text("<html>chat ui</html>", encoding="utf-8")
    settings = Settings(
        environment="test", hubs_file=seed_hubs_file, frontend_dir=tmp_path, _env_file=None
    )

    with TestClient(create_app(settings, llm_provider=llm)) as client:
        assert "chat ui" in client.get("/").text
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/hubs").status_code == 200


def test_no_ui_mounted_when_not_built(settings: Settings, llm: ScriptedLlm, tmp_path: Path) -> None:
    missing = settings.model_copy(update={"frontend_dir": tmp_path / "missing"})

    with TestClient(create_app(missing, llm_provider=llm)) as client:
        assert client.get("/").status_code == 404


def test_blank_answer_then_retry_with_same_turn_id_keeps_one_turn(
    client: TestClient, llm: ScriptedLlm
) -> None:
    llm.queue(plan(), "", plan(), "Hello!", plan(), "Next.")
    request = {"session_id": "s1", "turn_id": "t1", "message": "hi"}

    failed = client.post("/chat", json=request)
    retried = client.post("/chat", json=request)
    client.post("/chat", json={"session_id": "s1", "turn_id": "t2", "message": "and?"})

    assert failed.status_code == 502
    assert failed.json() == {"detail": "The language model returned no text"}
    assert retried.status_code == 200
    assert llm.calls[4].transcript == "user: hi\nassistant: Hello!\nuser: and?"


class TestStoredConversations:
    def test_sessions_and_a_full_conversation_are_returned(
        self, client: TestClient, llm: ScriptedLlm
    ) -> None:
        llm.queue(plan(("list_hubs", {"region": "midwest"})), "Chicago and Minneapolis.", plan(), "Yes.")
        first = client.post("/chat", json={"session_id": "s1", "turn_id": "t1", "message": "Midwest hubs?"})
        client.post("/chat", json={"session_id": "s1", "turn_id": "t2", "message": "Sure?"})

        sessions = client.get("/chat/sessions")
        conversation = client.get("/chat/sessions/s1")

        assert sessions.headers["cache-control"] == "no-store"
        assert [(s["session_id"], s["title"], s["turn_count"]) for s in sessions.json()] == [
            ("s1", "Midwest hubs?", 2)
        ]
        body = conversation.json()
        assert conversation.headers["cache-control"] == "no-store"
        assert [(t["turn_id"], t["question"], t["answer"]) for t in body["turns"]] == [
            ("t1", "Midwest hubs?", "Chicago and Minneapolis."),
            ("t2", "Sure?", "Yes."),
        ]
        stored = body["turns"][0]
        assert stored["results"] == first.json()["results"]
        assert stored["actions_performed"] == first.json()["actions_performed"]

    def test_unknown_and_invalid_sessions(self, client: TestClient) -> None:
        assert client.get("/chat/sessions/unknown").status_code == 404
        assert client.get("/chat/sessions/bad id!").status_code == 422
        assert client.get("/chat/sessions", params={"limit": 0}).status_code == 422
        assert client.get("/chat/sessions").json() == []

    def test_sqlite_store_serves_conversations_to_a_second_app_on_the_same_file(
        self, seed_hubs_file: Path, tmp_path: Path, llm: ScriptedLlm
    ) -> None:
        conversation = {"store": "sqlite", "db_file": tmp_path / "weather_risk.db"}
        settings = Settings(
            environment="test", hubs_file=seed_hubs_file, conversation=conversation, _env_file=None
        )
        llm.queue(plan(), "Hello!")
        with TestClient(create_app(settings, llm_provider=llm)) as first_pc:
            session_id = first_pc.post("/chat", json={"message": "hi"}).json()["session_id"]

        with TestClient(create_app(settings, llm_provider=ScriptedLlm())) as second_pc:
            sessions = second_pc.get("/chat/sessions").json()
            turns = second_pc.get(f"/chat/sessions/{session_id}").json()["turns"]

        assert [s["session_id"] for s in sessions] == [session_id]
        assert [(t["question"], t["answer"]) for t in turns] == [("hi", "Hello!")]
