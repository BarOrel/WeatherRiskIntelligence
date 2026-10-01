"""OpenAiLlmProvider against a fake SDK client: request shape and error mapping. No network."""

import datetime as dt
import logging
from types import SimpleNamespace
from typing import Any

import httpx2
import openai
import pytest
from support.agents import TOY_DEFINITION, Add

from weather_risk.agents.core import (
    CapabilityRegistry,
    LlmMessage,
    LlmResponseError,
    LlmRole,
    LlmTimeoutError,
    LlmUnavailableError,
    ReasoningEngine,
    StructuredLlmClient,
)
from weather_risk.infrastructure.llm import OpenAiConfig, OpenAiLlmProvider

REQUEST = httpx2.Request("POST", "https://api.openai.com/v1/chat/completions")
MESSAGES = [
    LlmMessage(LlmRole.USER, "hi"),
    LlmMessage(LlmRole.ASSISTANT, "hello"),
    LlmMessage(LlmRole.USER, "q"),
]


def status_error(
    cls: type[openai.APIStatusError], code: int, body: object = None
) -> openai.APIStatusError:
    return cls("error", response=httpx2.Response(code, request=REQUEST), body=body)


class FakeCompletions:
    """Returns ``outcome`` on every request, or each item of a list in turn."""

    def __init__(self, outcome: Any) -> None:
        self.outcomes = list(outcome) if isinstance(outcome, list) else None
        self.outcome = outcome
        self.kwargs: dict[str, Any] = {}
        self.requests = 0

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        self.requests += 1
        outcome = self.outcomes.pop(0) if self.outcomes is not None else self.outcome
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def completion(
    content: str | None, finish_reason: str = "stop", refusal: str | None = None
) -> SimpleNamespace:
    message = SimpleNamespace(content=content, refusal=refusal)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish_reason)])


def provider(
    outcome: Any, effort: Any = "medium", blank_retries: int = 2
) -> tuple[OpenAiLlmProvider, FakeCompletions]:
    completions = FakeCompletions(outcome)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    config = OpenAiConfig(
        model="gpt-6-luna",
        max_tokens=16000,
        reasoning_effort=effort,
        blank_response_max_retries=blank_retries,
    )
    return OpenAiLlmProvider(client, config), completions  # type: ignore[arg-type]


async def test_request_shape_and_text() -> None:
    llm, fake = provider(completion("Hello world"))

    assert await llm.complete("SYSTEM", MESSAGES) == "Hello world"
    assert fake.kwargs["model"] == "gpt-6-luna"
    assert fake.kwargs["max_completion_tokens"] == 16000
    assert fake.kwargs["reasoning_effort"] == "medium"
    assert fake.kwargs["messages"] == [
        {"role": "system", "content": "SYSTEM"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "q"},
    ]
    assert "temperature" not in fake.kwargs


async def test_reasoning_effort_is_optional() -> None:
    llm, fake = provider(completion("ok"), effort=None)

    await llm.complete("S", MESSAGES)

    assert "reasoning_effort" not in fake.kwargs


@pytest.mark.parametrize(
    ("error", "expected", "message"),
    [
        (openai.APITimeoutError(request=REQUEST), LlmTimeoutError, "in time"),
        (openai.APIConnectionError(request=REQUEST), LlmUnavailableError, "reach"),
        (status_error(openai.RateLimitError, 429), LlmUnavailableError, "rate limited"),
        (
            status_error(openai.RateLimitError, 429, {"code": "insufficient_quota"}),
            LlmUnavailableError,
            "no remaining quota",
        ),
        (status_error(openai.AuthenticationError, 401), LlmUnavailableError, "credentials"),
        (status_error(openai.InternalServerError, 500), LlmUnavailableError, "temporarily"),
        (status_error(openai.BadRequestError, 400), LlmResponseError, "rejected"),
    ],
)
async def test_sdk_errors_are_mapped(
    error: Exception, expected: type[Exception], message: str
) -> None:
    llm, _ = provider(error)

    with pytest.raises(expected, match=message) as exc_info:
        await llm.complete("S", MESSAGES)

    assert not isinstance(exc_info.value, openai.OpenAIError)


@pytest.mark.parametrize(
    "response",
    [
        completion(None, refusal="I can't help with that."),
        completion("partial", finish_reason="content_filter"),
    ],
    ids=["refusal", "content-filter"],
)
async def test_refusals_are_errors(response: Any) -> None:
    llm, _ = provider(response)

    with pytest.raises(LlmResponseError, match="declined"):
        await llm.complete("S", MESSAGES)


@pytest.mark.parametrize("response", [completion(""), SimpleNamespace(choices=[])])
async def test_empty_responses_are_errors(response: Any) -> None:
    llm, _ = provider(response)

    with pytest.raises(LlmResponseError):
        await llm.complete("S", MESSAGES)


