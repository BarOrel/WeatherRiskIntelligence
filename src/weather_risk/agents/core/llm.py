"""LLM port. The agent layer never sees a vendor SDK type."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum


class LlmRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class LlmMessage:
    role: LlmRole
    content: str


class LlmError(Exception):
    """Base class for LLM transport/provider failures (not output-validation failures)."""


class LlmUnavailableError(LlmError):
    """The provider could not be reached, is overloaded, or is not configured."""


class LlmTimeoutError(LlmError):
    """The provider did not respond in time."""


class LlmResponseError(LlmError):
    """The provider rejected the request or returned an unusable response (e.g. a refusal)."""


class LlmProvider(ABC):
    """Text-in/text-out completion. Transport retries are the provider's responsibility."""

    @abstractmethod
    async def complete(self, system: str, messages: Sequence[LlmMessage]) -> str:
        """Return the assistant's text. Raises an ``LlmError`` subclass on failure."""
