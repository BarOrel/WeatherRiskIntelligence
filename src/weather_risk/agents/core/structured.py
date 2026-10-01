"""Typed JSON output on top of any LlmProvider, with bounded repair of invalid output.

Two separate retry concerns:
- transport retries (timeouts, 5xx, rate limits) belong to the LlmProvider; LlmError
  propagates from here untouched;
- structured-output repair (invalid JSON, schema violations) happens here, at most
  ``max_repair_attempts`` times.
"""

import json
import logging
import re
from collections.abc import Sequence

from pydantic import BaseModel, ValidationError

from weather_risk.agents.core.llm import LlmMessage, LlmProvider, LlmRole

logger = logging.getLogger(__name__)

_MAX_ECHOED_CHARS = 4000
_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)

OUTPUT_INSTRUCTIONS = """\
OUTPUT FORMAT:
Respond with ONLY one JSON object that validates against this JSON Schema.
No markdown, no code fences, no commentary, no unknown fields.
{schema}"""

REPAIR_PROMPT = """\
Your previous response failed structured-output validation.

Validation error:
{error}

Previous response:
{previous}

Return ONLY corrected JSON matching this schema:
{schema}

Do not include markdown.
Do not include commentary.
Do not add unknown fields."""


class StructuredOutputError(Exception):
    """The LLM did not produce valid structured output within the repair budget."""

    def __init__(self, model: type[BaseModel], attempts: int, last_error: str) -> None:
        super().__init__(
            f"No valid {model.__name__} after {attempts} attempt(s): {last_error}"
        )
        self.attempts = attempts
        self.last_error = last_error


class StructuredLlmClient:
    def __init__(self, provider: LlmProvider, max_repair_attempts: int) -> None:
        if max_repair_attempts < 0:
            raise ValueError("max_repair_attempts must be >= 0")
        self._provider = provider
        self._max_repair_attempts = max_repair_attempts

    async def generate[T: BaseModel](
        self, system: str, messages: Sequence[LlmMessage], response_model: type[T]
    ) -> T:
        schema = json.dumps(response_model.model_json_schema(), separators=(",", ":"))
        system = f"{system}\n\n{OUTPUT_INSTRUCTIONS.format(schema=schema)}"
        conversation = list(messages)

        for attempt in range(1, self._max_repair_attempts + 2):
            raw = await self._provider.complete(system, conversation)
            try:
                return response_model.model_validate_json(_strip_fences(raw))
            except ValidationError as exc:
                error = _describe(exc)
            logger.warning(
                "Structured output for %s invalid (attempt %d/%d): %s",
                response_model.__name__,
                attempt,
                self._max_repair_attempts + 1,
                error,
            )
            if attempt > self._max_repair_attempts:
                raise StructuredOutputError(response_model, attempt, error)
            conversation += [
                LlmMessage(LlmRole.ASSISTANT, raw or "(empty response)"),
                LlmMessage(
                    LlmRole.USER,
                    REPAIR_PROMPT.format(
                        error=error, previous=raw[:_MAX_ECHOED_CHARS], schema=schema
                    ),
                ),
            ]
        raise AssertionError("unreachable")


def _strip_fences(raw: str) -> str:
    """Tolerate a model wrapping JSON in a code fence; anything else must be pure JSON."""
    text = raw.strip()
    match = _FENCE.match(text)
    return match.group(1) if match else text


def _describe(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(map(str, e['loc'])) or '<root>'}: {e['msg']}" for e in exc.errors()[:10]
    )
