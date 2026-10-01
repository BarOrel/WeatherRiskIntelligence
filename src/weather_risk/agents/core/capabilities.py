"""Capabilities: the only way an agent touches the system. Thin adapters over application
services; they never contain business logic."""

import json
from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError


@dataclass(frozen=True, slots=True)
class CapabilityResult:
    """JSON-ready deterministic data returned to the LLM, plus any warnings."""

    data: Mapping[str, Any]
    warnings: tuple[str, ...] = field(default=())


class AgentCapability[I: BaseModel](ABC):
    name: str
    description: str
    input_model: type[I]

    @abstractmethod
    async def execute(self, input_data: I) -> CapabilityResult: ...


class UnknownCapabilityError(Exception):
    def __init__(self, name: str, available: Iterable[str]) -> None:
        super().__init__(f"Unknown capability '{name}'. Available: {', '.join(available)}")


class InvalidCapabilityArgumentsError(Exception):
    pass


class CapabilityRegistry:
    def __init__(self, capabilities: Iterable[AgentCapability[Any]]) -> None:
        self._capabilities: dict[str, AgentCapability[Any]] = {}
        for capability in capabilities:
            if capability.name in self._capabilities:
                raise ValueError(f"Capability '{capability.name}' is registered more than once")
            self._capabilities[capability.name] = capability

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._capabilities)

    def get(self, name: str) -> AgentCapability[Any]:
        try:
            return self._capabilities[name]
        except KeyError:
            raise UnknownCapabilityError(name, self.names) from None

    def parse_arguments(self, name: str, arguments: Mapping[str, Any]) -> BaseModel:
        capability = self.get(name)
        try:
            return capability.input_model.model_validate(dict(arguments))
        except ValidationError as exc:
            details = "; ".join(
                f"{'.'.join(map(str, e['loc'])) or '<root>'}: {e['msg']}" for e in exc.errors()
            )
            raise InvalidCapabilityArgumentsError(
                f"Invalid arguments for '{name}': {details}"
            ) from exc

    def describe(self) -> str:
        """Capability catalogue for prompts, generated from the registered capabilities."""
        return "\n\n".join(
            f"- {c.name}: {c.description}\n  arguments schema: "
            f"{json.dumps(c.input_model.model_json_schema(), separators=(',', ':'))}"
            for c in self._capabilities.values()
        )
