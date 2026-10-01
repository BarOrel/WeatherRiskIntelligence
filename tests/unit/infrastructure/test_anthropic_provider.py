"""AnthropicLlmProvider against a fake SDK client: request shape and error mapping. No network."""

from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest

from weather_risk.agents.core import (
    LlmMessage,
    LlmResponseError,
    LlmRole,
    LlmTimeoutError,
    LlmUnavailableError,
)
from weather_risk.infrastructure.llm import (
    AnthropicConfig,
    AnthropicLlmProvider,
    UnconfiguredLlmProvider,
)

REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
MESSAGES = [LlmMessage(LlmRole.USER, "hi"), LlmMessage(LlmRole.ASSISTANT, "hello"), LlmMessage(LlmRole.USER, "q")]


def status_error(cls: type[anthropic.APIStatusError], code: int) -> anthropic.APIStatusError:
    return cls("error", response=httpx2.Response(code, request=REQUEST), body=None)


class FakeMessages:
    def __init__(self, outcome: Any) -> None:
        self.outcome = outcome
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def response(*blocks: Any, stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(stop_reason=stop_reason, content=list(blocks))


def text(value: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=value)


def provider(outcome: Any, refusal_fallback: bool = True) -> tuple[AnthropicLlmProvider, FakeMessages]:
    messages = FakeMessages(outcome)
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    config = AnthropicConfig(
        model="claude-opus-5-5", max_tokens=16000, effort="medium", refusal_fallback=refusal_fallback
    )
    return AnthropicLlmProvider(client, config), messages  # type: ignore[arg-type]


async def test_request_shape_and_text_extraction() -> None:
    thinking = SimpleNamespace(type="thinking", thinking="")
    llm, fake = provider(response(thinking, text("Hello "), text("world")))

    result = await llm.complete("SYSTEM", MESSAGES)

    assert result == "Hello world"
    assert fake.kwargs["model"] == "claude-opus-5-5"
    assert fake.kwargs["system"] == "SYSTEM"
    assert fake.kwargs["max_tokens"] == 16000
    assert fake.kwargs["output_config"] == {"effort": "medium"}
    assert fake.kwargs["messages"] == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "q"},
    ]
    assert fake.kwargs["fallbacks"] == "default"
    assert fake.kwargs["betas"] == ["server-side-fallback-2026-07-01"]
    assert "temperature" not in fake.kwargs  # rejected by the model


async def test_fallback_can_be_disabled() -> None:
    llm, fake = provider(response(text("ok")), refusal_fallback=False)

    await llm.complete("S", MESSAGES)

    assert "fallbacks" not in fake.kwargs and "betas" not in fake.kwargs


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (anthropic.APITimeoutError(request=REQUEST), LlmTimeoutError),
        (anthropic.APIConnectionError(request=REQUEST), LlmUnavailableError),
        (status_error(anthropic.RateLimitError, 429), LlmUnavailableError),
        (status_error(anthropic.InternalServerError, 500), LlmUnavailableError),
        (status_error(anthropic.AuthenticationError, 401), LlmUnavailableError),
        (status_error(anthropic.BadRequestError, 400), LlmResponseError),
    ],
)
async def test_sdk_errors_are_mapped(error: Exception, expected: type[Exception]) -> None:
    llm, _ = provider(error)

    with pytest.raises(expected) as exc_info:
        await llm.complete("S", MESSAGES)

    assert not isinstance(exc_info.value, anthropic.APIError)


async def test_refusal_is_an_error() -> None:
    llm, _ = provider(response(stop_reason="refusal"))

    with pytest.raises(LlmResponseError, match="declined"):
        await llm.complete("S", MESSAGES)


async def test_empty_text_is_an_error() -> None:
    llm, _ = provider(response(SimpleNamespace(type="thinking", thinking="")))

    with pytest.raises(LlmResponseError, match="no text"):
        await llm.complete("S", MESSAGES)


async def test_unconfigured_provider_explains_how_to_enable() -> None:
    with pytest.raises(LlmUnavailableError, match="WRI_LLM__API_KEY"):
        await UnconfiguredLlmProvider().complete("S", MESSAGES)
