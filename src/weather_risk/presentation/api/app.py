import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from weather_risk.agents.core import (
    LlmProvider,
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
from weather_risk.container import build_container
from weather_risk.infrastructure.config import Settings, get_settings
from weather_risk.infrastructure.logging import configure_logging
from weather_risk.presentation.api.routers import chat, hazards, health, hubs, risk, weather

logger = logging.getLogger(__name__)

# Errors whose message is safe and useful to return as-is.
_CLIENT_ERRORS: dict[type[Exception], int] = {
    HubNotFoundError: 404,
    InvalidDateRangeError: 422,
    InvalidRiskRequestError: 422,
    UnsupportedHazardError: 501,
    # LLM errors carry curated, secret-free messages.
    LlmUnavailableError: 503,
    LlmTimeoutError: 504,
    LlmResponseError: 502,
}

# Upstream failures: log the details, return a generic message.
_UPSTREAM_ERRORS: dict[type[Exception], tuple[int, str]] = {
    WeatherProviderTimeoutError: (504, "The weather provider timed out"),
    WeatherProviderUnavailableError: (503, "The weather provider is unavailable"),
    WeatherProviderResponseError: (502, "The weather provider returned an unexpected response"),
    InvalidWeatherDataError: (502, "The weather provider returned invalid data"),
    HazardProviderTimeoutError: (504, "The hazard data provider timed out"),
    HazardProviderUnavailableError: (503, "The hazard data provider is unavailable"),
    HazardProviderResponseError: (502, "The hazard data provider returned an unexpected response"),
    InvalidHazardDataError: (502, "The hazard data provider returned invalid data"),
    StructuredOutputError: (502, "The language model did not return a valid plan; try again"),
}

ErrorHandler = Callable[[Request, Exception], Awaitable[JSONResponse]]


def create_app(
    settings: Settings | None = None,
    http_client: httpx.AsyncClient | None = None,
    llm_provider: LlmProvider | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    container = build_container(settings, http_client=http_client, llm_provider=llm_provider)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await container.aclose()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.container = container

    app.include_router(health.router)
    app.include_router(hubs.router)
    app.include_router(weather.router)
    app.include_router(hazards.router)
    app.include_router(risk.router)
    app.include_router(chat.router)
    _register_error_handlers(app)

    # The built Angular chat UI, served last so API routes always take precedence.
    if settings.frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="ui")

    return app


def _register_error_handlers(app: FastAPI) -> None:
    for error_type, status in _CLIENT_ERRORS.items():
        app.add_exception_handler(error_type, _client_error_handler(status))
    for error_type, (status, detail) in _UPSTREAM_ERRORS.items():
        app.add_exception_handler(error_type, _upstream_error_handler(status, detail))


def _client_error_handler(status: int) -> ErrorHandler:
    async def handler(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=status, content={"detail": str(exc)})

    return handler


def _upstream_error_handler(status: int, detail: str) -> ErrorHandler:
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        logger.warning("%s %s failed: %s", request.method, request.url.path, exc)
        return JSONResponse(status_code=status, content={"detail": detail})

    return handler
