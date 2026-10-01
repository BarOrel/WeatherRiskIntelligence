"""Claude via the official Anthropic SDK. The only module that knows about the SDK."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import anthropic

from weather_risk.agents.core.llm import (
    LlmMessage,
    LlmProvider,
    LlmResponseError,
    LlmTimeoutError,
    LlmUnavailableError,
)

logger = logging.getLogger(__name__)

Effort = Literal["low", "medium", "high", "xhigh", "max"]

# Server-side refusal fallback: on a safety decline the API re-runs the request on a
# fallback model chosen by refusal category, inside the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass(frozen=True, slots=True)
class AnthropicConfig:
    model: str
    max_tokens: int
    effort: Effort
    refusal_fallback: bool


class AnthropicLlmProvider(LlmProvider):
    """Transport retries (429/5xx/connection/timeouts) are done by the SDK client
    (``max_retries`` on construction); this class maps SDK errors to LlmError types."""

    def __init__(self, client: anthropic.AsyncAnthropic, config: AnthropicConfig) -> None:
        self._client = client
        self._config = config

    async def complete(self, system: str, messages: Sequence[LlmMessage]) -> str:
        extra: dict[str, object] = {}
        if self._config.refusal_fallback:
            extra = {"betas": [FALLBACK_BETA], "fallbacks": "default"}
        try:
            response = await self._client.beta.messages.create(
                model=self._config.model,
                max_tokens=self._config.max_tokens,
                system=system,
                messages=[{"role": m.role.value, "content": m.content} for m in messages],
                output_config={"effort": self._config.effort},
                **extra,  # type: ignore[arg-type]
            )
        except anthropic.APITimeoutError as exc:
            raise LlmTimeoutError("The language model did not respond in time") from exc
        except anthropic.APIConnectionError as exc:
            raise LlmUnavailableError("Could not reach the language model") from exc
        except anthropic.RateLimitError as exc:
            raise LlmUnavailableError("The language model is rate limited") from exc
        except anthropic.AuthenticationError as exc:
            raise LlmUnavailableError("The language model credentials were rejected") from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                raise LlmUnavailableError("The language model is temporarily unavailable") from exc
            raise LlmResponseError(f"The language model rejected the request ({exc.status_code})") from exc

        if response.stop_reason == "refusal":
            raise LlmResponseError("The language model declined to answer this request")
        if response.stop_reason == "max_tokens":
            logger.warning("LLM response hit max_tokens (%d)", self._config.max_tokens)
        text = "".join(block.text for block in response.content if block.type == "text")
        if not text.strip():
            raise LlmResponseError("The language model returned no text")
        return text


class UnconfiguredLlmProvider(LlmProvider):
    """Used when no credentials are configured, so the rest of the API still runs."""

    async def complete(self, system: str, messages: Sequence[LlmMessage]) -> str:
        raise LlmUnavailableError(
            "No LLM is configured. Set WRI_LLM__API_KEY (or the provider's ANTHROPIC_API_KEY / "
            "OPENAI_API_KEY) to enable chat."
        )
