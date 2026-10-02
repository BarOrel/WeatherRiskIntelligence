"""One error format (RFC 9457 problem details) for every failure, documented in OpenAPI."""

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from weather_risk.application.errors import WeatherProviderTimeoutError
from weather_risk.infrastructure.config import Settings
from weather_risk.presentation.api import create_app
from weather_risk.presentation.api.dependencies import get_hub_service, get_weather_service

DATES = {"start_date": "2025-01-01", "end_date": "2025-12-31"}
PROBLEM_KEYS = {"type", "title", "status", "detail", "code"}


@pytest.fixture
def app(seed_hubs_file: Path, tmp_path: Path) -> FastAPI:
    settings = Settings(
        environment="test", hubs_file=seed_hubs_file, frontend_dir=tmp_path / "no-ui", _env_file=None
    )
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def assert_problem(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert PROBLEM_KEYS <= body.keys()
    assert (body["status"], body["code"], body["type"]) == (status, code, "about:blank")
    return body


class TestProblemDetails:
    def test_application_error_keeps_its_safe_message(self, client: TestClient) -> None:
        body = assert_problem(client.get("/hubs/atlantis"), 404, "hub_not_found")
        assert body["title"] == "Not Found"
        assert "atlantis" in body["detail"]

    def test_validation_error_lists_fields_without_echoing_input(self, client: TestClient) -> None:
        response = client.get("/hubs/denver/risk", params={"start_date": "not-a-date", "end_date": "2025-12-31"})

        body = assert_problem(response, 422, "validation_error")
        assert body["errors"][0]["loc"] == ["query", "start_date"]
        assert {"loc", "msg", "type"} == body["errors"][0].keys()
        assert "not-a-date" not in response.text

    def test_invalid_date_range_has_its_own_code(self, client: TestClient) -> None:
        params = {"start_date": "2025-12-31", "end_date": "2025-01-01"}
        assert_problem(client.get("/hubs/denver/weather/metrics", params=params), 422, "invalid_date_range")

    def test_upstream_failure_is_generic_and_logged(
        self, app: FastAPI, client: TestClient, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class TimingOut:
            async def get_hub_history(self, *args: object) -> None:
                raise WeatherProviderTimeoutError("upstream said: secret internal detail")

        app.dependency_overrides[get_weather_service] = lambda: TimingOut()
        monkeypatch.setattr(logging.getLogger("weather_risk"), "propagate", True)

        response = client.get("/hubs/denver/weather/history", params=DATES)

        body = assert_problem(response, 504, "weather_provider_timeout")
        assert body["detail"] == "The weather provider timed out"
        assert "secret internal detail" not in response.text
        assert "secret internal detail" in caplog.text

    def test_unexpected_exception_is_a_json_500_and_logged(
        self, app: FastAPI, client: TestClient, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class Broken:
            def list_hubs(self, region: object = None) -> None:
                raise RuntimeError("database password is hunter2")

        app.dependency_overrides[get_hub_service] = lambda: Broken()
        monkeypatch.setattr(logging.getLogger("weather_risk"), "propagate", True)

        response = client.get("/hubs")

        body = assert_problem(response, 500, "internal_error")
        assert body["detail"] == "An unexpected error occurred."
        assert "hunter2" not in response.text
        assert "RuntimeError: database password is hunter2" in caplog.text  # full traceback logged

    @pytest.mark.parametrize(
        ("method", "path", "status", "code"),
        [
            ("get", "/no-such-route", 404, "not_found"),
            ("delete", "/hubs", 405, "method_not_allowed"),
            ("get", "/chat/sessions/unknown", 404, "session_not_found"),
        ],
    )
    def test_framework_and_router_errors_use_the_same_format(
        self, client: TestClient, method: str, path: str, status: int, code: str
    ) -> None:
        assert_problem(getattr(client, method)(path), status, code)

    def test_llm_unavailable_has_a_code(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY"):
            monkeypatch.delenv(name, raising=False)
        body = assert_problem(client.post("/chat", json={"message": "hi"}), 503, "llm_unavailable")
        assert "WRI_LLM__API_KEY" in body["detail"]


class TestListQueryParameters:
    def test_repeated_hazards_are_validated_against_the_enum(self, client: TestClient) -> None:
        body = assert_problem(
            client.get("/hubs/denver/risk", params=DATES | {"hazards": ["winter", "tornado"]}),
            422,
            "validation_error",
        )
        assert body["errors"][0]["loc"] == ["query", "hazards", 1]

    def test_comma_separated_values_are_no_longer_accepted(self, client: TestClient) -> None:
        response = client.get("/hubs/denver/risk", params=DATES | {"hazards": "winter,flood"})
        assert_problem(response, 422, "validation_error")

    def test_compare_requires_hubs(self, client: TestClient) -> None:
        body = assert_problem(client.get("/risk/compare", params=DATES), 422, "validation_error")
        assert body["errors"][0]["loc"] == ["query", "hubs"]


class TestOpenApi:
    @pytest.fixture
    def spec(self, client: TestClient) -> dict[str, Any]:
        return client.get("/openapi.json").json()

    def test_hazards_is_a_documented_list_of_the_allowed_values(self, spec: dict[str, Any]) -> None:
        params = {p["name"]: p for p in spec["paths"]["/risk/rank"]["get"]["parameters"]}
        hazards = params["hazards"]["schema"]["anyOf"][0]
        assert hazards["type"] == "array"
        enum_ref = hazards["items"]["$ref"].split("/")[-1]
        assert spec["components"]["schemas"][enum_ref]["enum"] == ["winter", "flood", "hurricane", "heat"]
        assert params["hubs"]["schema"]["anyOf"][0]["type"] == "array"

    @pytest.mark.parametrize(
        ("path", "method", "statuses"),
        [
            ("/risk/rank", "get", {"404", "422", "500", "502", "503", "504"}),
            ("/hubs/{hub_id}/hazards/{hazard}", "get", {"404", "422", "500", "501", "502", "503", "504"}),
            ("/hubs/{hub_id}", "get", {"404", "422", "500"}),
            ("/chat", "post", {"422", "500", "502", "503", "504"}),
            ("/chat/sessions/{session_id}", "get", {"404", "422", "500"}),
        ],
    )
    def test_error_responses_are_documented_as_problem_details(
        self, spec: dict[str, Any], path: str, method: str, statuses: set[str]
    ) -> None:
        responses = spec["paths"][path][method]["responses"]
        assert statuses <= responses.keys()
        for status in statuses:
            content = responses[status]["content"]
            assert list(content) == ["application/problem+json"]
            assert content["application/problem+json"]["schema"]["$ref"].endswith("/ProblemDetails")
        assert {"type", "title", "status", "detail", "code"} <= spec["components"]["schemas"]["ProblemDetails"]["properties"].keys()
