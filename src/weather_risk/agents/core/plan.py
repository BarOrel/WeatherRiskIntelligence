"""The validated LLM-to-code boundary. Raw LLM text never reaches an agent; only an AgentPlan
produced by StructuredLlmClient (JSON schema + Pydantic validation) does."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability: str = Field(min_length=1, description="Name of a listed capability")
    arguments: dict[str, Any] = Field(
        default_factory=dict, description="Arguments matching that capability's schema"
    )


class AgentPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actions: list[AgentAction] = Field(
        default_factory=list,
        description="Capability calls to run now, in order. Empty when ready to answer.",
    )
    continue_after_results: bool = Field(
        default=False,
        description="True only if you must see these results before deciding further calls.",
    )
