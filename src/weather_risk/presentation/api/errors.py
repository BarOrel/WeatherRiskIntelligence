"""One error format for the whole API: RFC 9457 "problem details" (application/problem+json).

Every error, expected or not, returns the same JSON body with a stable machine-readable
``code``, so clients never parse human-readable text:

    {"type": "about:blank", "title": "Not Found", "status": 404,
     "detail": "Unknown hub 'atlantis'", "code": "hub_not_found"}

Client errors return their own (safe, curated) message; upstream failures and unexpected
errors return a generic message and log the details.
"""

import logging
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from weather_risk.agents.core import (
    LlmResponseError,
    LlmTimeoutError,
    LlmUnavailableError,
    StructuredOutputError,
)
from weather_risk.application.errors import (
    HazardProviderResponseError,
    HazardProviderTimeoutError,
    HazardProviderUnavailableError,
    HubNotFoundError,
    InvalidDateRangeError,
    InvalidHazardDataError,
    InvalidRiskRequestError,
    InvalidWeatherDataError,
    UnsupportedHazardError,
    WeatherProviderResponseError,
    WeatherProviderTimeoutError,
    WeatherProviderUnavailableError,
)

logger = logging.getLogger(__name__)

PROBLEM_JSON = "application/problem+json"


class FieldError(BaseModel):
    loc: list[str | int] = Field(description="Where the invalid value is, e.g. ['query', 'start_date']")
    msg: str
    type: str


class ProblemDetails(BaseModel):
    """RFC 9457 problem details, with a stable ``code`` for programmatic handling."""

    type: str = Field(default="about:blank", description="Problem type URI (RFC 9457)")
    title: str = Field(description="HTTP status phrase, e.g. 'Not Found'")
    status: int
    detail: str = Field(description="Human-readable explanation of this occurrence")
    code: str = Field(description="Stable machine-readable error code, e.g. 'hub_not_found'")
    errors: list[FieldError] | None = Field(
        default=None, description="Per-field problems (validation errors only)"
    )


class ApiError(Exception):
    """Raised by routers for API-level errors that have no application exception."""

    def __init__(self, status: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail


# Exception -> (status, code, generic detail). A generic detail of None means the exception's
# own message is safe and useful to return (curated, secret-free); otherwise it is logged only.
_ERRORS: dict[type[Exception], tuple[int, str, str | None]] = {
    HubNotFoundError: (404, "hub_not_found", None),
    InvalidDateRangeError: (422, "invalid_date_range", None),
    InvalidRiskRequestError: (422, "invalid_risk_request", None),
    UnsupportedHazardError: (501, "hazard_data_unsupported", None),
    LlmUnavailableError: (503, "llm_unavailable", None),
    LlmTimeoutError: (504, "llm_timeout", None),
    LlmResponseError: (502, "llm_bad_response", None),
    StructuredOutputError: (
        502,
        "llm_invalid_plan",
        "The language model did not return a valid plan; try again",
    ),
    WeatherProviderTimeoutError: (504, "weather_provider_timeout", "The weather provider timed out"),
    WeatherProviderUnavailableError: (
        503,
        "weather_provider_unavailable",
        "The weather provider is unavailable",
    ),
    WeatherProviderResponseError: (
        502,
        "weather_provider_bad_response",
        "The weather provider returned an unexpected response",
    ),
    InvalidWeatherDataError: (
        502,
        "weather_provider_invalid_data",
        "The weather provider returned invalid data",
    ),
    HazardProviderTimeoutError: (504, "hazard_provider_timeout", "The hazard data provider timed out"),
    HazardProviderUnavailableError: (
        503,
        "hazard_provider_unavailable",
        "The hazard data provider is unavailable",
    ),
    HazardProviderResponseError: (
        502,
        "hazard_provider_bad_response",
        "The hazard data provider returned an unexpected response",
    ),
    InvalidHazardDataError: (
        502,
        "hazard_provider_invalid_data",
        "The hazard data provider returned invalid data",
    ),
}

_HTTP_CODES = {404: "not_found", 405: "method_not_allowed"}

ErrorHandler = Callable[[Request, Exception], Awaitable[JSONResponse]]


def problem(
    status: int, code: str, detail: str, errors: list[dict[str, Any]] | None = None
) -> JSONResponse:
    body = ProblemDetails(
        title=HTTPStatus(status).phrase,
        status=status,
        detail=detail,
        code=code,
        errors=[FieldError(**e) for e in errors] if errors is not None else None,
    )
    return JSONResponse(
        status_code=status,
        content=body.model_dump(exclude_none=True),
        media_type=PROBLEM_JSON,
    )


def register_error_handlers(app: FastAPI) -> None:
    for error_type, (status, code, generic) in _ERRORS.items():
        app.add_exception_handler(error_type, _mapped_handler(status, code, generic))
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unexpected_error)


def error_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI documentation of error responses for a route or router."""
    return {
        status: {
            "model": ProblemDetails,
            "description": HTTPStatus(status).phrase,
            "content": {PROBLEM_JSON: {"schema": {"$ref": "#/components/schemas/ProblemDetails"}}},
        }
        for status in statuses
    }


def document_problem_responses(app: FastAPI) -> None:
    """Error responses are only ever ``application/problem+json``. FastAPI also lists
    ``application/json`` for any response that declares a model, so drop it from them."""
    generate = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            spec = generate()
            for operation in (op for path in spec.get("paths", {}).values() for op in path.values()):
                for response in operation.get("responses", {}).values():
                    content = response.get("content", {})
                    if PROBLEM_JSON in content:
                        content.pop("application/json", None)
            app.openapi_schema = spec
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]


def _mapped_handler(status: int, code: str, generic: str | None) -> ErrorHandler:
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        if generic is not None:
            logger.warning("%s %s failed: %s", request.method, request.url.path, exc)
        return problem(status, code, generic or str(exc))

    return handler


async def _api_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return problem(exc.status, exc.code, exc.detail)


async def _validation_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    # Only location, message and type: never echo the submitted input back.
    errors = [
        {"loc": list(e.get("loc", ())), "msg": str(e.get("msg", "")), "type": str(e.get("type", ""))}
        for e in exc.errors()
    ]
    return problem(422, "validation_error", "The request is invalid; see 'errors'.", errors)


async def _http_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    detail = exc.detail if isinstance(exc.detail, str) else HTTPStatus(exc.status_code).phrase
    response = problem(exc.status_code, _HTTP_CODES.get(exc.status_code, "http_error"), detail)
    if exc.headers:
        response.headers.update(exc.headers)
    return response


async def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("%s %s failed unexpectedly", request.method, request.url.path, exc_info=exc)
    return problem(500, "internal_error", "An unexpected error occurred.")
