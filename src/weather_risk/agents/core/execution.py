"""Reusable plan execution for agents: bounded, validated, duplicate-safe capability dispatch."""

import json
import logging
import time
from collections.abc import Callable, Sequence

from weather_risk.agents.core.agent import (
    ActionRecord,
    ActionStatus,
    AgentExecutionResult,
    Observation,
)
from weather_risk.agents.core.capabilities import (
    CapabilityRegistry,
    InvalidCapabilityArgumentsError,
    UnknownCapabilityError,
)
from weather_risk.agents.core.plan import AgentAction, AgentPlan
from weather_risk.application.errors import ApplicationError

logger = logging.getLogger(__name__)


class PlanExecutor:
    """Executes a validated plan against a capability registry.

    Capability failures never propagate: unknown capabilities, invalid arguments and service
    errors become error observations the LLM can react to; unexpected exceptions are logged
    and reported without internal details.
    """

    def __init__(
        self,
        registry: CapabilityRegistry,
        max_actions: int,
        timer: Callable[[], float] = time.perf_counter,
    ) -> None:
        if max_actions < 1:
            raise ValueError("max_actions must be >= 1")
        self._registry = registry
        self._max_actions = max_actions
        self._timer = timer

    async def execute(
        self, plan: AgentPlan, previous: Sequence[Observation] = ()
    ) -> AgentExecutionResult:
        actions = plan.actions
        warnings: list[str] = []
        if len(actions) > self._max_actions:
            warnings.append(
                f"Only the first {self._max_actions} of {len(actions)} requested actions "
                "were executed."
            )
            actions = actions[: self._max_actions]

        seen = list(previous)
        observations: list[Observation] = []
        records: list[ActionRecord] = []
        for action in actions:
            observation, record = await self._execute(action, seen)
            records.append(record)
            if observation is not None:
                observations.append(observation)
                seen.append(observation)
        return AgentExecutionResult(tuple(observations), tuple(records), tuple(warnings))

    async def _execute(
        self, action: AgentAction, seen: Sequence[Observation]
    ) -> tuple[Observation | None, ActionRecord]:
        name, arguments = action.capability, action.arguments
        start = self._timer()

        def record(status: ActionStatus, error: str | None = None) -> ActionRecord:
            elapsed = round((self._timer() - start) * 1000)
            return ActionRecord(name, arguments, status, elapsed, error)

        if any(o.capability == name and _same(o.arguments, arguments) for o in seen):
            return None, record(ActionStatus.SKIPPED, "Duplicate call; earlier result reused")

        try:
            capability = self._registry.get(name)
            input_data = self._registry.parse_arguments(name, arguments)
            result = await capability.execute(input_data)
        except (UnknownCapabilityError, InvalidCapabilityArgumentsError, ApplicationError) as exc:
            error = str(exc)
        except Exception:
            logger.exception("Capability %s failed unexpectedly", name)
            error = "The capability failed unexpectedly."
        else:
            observation = Observation(
                name, arguments, True, data=result.data, warnings=result.warnings
            )
            return observation, record(ActionStatus.SUCCESS)

        return Observation(name, arguments, False, error=error), record(ActionStatus.ERROR, error)


def _same(a: object, b: object) -> bool:
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)
