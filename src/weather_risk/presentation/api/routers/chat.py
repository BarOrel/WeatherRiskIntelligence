import datetime as dt
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query, Response
from pydantic import BaseModel, Field

from weather_risk.agents.core import (
    ActionRecord,
    AgentResponse,
    ConversationTurn,
    Observation,
    SessionSummary,
)
from weather_risk.presentation.api.dependencies import ChatRuntimeDep

router = APIRouter(tags=["chat"])

MAX_MESSAGE_CHARS = 4000
SESSION_ID_PATTERN = r"^[A-Za-z0-9_\-]+$"
# Stored conversations change with every turn; browsers must always ask again.
NO_STORE = "no-store"


class ChatRequest(BaseModel):
    session_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        pattern=SESSION_ID_PATTERN,
        description="Existing session to continue; omit to start a new one",
    )
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    turn_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9_\-]+$",
        description="Client id for this question; send the same id when retrying it so the "
        "turn is replaced, never duplicated",
    )


class ActionResponse(BaseModel):
    capability: str
    arguments: dict[str, Any]
    status: str
    duration_ms: int
    error: str | None = None

    @classmethod
    def from_domain(cls, record: ActionRecord) -> "ActionResponse":
        return cls(
            capability=record.capability,
            arguments=_jsonable(dict(record.arguments)),
            status=record.status.value,
            duration_ms=record.duration_ms,
            error=record.error,
        )


class ResultResponse(BaseModel):
    """Deterministic data behind the answer, exactly as the capability returned it."""

    capability: str
    arguments: dict[str, Any]
    data: dict[str, Any]
    warnings: list[str]

    @classmethod
    def from_domain(cls, observation: Observation) -> "ResultResponse":
        return cls(
            capability=observation.capability,
            arguments=_jsonable(dict(observation.arguments)),
            data=_jsonable(dict(observation.data or {})),
            warnings=list(observation.warnings),
        )


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    actions_performed: list[ActionResponse]
    warnings: list[str]
    results: list[ResultResponse] = Field(
        default_factory=list, description="Structured results behind the answer (for UIs)"
    )

    @classmethod
    def from_domain(cls, response: AgentResponse) -> "ChatResponse":
        return cls(
            session_id=response.session_id,
            answer=response.answer,
            actions_performed=[ActionResponse.from_domain(a) for a in response.actions_performed],
            warnings=list(response.warnings),
            results=[ResultResponse.from_domain(o) for o in response.results],
        )


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, runtime: ChatRuntimeDep) -> ChatResponse:
    session_id = request.session_id or uuid.uuid4().hex
    response = await runtime.run(session_id, request.message.strip(), request.turn_id)
    return ChatResponse.from_domain(response)


class SessionSummaryResponse(BaseModel):
    session_id: str
    title: str = Field(description="The session's first question")
    created_at: dt.datetime
    updated_at: dt.datetime
    turn_count: int

    @classmethod
    def from_domain(cls, summary: SessionSummary) -> "SessionSummaryResponse":
        return cls(
            session_id=summary.session_id,
            title=summary.title,
            created_at=summary.created_at,
            updated_at=summary.updated_at,
            turn_count=summary.turn_count,
        )


class TurnResponse(BaseModel):
    """One stored question and its full answer (same fields as a /chat response)."""

    turn_id: str
    question: str
    asked_at: dt.datetime
    answer: str
    answered_at: dt.datetime
    actions_performed: list[ActionResponse]
    warnings: list[str]
    results: list[ResultResponse]

    @classmethod
    def from_domain(cls, turn: ConversationTurn) -> "TurnResponse":
        return cls(
            turn_id=turn.turn_id,
            question=turn.user.content,
            asked_at=turn.user.timestamp,
            answer=turn.assistant.content,
            answered_at=turn.assistant.timestamp,
            actions_performed=[ActionResponse.from_domain(a) for a in turn.actions_performed],
            warnings=list(turn.warnings),
            results=[ResultResponse.from_domain(o) for o in turn.results],
        )


class ConversationResponse(BaseModel):
    session_id: str
    turns: list[TurnResponse]


@router.get("/chat/sessions", response_model=list[SessionSummaryResponse])
async def list_sessions(
    runtime: ChatRuntimeDep, response: Response, limit: int = Query(default=50, ge=1, le=200)
) -> list[SessionSummaryResponse]:
    """Stored conversations, most recently active first."""
    response.headers["Cache-Control"] = NO_STORE
    return [SessionSummaryResponse.from_domain(s) for s in await runtime.sessions(limit)]


@router.get("/chat/sessions/{session_id}", response_model=ConversationResponse)
async def get_session(
    runtime: ChatRuntimeDep,
    response: Response,
    session_id: str = Path(min_length=1, max_length=100, pattern=SESSION_ID_PATTERN),
) -> ConversationResponse:
    """A stored conversation with every turn's answer, trace, warnings and results."""
    turns = await runtime.conversation(session_id)
    if not turns:
        raise HTTPException(status_code=404, detail=f"Unknown session '{session_id}'")
    response.headers["Cache-Control"] = NO_STORE
    return ConversationResponse(
        session_id=session_id, turns=[TurnResponse.from_domain(t) for t in turns]
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, dt.date):
        return value.isoformat()
    return value
