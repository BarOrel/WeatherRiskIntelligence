from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from support.fakes import FakeWeatherProvider

from weather_risk.application.errors import (
    InvalidWeatherDataError,
    WeatherProviderResponseError,
    WeatherProviderTimeoutError,
    WeatherProviderUnavailableError,
)
from weather_risk.application.weather import WeatherService
from weather_risk.infrastructure.config import Settings
from weather_risk.presentation.api import create_app
from weather_risk.presentation.api.dependencies import get_weather_service

URL = "/hubs/denver/weather/history"
PARAMS = {"start_date": "2024-01-01", "end_date": "2024-01-03"}


@pytest.fixture
def settings(seed_hubs_file: Path) -> Settings:
    return Settings(environment="test", hubs_file=seed_hubs_file, _env_file=None)


def with_fake_provider(app: FastAPI, provider: FakeWeatherProvider) -> None:
    hub_repository = app.state.container.hub_repository
    app.dependency_overrides[get_weather_service] = lambda: WeatherService(
        hub_repository,
        provider,
        max_history_days=366,
    )


@pytest.fixture
def provider() -> FakeWeatherProvider:
    return FakeWeatherProvider()


@pytest.fixture
def client(settings: Settings, provider: FakeWeatherProvider) -> Iterator[TestClient]:
    app = create_app(settings)
    with_fake_provider(app, provider)
    with TestClient(app) as client:
        yield client


def test_returns_history_for_hub(client: TestClient, provider: FakeWeatherProvider) -> None:
    response = client.get(URL, params=PARAMS)

    assert response.status_code == 200
    body = response.json()
    assert body["hub_id"] == "denver"
    assert body["location"] == {"latitude": 39.7392, "longitude": -104.9903}
    assert body["timezone"] == "America/Denver"
    assert (body["start_date"], body["end_date"]) == ("2024-01-01", "2024-01-03")
    assert [day["date"] for day in body["days"]] == ["2024-01-01", "2024-01-02", "2024-01-03"]
    assert body["days"][0] == {
        "date": "2024-01-01",
        "precipitation_mm": 1.2,
        "rain_mm": 1.0,
        "snowfall_cm": 0.0,
        "temperature_max_c": 12.5,
        "temperature_min_c": -1.5,
        "wind_speed_max_kmh": 20.0,
        "wind_gust_max_kmh": 45.0,
    }
    location, _ = provider.calls[0]
    assert (location.latitude, location.longitude) == (39.7392, -104.9903)


def test_unknown_hub_returns_404(client: TestClient) -> None:
    assert client.get("/hubs/atlantis/weather/history", params=PARAMS).status_code == 404


@pytest.mark.parametrize(
    "params",
    [
        {"start_date": "2024-01-05", "end_date": "2024-01-01"},
        {"start_date": "2024-01-01", "end_date": "2999-01-01"},
        {"start_date": "2024-01-01"},
        {"start_date": "not-a-date", "end_date": "2024-01-01"},
    ],
    ids=["reversed", "future", "missing-end", "malformed"],
)
def test_invalid_dates_return_422(client: TestClient, params: dict[str, str]) -> None:
    assert client.get(URL, params=params).status_code == 422


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (WeatherProviderTimeoutError("slow"), 504),
        (WeatherProviderUnavailableError("down"), 503),
        (WeatherProviderResponseError(500, "boom"), 502),
        (InvalidWeatherDataError("garbage"), 502),
    ],
)
def test_provider_failures_map_to_gateway_errors(
    settings: Settings, error: Exception, status: int
) -> None:
    app = create_app(settings)
    with_fake_provider(app, FakeWeatherProvider(errors=[error]))

    with TestClient(app) as client:
        response = client.get(URL, params=PARAMS)

    assert response.status_code == status
    assert str(error) not in response.json()["detail"]


def test_full_stack_uses_open_meteo_adapter_and_cache(settings: Settings) -> None:
    """Real container wiring with only the HTTP transport mocked."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        days = ["2024-01-01", "2024-01-02", "2024-01-03"]
        values = [0.0, 1.0, 2.0]
        return httpx.Response(
            200,
            json={
                "timezone": "America/Denver",
                "daily": {
                    "time": days,
                    "precipitation_sum": values,
                    "rain_sum": values,
                    "snowfall_sum": values,
                    "temperature_2m_max": [5.0, 6.0, 7.0],
                    "temperature_2m_min": [-5.0, -6.0, -7.0],
                    "wind_speed_10m_max": values,
                    "wind_gusts_10m_max": values,
                },
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with TestClient(create_app(settings, http_client=http_client)) as client:
        first = client.get(URL, params=PARAMS)
        second = client.get(URL, params=PARAMS)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["days"][2]["temperature_min_c"] == -7.0
    assert len(requests) == 1
    assert http_client.is_closed
