import time
from collections.abc import Callable, Sequence

from weather_risk.agents.core import (
    Agent,
    AgentDefinition,
    AgentExecutionResult,
    AgentPlan,
    CapabilityRegistry,
    Observation,
    PlanExecutor,
)
from weather_risk.agents.weather_risk.definition import WEATHER_RISK_AGENT


class WeatherRiskAgent(Agent):
    """The Weather Risk Intelligence Agent: its definition and capabilities, and execution of
    validated plans against them (bounded, duplicate-safe, failure-safe).

    It never calls the LLM, never touches conversation history and never writes prose; the
    ChatRuntime does that around it.
    """

    def __init__(
        self,
        capabilities: CapabilityRegistry,
        max_actions_per_plan: int,
        definition: AgentDefinition = WEATHER_RISK_AGENT,
        timer: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._capabilities = capabilities
        self._definition = definition
        self._executor = PlanExecutor(capabilities, max_actions_per_plan, timer)

    @property
    def definition(self) -> AgentDefinition:
        return self._definition

    @property
    def capabilities(self) -> CapabilityRegistry:
        return self._capabilities

    async def execute(
        self, plan: AgentPlan, previous: Sequence[Observation] = ()
    ) -> AgentExecutionResult:
        return await self._executor.execute(plan, previous)
