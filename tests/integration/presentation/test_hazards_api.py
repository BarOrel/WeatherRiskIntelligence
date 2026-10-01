from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from support.fakes import FakeFloodProvider, FakeHurricaneProvider

from weather_risk.application.errors import (
    HazardProviderResponseError,
    HazardProviderTimeoutError,
    HazardProviderUnavailableError,
    InvalidHazardDataError,
)
from weather_risk.application.hazards import (
    FloodHazard,
    HazardDataService,
    HazardRegistry,
    HurricaneHazard,
)
from weather_risk.infrastructure.config import Settings
from weather_risk.presentation.api import create_app
from weather_risk.presentation.api.dependencies import get_hazard_data_service

PARAMS = {"start_date": "2024-01-01", "end_date": "2024-01-03"}


@pytest.fixture
def settings(seed_hubs_file: Path) -> Settings:
    return Settings(environment="test", hubs_file=seed_hubs_file, _env_file=None)


def use_fakes(
    app: FastAPI,
    flood: FakeFloodProvider | None = None,
    hurricane: FakeHurricaneProvider | None = None,
    only_flood: bool = False,
) -> None:
    hazards = [FloodHazard(flood or FakeFloodProvider())]
    if not only_flood:
        hazards.append(HurricaneHazard(hurricane or FakeHurricaneProvider()))
    service = HazardDataService(
        hub_repository=app.state.container.hub_repository,
        registry=HazardRegistry(hazards),
        max_history_days=3660,
    )
    app.dependency_overrides[get_hazard_data_service] = lambda: service


@pytest.fixture
def providers() -> tuple[FakeFloodProvider, FakeHurricaneProvider]:
    return FakeFloodProvider(), FakeHurricaneProvider()


@pytest.fixture
def client(
    settings: Settings, providers: tuple[FakeFloodProvider, FakeHurricaneProvider]
) -> Iterator[TestClient]:
    app = create_app(settings)
    use_fakes(app, *providers)
    with TestClient(app) as client:
        yield client


def test_flood_response(
    client: TestClient, providers: tuple[FakeFloodProvider, FakeHurricaneProvider]
) -> None:
    response = client.get("/hubs/houston/hazards/flood", params=PARAMS)

    assert response.status_code == 200
    body = response.json()
    assert body["hazard_type"] == "flood"
    assert body["hub_id"] == "houston"
    assert body["location"] == {"latitude": 29.7604, "longitude": -95.3698}
    assert (body["start_date"], body["end_date"]) == ("2024-01-01", "2024-01-03")
    assert body["source"] == {"name": "Fake source", "url": "https://example.test"}
    assert body["limitations"] == ["Signal only."]
    assert body["days"][0] == {"date": "2024-01-01", "discharge_m3s": 10.0}
    assert "score" not in body
    location, _ = providers[0].calls[0]
    assert (location.latitude, location.longitude) == (29.7604, -95.3698)


def test_hurricane_response(client: TestClient) -> None:
    response = client.get("/hubs/miami/hazards/hurricane", params=PARAMS)

    assert response.status_code == 200
    body = response.json()
    assert body["hazard_type"] == "hurricane"
    assert body["search_radius_km"] == 200.0
    assert body["data_coverage_end"] == "2024-01-03"
    [event] = body["events"]
    assert event["storm_id"] == "AL012024"
    assert event["peak_category"] == 1
    assert event["classification_at_closest_approach"] == "hurricane"
    assert event["track"][0]["time"] == "2024-01-01T12:00:00Z"
    assert "score" not in body


def test_unknown_hub_returns_404(client: TestClient) -> None:
    assert client.get("/hubs/atlantis/hazards/flood", params=PARAMS).status_code == 404


def test_unknown_hazard_name_returns_422(client: TestClient) -> None:
    assert client.get("/hubs/miami/hazards/tornado", params=PARAMS).status_code == 422


@pytest.mark.parametrize(
    "params",
    [
        {"start_date": "2024-01-05", "end_date": "2024-01-01"},
        {"start_date": "2024-01-01", "end_date": "2999-01-01"},
        {"start_date": "2024-01-01"},
    ],
    ids=["reversed", "future", "missing"],
)
def test_invalid_dates_return_422(client: TestClient, params: dict[str, str]) -> None:
    assert client.get("/hubs/miami/hazards/flood", params=params).status_code == 422


def test_registered_type_without_implementation_returns_501(settings: Settings) -> None:
    app = create_app(settings)
    use_fakes(app, only_flood=True)

    with TestClient(app) as client:
        response = client.get("/hubs/miami/hazards/hurricane", params=PARAMS)

    assert response.status_code == 501


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (HazardProviderTimeoutError("slow"), 504),
        (HazardProviderUnavailableError("down"), 503),
        (HazardProviderResponseError(500, "boom"), 502),
        (InvalidHazardDataError("garbage"), 502),
    ],
)
def test_provider_failures_map_to_gateway_errors(
    settings: Settings, error: Exception, status: int
) -> None:
    app = create_app(settings)
    use_fakes(app, flood=FakeFloodProvider(errors=[error]))

    with TestClient(app) as client:
        response = client.get("/hubs/houston/hazards/flood", params=PARAMS)

    assert response.status_code == status
    assert str(error) not in response.json()["detail"]


@pytest.mark.parametrize("hazard", ["winter", "heat"])
def test_weather_derived_hazards_have_no_dataset_endpoint(client: TestClient, hazard: str) -> None:
    """WINTER/HEAT are scored from weather data; there is no hazard dataset to return."""
    assert client.get(f"/hubs/denver/hazards/{hazard}", params=PARAMS).status_code == 501
