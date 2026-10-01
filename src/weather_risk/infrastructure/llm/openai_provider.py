"""OpenAI via the official ``openai`` SDK (Chat Completions). The only module that knows
about that SDK."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

import openai

from weather_risk.agents.core.llm import (
    LlmMessage,
    LlmProvider,
    LlmResponseError,
    LlmTimeoutError,
    LlmUnavailableError,
)

logger = logging.getLogger(__name__)

ReasoningEffort = Literal["low", "medium", "high", "xhigh", "max"]


@dataclass(frozen=True, slots=True)
class OpenAiConfig:
    model: str
    max_tokens: int
    reasoning_effort: ReasoningEffort | None
    """Sent only when set; current GPT-6 models are reasoning models and accept it."""
    blank_response_max_retries: int = 2
    """Extra requests after a successful response with blank (whitespace-only) text."""

    def __post_init__(self) -> None:
        if self.blank_response_max_retries < 0:
            raise ValueError("blank_response_max_retries must be >= 0")


class OpenAiLlmProvider(LlmProvider):
    """Two retry concerns, kept apart:

    - transport retries (429/5xx/connection/timeouts) are done by the SDK client
      (``max_retries`` on construction); SDK errors are mapped to LlmError types, never
      retried here;
    - blank-response retries: the model sometimes ends a successful turn without any text
      (finish_reason "stop", empty content). That request is repeated up to
      ``blank_response_max_retries`` times; then ``LlmResponseError`` is raised.

    Non-empty text is returned unchanged, even if it is invalid JSON: structured-output
    repair belongs to StructuredLlmClient.
    """

    def __init__(self, client: openai.AsyncOpenAI, config: OpenAiConfig) -> None:
        self._client = client
        self._config = config

    async def complete(self, system: str, messages: Sequence[LlmMessage]) -> str:
        attempts = self._config.blank_response_max_retries + 1
        for attempt in range(1, attempts + 1):
            response = await self._request(system, messages)
            text = self._text(response)
            if text.strip():
                if attempt > 1:
                    logger.info("LLM returned text on attempt %d/%d", attempt, attempts)
                return text
            logger.warning(
                "LLM returned no text (attempt %d/%d): %s",
                attempt,
                attempts,
                _response_shape(response),
            )
            if attempt < attempts:
                logger.info("Retrying LLM request after a blank response")
        logger.warning("LLM returned no text on all %d attempts; giving up", attempts)
        raise LlmResponseError("The language model returned no text")

    async def _request(self, system: str, messages: Sequence[LlmMessage]) -> Any:
        extra: dict[str, object] = {}
        if self._config.reasoning_effort is not None:
            extra["reasoning_effort"] = self._config.reasoning_effort
        try:
            return await self._client.chat.completions.create(
                model=self._config.model,
                max_completion_tokens=self._config.max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    *({"role": m.role.value, "content": m.content} for m in messages),
                ],
                **extra,  # type: ignore[arg-type]
            )
        except openai.APITimeoutError as exc:
            raise LlmTimeoutError("The language model did not respond in time") from exc
        except openai.APIConnectionError as exc:
            raise LlmUnavailableError("Could not reach the language model") from exc
        except openai.RateLimitError as exc:
            if getattr(exc, "code", None) == "insufficient_quota":
                raise LlmUnavailableError(
                    "The OpenAI account has no remaining quota; check billing/credits"
                ) from exc
            raise LlmUnavailableError("The language model is rate limited") from exc
        except openai.AuthenticationError as exc:
            raise LlmUnavailableError("The language model credentials were rejected") from exc
        except openai.APIStatusError as exc:
            if exc.status_code >= 500:
                raise LlmUnavailableError("The language model is temporarily unavailable") from exc
            raise LlmResponseError(
                f"The language model rejected the request ({exc.status_code})"
            ) from exc

    def _text(self, response: Any) -> str:
        """The response text ("" when blank). Raises for responses that are not retryable."""
        if not response.choices:
            raise LlmResponseError("The language model returned no choices")
        choice = response.choices[0]
        if getattr(choice.message, "refusal", None) or choice.finish_reason == "content_filter":
            raise LlmResponseError("The language model declined to answer this request")
        if choice.finish_reason == "length":
            logger.warning("LLM response hit max_completion_tokens (%d)", self._config.max_tokens)
        content = choice.message.content
        return content if isinstance(content, str) else ""


def _response_shape(response: object) -> str:
    """Everything needed to diagnose an empty completion, without prompt or answer text."""
    choice = response.choices[0]  # type: ignore[attr-defined]
    message = choice.message
    usage = getattr(response, "usage", None)
    details = getattr(usage, "completion_tokens_details", None)
    fields = {
        "id": getattr(response, "id", None),
        "model": getattr(response, "model", None),
        "finish_reason": choice.finish_reason,
        "content": repr(message.content),
        "refusal": getattr(message, "refusal", None),
        "tool_calls": len(getattr(message, "tool_calls", None) or []),
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "reasoning_tokens": getattr(details, "reasoning_tokens", None),
    }
    return " ".join(f"{key}={value}" for key, value in fields.items())
