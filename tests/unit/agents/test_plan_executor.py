"""Capability registry and plan execution (the Agent's job), with toy capabilities.
No LLM and no conversation storage are involved at all."""

import pytest
from support.agents import Add, AddInput, Fail
from support.llm import plan

from weather_risk.agents.core import (
    ActionStatus,
    AgentPlan,
    CapabilityRegistry,
    InvalidCapabilityArgumentsError,
    PlanExecutor,
    UnknownCapabilityError,
)


@pytest.fixture
def add() -> Add:
    return Add()


@pytest.fixture
def registry(add: Add) -> CapabilityRegistry:
    return CapabilityRegistry([add, Fail()])


def make_plan(*actions: tuple[str, dict]) -> AgentPlan:
    return AgentPlan.model_validate_json(plan(*actions))


class TestRegistry:
    def test_resolves_by_name(self, registry: CapabilityRegistry, add: Add) -> None:
        assert registry.get("add") is add
        assert registry.names == ("add", "fail")

    def test_rejects_duplicates(self) -> None:
        with pytest.raises(ValueError, match="more than once"):
            CapabilityRegistry([Add(), Add()])

    def test_unknown_capability(self, registry: CapabilityRegistry) -> None:
        with pytest.raises(UnknownCapabilityError, match="Available: add, fail"):
            registry.get("delete_everything")

    def test_validates_arguments(self, registry: CapabilityRegistry) -> None:
        assert registry.parse_arguments("add", {"a": 1, "b": 2}) == AddInput(a=1, b=2)
        with pytest.raises(InvalidCapabilityArgumentsError, match="b"):
            registry.parse_arguments("add", {"a": 1})

    def test_describe_lists_names_and_schemas(self, registry: CapabilityRegistry) -> None:
        text = registry.describe()

        assert "- add: Add two integers." in text
        assert '"required":["a","b"]' in text


class TestExecution:
    async def test_executes_actions_in_order(self, registry: CapabilityRegistry, add: Add) -> None:
        result = await PlanExecutor(registry, 4).execute(
            make_plan(("add", {"a": 1, "b": 1}), ("add", {"a": 2, "b": 2}))
        )

        assert add.calls == [AddInput(a=1, b=1), AddInput(a=2, b=2)]
        assert [o.data for o in result.observations] == [{"sum": 2}, {"sum": 4}]
        assert [r.status for r in result.records] == [ActionStatus.SUCCESS] * 2
        assert result.observations[0].warnings == ("approximate",)

    async def test_empty_plan_does_nothing(self, registry: CapabilityRegistry, add: Add) -> None:
        result = await PlanExecutor(registry, 4).execute(AgentPlan())

        assert result.observations == result.records == ()
        assert add.calls == []

    async def test_unknown_capability_becomes_error(self, registry: CapabilityRegistry) -> None:
        result = await PlanExecutor(registry, 4).execute(make_plan(("rm_rf", {})))

        [record] = result.records
        assert record.status is ActionStatus.ERROR
        assert "Unknown capability 'rm_rf'" in (record.error or "")
        assert result.observations[0].succeeded is False

    async def test_invalid_arguments_become_error(self, registry: CapabilityRegistry, add: Add) -> None:
        result = await PlanExecutor(registry, 4).execute(make_plan(("add", {"a": "x"})))

        assert "Invalid arguments for 'add'" in (result.records[0].error or "")
        assert add.calls == []

    async def test_application_error_message_is_kept(self, registry: CapabilityRegistry) -> None:
        result = await PlanExecutor(registry, 4).execute(make_plan(("fail", {"kind": "app"})))

        assert result.records[0].error == "Hub 'atlantis' was not found"

    async def test_unexpected_error_is_not_leaked(self, registry: CapabilityRegistry) -> None:
        result = await PlanExecutor(registry, 4).execute(make_plan(("fail", {"kind": "boom"})))

        assert result.records[0].error == "The capability failed unexpectedly."
        assert "secret" not in str(result.observations[0].to_prompt())

    async def test_actions_are_capped(self, registry: CapabilityRegistry, add: Add) -> None:
        actions = [("add", {"a": i, "b": 0}) for i in range(5)]

        result = await PlanExecutor(registry, 2).execute(make_plan(*actions))

        assert len(add.calls) == 2
        assert any("first 2 of 5" in w for w in result.warnings)

    async def test_duplicate_within_plan_is_skipped(self, registry: CapabilityRegistry, add: Add) -> None:
        result = await PlanExecutor(registry, 4).execute(
            make_plan(("add", {"a": 1, "b": 1}), ("add", {"b": 1, "a": 1}))
        )

        assert len(add.calls) == 1
        assert [r.status for r in result.records] == [ActionStatus.SUCCESS, ActionStatus.SKIPPED]
        assert len(result.observations) == 1

    async def test_duplicate_of_previous_result_is_skipped(
        self, registry: CapabilityRegistry, add: Add
    ) -> None:
        executor = PlanExecutor(registry, 4)
        first = await executor.execute(make_plan(("add", {"a": 1, "b": 1})))

        second = await executor.execute(
            make_plan(("add", {"a": 1, "b": 1})), previous=first.observations
        )

        assert len(add.calls) == 1
        assert second.records[0].status is ActionStatus.SKIPPED

    def test_rejects_invalid_cap(self, registry: CapabilityRegistry) -> None:
        with pytest.raises(ValueError):
            PlanExecutor(registry, 0)
