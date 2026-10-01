"""The Agent port: executes an already validated plan through its capabilities.

An agent never calls the LLM, never touches conversation history and never writes prose.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from weather_risk.agents.core.capabilities import CapabilityRegistry
from weather_risk.agents.core.plan import AgentPlan


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    """Who an agent is. The capability catalogue is appended from its registry, never
    duplicated in the instructions."""

    name: str
    description: str
    instructions: str


class ActionStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class ActionRecord:
    """Safe execution trace entry (no LLM reasoning is ever exposed)."""

    capability: str
    arguments: Mapping[str, Any]
    status: ActionStatus
    duration_ms: int
    error: str | None = None


@dataclass(frozen=True, slots=True)
class Observation:
    """Outcome of one capability call: deterministic data or a safe error message."""

    capability: str
    arguments: Mapping[str, Any]
    succeeded: bool
    data: Mapping[str, Any] | None = None
    error: str | None = None
    warnings: tuple[str, ...] = field(default=())

    def to_prompt(self) -> dict[str, Any]:
        entry: dict[str, Any] = {"capability": self.capability, "arguments": self.arguments}
        if self.succeeded:
            entry["result"] = self.data
            if self.warnings:
                entry["warnings"] = list(self.warnings)
        else:
            entry["error"] = self.error
        return entry


@dataclass(frozen=True, slots=True)
class AgentExecutionResult:
    observations: tuple[Observation, ...] = field(default=())
    """New results from this execution (skipped duplicates excluded)."""
    records: tuple[ActionRecord, ...] = field(default=())
    """One trace entry per requested action, including skipped and failed ones."""
    warnings: tuple[str, ...] = field(default=())
    """Execution-level warnings (e.g. actions dropped by the per-plan cap)."""


@dataclass(frozen=True, slots=True)
class AgentResponse:
    """Result of one chat turn, produced by the ChatRuntime."""

    session_id: str
    answer: str
    actions_performed: tuple[ActionRecord, ...] = field(default=())
    warnings: tuple[str, ...] = field(default=())
    results: tuple[Observation, ...] = field(default=())
    """The successful capability results behind the answer (deterministic data, for UIs)."""


class Agent(ABC):
    @property
    @abstractmethod
    def definition(self) -> AgentDefinition: ...

    @property
    @abstractmethod
    def capabilities(self) -> CapabilityRegistry: ...

    @property
    def name(self) -> str:
        return self.definition.name

    @abstractmethod
    async def execute(
        self, plan: AgentPlan, previous: Sequence[Observation] = ()
    ) -> AgentExecutionResult:
        """Run the plan's actions. ``previous`` = results already gathered this turn, so
        identical calls are not repeated."""
