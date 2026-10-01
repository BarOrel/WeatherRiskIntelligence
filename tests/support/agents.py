"""Toy capabilities and agents for testing the generic agent core. Importable as
``support.agents``. Nothing weather-specific."""

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from weather_risk.agents.core import (
    Agent,
    AgentCapability,
    AgentDefinition,
    AgentExecutionResult,
    AgentPlan,
    CapabilityRegistry,
    CapabilityResult,
    Observation,
    PlanExecutor,
)
from weather_risk.application.errors import HubNotFoundError

TOY_DEFINITION = AgentDefinition("toy", "Toy agent", "ROLE: toy agent.")


class AddInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    a: int
    b: int


class Add(AgentCapability[AddInput]):
    name = "add"
    description = "Add two integers."
    input_model = AddInput

    def __init__(self) -> None:
        self.calls: list[AddInput] = []

    async def execute(self, input_data: AddInput) -> CapabilityResult:
        self.calls.append(input_data)
        return CapabilityResult({"sum": input_data.a + input_data.b}, ("approximate",))


class FailInput(BaseModel):
    kind: str


class Fail(AgentCapability[FailInput]):
    name = "fail"
    description = "Always fails."
    input_model = FailInput

    async def execute(self, input_data: FailInput) -> CapabilityResult:
        if input_data.kind == "app":
            raise HubNotFoundError("atlantis")
        raise RuntimeError("secret internal detail")


class ToyAgent(Agent):
    """Executes plans with the shared PlanExecutor and records every call it receives, plus
    an optional shared event log to assert ordering against the LLM."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        max_actions: int = 4,
        events: list[str] | None = None,
    ) -> None:
        self._registry = registry
        self._executor = PlanExecutor(registry, max_actions)
        self.plans: list[AgentPlan] = []
        self.events = events if events is not None else []

    @property
    def definition(self) -> AgentDefinition:
        return TOY_DEFINITION

    @property
    def capabilities(self) -> CapabilityRegistry:
        return self._registry

    async def execute(
        self, plan: AgentPlan, previous: Sequence[Observation] = ()
    ) -> AgentExecutionResult:
        self.plans.append(plan)
        self.events.append("execute")
        return await self._executor.execute(plan, previous)
