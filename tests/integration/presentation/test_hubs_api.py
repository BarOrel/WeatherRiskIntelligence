"""Smoke tests that the composition root wires settings -> repository -> service -> HTTP."""

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weather_risk.infrastructure.config import Settings
from weather_risk.presentation.api import create_app


@pytest.fixture
def client(seed_hubs_file: Path) -> Iterator[TestClient]:
    settings = Settings(environment="test", hubs_file=seed_hubs_file, _env_file=None)
    with TestClient(create_app(settings)) as client:
        yield client


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_list_hubs(client: TestClient) -> None:
    response = client.get("/hubs")

    assert response.status_code == 200
    assert len(response.json()) == 6


def test_list_hubs_filtered_by_region(client: TestClient) -> None:
    response = client.get("/hubs", params={"region": "midwest"})

    assert [hub["id"] for hub in response.json()] == ["chicago", "minneapolis"]


def test_get_hub(client: TestClient) -> None:
    response = client.get("/hubs/denver")

    assert response.status_code == 200
    assert response.json() == {
        "id": "denver",
        "name": "Denver",
        "state": "CO",
        "region": "west",
        "location": {"latitude": 39.7392, "longitude": -104.9903},
    }


def test_get_unknown_hub_returns_404(client: TestClient) -> None:
    assert client.get("/hubs/atlantis").status_code == 404


def test_unknown_region_returns_422(client: TestClient) -> None:
    assert client.get("/hubs", params={"region": "atlantis"}).status_code == 422


def test_hub_list_is_never_cached_by_the_browser(client: TestClient) -> None:
    assert client.get("/hubs").headers["cache-control"] == "no-store"
    assert client.get("/hubs/denver").headers["cache-control"] == "no-store"


def test_hub_list_reflects_edits_to_the_json_file(tmp_path: Path, seed_hubs_file: Path) -> None:
    hubs_file = tmp_path / "hubs.json"
    hubs_file.write_text(seed_hubs_file.read_text(encoding="utf-8"), encoding="utf-8")
    settings = Settings(environment="test", hubs_file=hubs_file, _env_file=None)

    with TestClient(create_app(settings)) as client:
        assert len(client.get("/hubs").json()) == 6

        payload = json.loads(hubs_file.read_text(encoding="utf-8"))
        payload["hubs"].append(
            {
                "id": "atlanta",
                "name": "Atlanta",
                "state": "GA",
                "region": "south",
                "location": {"latitude": 33.749, "longitude": -84.388},
            }
        )
        hubs_file.write_text(json.dumps(payload), encoding="utf-8")
        stat = hubs_file.stat()
        os.utime(hubs_file, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))

        hubs = client.get("/hubs").json()
        assert len(hubs) == 7
        assert client.get("/hubs/atlanta").json()["name"] == "Atlanta"
