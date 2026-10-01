"""ASGI entrypoint: ``uvicorn weather_risk.main:app``."""

from weather_risk.presentation.api import create_app

app = create_app()
