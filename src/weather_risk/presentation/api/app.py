import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from weather_risk.agents.core import LlmProvider
from weather_risk.container import build_container
from weather_risk.infrastructure.config import Settings, get_settings
from weather_risk.infrastructure.logging import configure_logging
from weather_risk.presentation.api.errors import (
    document_problem_responses,
    register_error_handlers,
)
from weather_risk.presentation.api.routers import chat, hazards, health, hubs, risk, weather

logger = logging.getLogger(__name__)


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
    register_error_handlers(app)
    document_problem_responses(app)

    # The built Angular chat UI, served last so API routes always take precedence.
    if settings.frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="ui")

    return app
