import pytest
from pydantic import BaseModel, ConfigDict
from support.llm import ScriptedLlm

from weather_risk.agents.core import (
    AgentPlan,
    LlmMessage,
    LlmRole,
    LlmTimeoutError,
    StructuredLlmClient,
    StructuredOutputError,
)
from weather_risk.domain.models import HazardType


class Pick(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hazard: HazardType
    count: int


USER = [LlmMessage(LlmRole.USER, "pick one")]
VALID = '{"hazard": "flood", "count": 2}'


async def test_valid_json_is_parsed_into_the_model() -> None:
    llm = ScriptedLlm([VALID])

    result = await StructuredLlmClient(llm, max_repair_attempts=2).generate("SYS", USER, Pick)

    assert result == Pick(hazard=HazardType.FLOOD, count=2)
    assert len(llm.calls) == 1
    assert '"hazard"' in llm.calls[0].system  # schema is part of the instructions
    assert llm.calls[0].system.startswith("SYS")


async def test_code_fence_is_tolerated() -> None:
    llm = ScriptedLlm([f"```json\n{VALID}\n```"])

    assert (await StructuredLlmClient(llm, 0).generate("S", USER, Pick)).count == 2


@pytest.mark.parametrize(
    ("bad", "fragment"),
    [
        ("not json at all", "Invalid JSON"),
        ('{"hazard": "flood"}', "count"),  # missing field
        ('{"hazard": "tornado", "count": 1}', "hazard"),  # invalid enum
        ('{"hazard": "flood", "count": 1, "extra": 1}', "extra"),  # unknown field
    ],
    ids=["invalid-json", "missing-field", "bad-enum", "unknown-field"],
)
async def test_invalid_output_triggers_repair_then_succeeds(bad: str, fragment: str) -> None:
    llm = ScriptedLlm([bad, VALID])

    result = await StructuredLlmClient(llm, max_repair_attempts=2).generate("S", USER, Pick)

    assert result.hazard is HazardType.FLOOD
    repair = llm.calls[1]
    assert repair.messages[-2].role is LlmRole.ASSISTANT
    assert repair.messages[-2].content == bad
    assert "failed structured-output validation" in repair.last_user_message
    assert fragment in repair.last_user_message
    assert "Do not include markdown" in repair.last_user_message


async def test_fails_after_max_repair_attempts() -> None:
    llm = ScriptedLlm(["nope", "still nope", "never"])

    with pytest.raises(StructuredOutputError) as exc_info:
        await StructuredLlmClient(llm, max_repair_attempts=2).generate("S", USER, Pick)

    assert exc_info.value.attempts == 3
    assert len(llm.calls) == 3


async def test_zero_repairs_means_single_attempt() -> None:
    llm = ScriptedLlm(["nope"])

    with pytest.raises(StructuredOutputError):
        await StructuredLlmClient(llm, max_repair_attempts=0).generate("S", USER, Pick)
    assert len(llm.calls) == 1


async def test_transport_errors_are_not_repaired() -> None:
    llm = ScriptedLlm([LlmTimeoutError("slow"), VALID])

    with pytest.raises(LlmTimeoutError):
        await StructuredLlmClient(llm, max_repair_attempts=2).generate("S", USER, Pick)
    assert len(llm.calls) == 1  # no repair retry for transport failures


async def test_agent_plan_rejects_unknown_fields() -> None:
    llm = ScriptedLlm(['{"actions": [], "thoughts": "x"}', '{"actions": []}'])

    result = await StructuredLlmClient(llm, 1).generate("S", USER, AgentPlan)

    assert result.actions == []
    assert len(llm.calls) == 2