class TestBlankResponseRetry:
    """A successful response with no text is retried (bounded); everything else is not."""

    @pytest.mark.parametrize("blank", ["", "   ", "\n", " \t\n ", None])
    async def test_blank_then_valid_returns_the_valid_text(self, blank: str | None) -> None:
        llm, fake = provider([completion(blank), completion("Answer")])

        assert await llm.complete("S", MESSAGES) == "Answer"
        assert fake.requests == 2

    async def test_blank_twice_then_valid_succeeds_within_the_budget(self) -> None:
        llm, fake = provider([completion(""), completion("  "), completion("Answer")])

        assert await llm.complete("S", MESSAGES) == "Answer"
        assert fake.requests == 3

    @pytest.mark.parametrize("retries", [0, 1, 2, 4])
    async def test_all_blank_raises_after_exactly_one_plus_retries_requests(
        self, retries: int
    ) -> None:
        llm, fake = provider(completion(""), blank_retries=retries)

        with pytest.raises(LlmResponseError, match="returned no text"):
            await llm.complete("S", MESSAGES)

        assert fake.requests == retries + 1

    async def test_valid_response_makes_exactly_one_request(self) -> None:
        llm, fake = provider([completion("Answer"), completion("unused")])

        assert await llm.complete("S", MESSAGES) == "Answer"
        assert fake.requests == 1

    @pytest.mark.parametrize("text", ["{}", "not json", '{"actions": "wrong"}'])
    async def test_non_empty_invalid_json_is_returned_unchanged(self, text: str) -> None:
        llm, fake = provider([completion(text), completion("unused")])

        assert await llm.complete("S", MESSAGES) == text
        assert fake.requests == 1

    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            (openai.APITimeoutError(request=REQUEST), LlmTimeoutError),
            (status_error(openai.RateLimitError, 429), LlmUnavailableError),
            (status_error(openai.InternalServerError, 503), LlmUnavailableError),
            (status_error(openai.BadRequestError, 400), LlmResponseError),
        ],
    )
    async def test_sdk_errors_are_mapped_and_not_retried_here(
        self, error: Exception, expected: type[Exception]
    ) -> None:
        llm, fake = provider([error, completion("unused")])

        with pytest.raises(expected):
            await llm.complete("S", MESSAGES)

        assert fake.requests == 1

    async def test_error_on_a_blank_retry_propagates(self) -> None:
        llm, fake = provider([completion(""), openai.APITimeoutError(request=REQUEST)])

        with pytest.raises(LlmTimeoutError):
            await llm.complete("S", MESSAGES)

        assert fake.requests == 2

    async def test_refusal_is_not_retried(self) -> None:
        llm, fake = provider([completion(None, refusal="No."), completion("unused")])

        with pytest.raises(LlmResponseError, match="declined"):
            await llm.complete("S", MESSAGES)

        assert fake.requests == 1

    async def test_blank_responses_are_logged_with_attempts(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # configure_logging (run by app tests) stops the package logger from propagating.
        monkeypatch.setattr(logging.getLogger("weather_risk"), "propagate", True)
        caplog.set_level(logging.INFO, logger="weather_risk.infrastructure.llm.openai_provider")
        llm, _ = provider(completion(""), blank_retries=1)

        with pytest.raises(LlmResponseError):
            await llm.complete("S", MESSAGES)

        text = caplog.text
        assert "attempt 1/2" in text
        assert "attempt 2/2" in text
        assert "finish_reason=stop" in text
        assert "Retrying LLM request" in text
        assert "on all 2 attempts" in text

    def test_negative_budget_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            OpenAiConfig("m", 100, None, blank_response_max_retries=-1)


class TestReasoningPathsUseTheRetry:
    """Planning and answer synthesis both go through the provider, so both are protected."""

    @staticmethod
    def engine(llm: OpenAiLlmProvider) -> ReasoningEngine:
        return ReasoningEngine(StructuredLlmClient(llm, 2), llm, today=lambda: dt.date(2026, 10, 1))

    async def test_planning_survives_a_blank_completion(self) -> None:
        valid = '{"actions": [], "continue_after_results": false}'
        llm, fake = provider([completion(""), completion(valid)])

        plan = await self.engine(llm).plan(
            TOY_DEFINITION, CapabilityRegistry([Add()]), [], "hello", []
        )

        assert list(plan.actions) == []
        assert fake.requests == 2

    async def test_invalid_plan_json_still_goes_to_structured_repair(self) -> None:
        valid = '{"actions": [], "continue_after_results": false}'
        llm, fake = provider([completion("not json"), completion(valid)])

        await self.engine(llm).plan(TOY_DEFINITION, CapabilityRegistry([Add()]), [], "hi", [])

        assert fake.requests == 2
        repair_request = fake.kwargs["messages"][-1]["content"]
        assert "failed structured-output validation" in repair_request

    async def test_synthesis_survives_a_blank_completion(self) -> None:
        llm, fake = provider([completion("  "), completion("Final answer.")])

        answer = await self.engine(llm).synthesize(TOY_DEFINITION, [], "hello", [])

        assert answer == "Final answer."
        assert fake.requests == 2
