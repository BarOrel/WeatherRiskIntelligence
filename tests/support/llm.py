"""Scripted LLM for agent tests. No network. Importable as ``support.llm``."""

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from weather_risk.agents.core import LlmMessage, LlmProvider


@dataclass(frozen=True)
class LlmCall:
    system: str
    messages: tuple[LlmMessage, ...]

    @property
    def last_user_message(self) -> str:
        return self.messages[-1].content

    @property
    def transcript(self) -> str:
        return "\n".join(f"{m.role.value}: {m.content}" for m in self.messages)


class ScriptedLlm(LlmProvider):
    """Returns queued responses in order (strings, or exceptions to raise)."""

    def __init__(self, responses: Iterable[str | Exception] = ()) -> None:
        self._responses = list(responses)
        self.calls: list[LlmCall] = []

    def queue(self, *responses: str | Exception) -> None:
        self._responses.extend(responses)

    async def complete(self, system: str, messages: Sequence[LlmMessage]) -> str:
        self.calls.append(LlmCall(system, tuple(messages)))
        if not self._responses:
            raise AssertionError("ScriptedLlm ran out of responses")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    @property
    def remaining(self) -> int:
        return len(self._responses)


def plan(*actions: tuple[str, dict[str, Any]], continue_after_results: bool = False) -> str:
    return json.dumps(
        {
            "actions": [{"capability": c, "arguments": a} for c, a in actions],
            "continue_after_results": continue_after_results,
        }
    )


DONE = plan()
