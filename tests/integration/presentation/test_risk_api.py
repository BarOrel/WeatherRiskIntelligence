from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from support.fakes import FakeWeatherProvider
from support.use_cases import Fixture, make_fixture

from weather_risk.application.use_cases import GetWeatherMetricsHandler
from weather_risk.application.weather import WeatherService
from weather_risk.domain.risk import WeatherMetricsCalculator, WeatherThresholds
from weather_risk.infrastructure.config import Settings
from weather_risk.presentation.api import create_app
from weather_risk.presentation.api.dependencies import (
    get_analyze_hub_risk,
    get_compare_hubs,
    get_rank_hubs,
    get_weather_metrics,
)

DATES = {"start_date": "2025-01-01", "end_date": "2025-12-31"}


@pytest.fixture
def fx() -> Fixture:
    return make_fixture()


@pytest.fixture
def client(seed_hubs_file: Path, fx: Fixture) -> Iterator[TestClient]:
    app = create_app(Settings(environment="test", hubs_file=seed_hubs_file, _env_file=None))
    app.dependency_overrides[get_analyze_hub_risk] = lambda: fx.analyze
    app.dependency_overrides[get_rank_hubs] = lambda: fx.rank
    app.dependency_overrides[get_compare_hubs] = lambda: fx.compare
    metrics = GetWeatherMetricsHandler(
        WeatherService(app.state.container.hub_repository, FakeWeatherProvider(), 366),
        WeatherMetricsCalculator(WeatherThresholds()),
    )
    app.dependency_overrides[get_weather_metrics] = lambda: metrics
    with TestClient(app) as client:
        yield client


class TestHubRisk:
    def test_full_assessment_with_evidence(self, client: TestClient) -> None:
        response = client.get("/hubs/denver/risk", params=DATES | {"hazards": ["winter", "heat"]})

        assert response.status_code == 200
        body = response.json()
        assert body["hub_id"] == "denver"
        assert [h["hazard_type"] for h in body["hazards"]] == ["winter", "heat"]
        assert sum(h["weight_in_overall"] for h in body["hazards"]) == pytest.approx(1.0)
        assert body["overall_score"] == pytest.approx(
            sum(h["contribution_to_overall"] for h in body["hazards"]), abs=0.02
        )
        factor = body["hazards"][0]["factors"][0]
        assert set(factor) == {
            "name",
            "description",
            "raw_value",
            "unit",
            "scale_low",
            "scale_high",
            "normalized_score",
            "weight",
            "contribution",
        }
        assert any("not probabilities" in a for a in body["assumptions"])

    def test_default_is_all_hazards(self, client: TestClient) -> None:
        body = client.get("/hubs/denver/risk", params=DATES).json()

        assert [h["hazard_type"] for h in body["hazards"]] == [
            "winter",
            "flood",
            "hurricane",
            "heat",
        ]

    def test_winter_only_fetches_no_hazard_data(self, client: TestClient, fx: Fixture) -> None:
        client.get("/hubs/denver/risk", params=DATES | {"hazards": "winter"})

        assert fx.flood.calls == fx.hurricane.calls == []

    @pytest.mark.parametrize(
        ("path", "params", "status"),
        [
            ("/hubs/atlantis/risk", DATES, 404),
            ("/hubs/denver/risk", DATES | {"hazards": "tornado"}, 422),
            ("/hubs/denver/risk", {"start_date": "2025-12-31", "end_date": "2025-01-01"}, 422),
            ("/hubs/denver/risk", {"start_date": "2025-01-01"}, 422),
        ],
    )
    def test_errors(self, client: TestClient, path: str, params: dict, status: int) -> None:
        assert client.get(path, params=params).status_code == status


class TestRanking:
    def test_region_winter_ranking(self, client: TestClient) -> None:
        response = client.get("/risk/rank", params=DATES | {"region": "midwest", "hazards": "winter"})

        assert response.status_code == 200
        body = response.json()
        assert body["region"] == "midwest"
        assert body["hazards"] == ["winter"]
        assert body["applied_weights"] == {"winter": 1.0}
        assert [r["rank"] for r in body["rankings"]] == [1, 2]
        assert {r["hub_id"] for r in body["rankings"]} == {"chicago", "minneapolis"}
        assert set(body["rankings"][0]["hazard_scores"]) == {"winter"}

    def test_explicit_hubs(self, client: TestClient) -> None:
        body = client.get("/risk/rank", params=DATES | {"hubs": ["miami", " Denver "]}).json()

        assert {r["hub_id"] for r in body["rankings"]} == {"miami", "denver"}

    def test_invalid_region(self, client: TestClient) -> None:
        assert client.get("/risk/rank", params=DATES | {"region": "atlantis"}).status_code == 422


class TestComparison:
    def test_compare_two_hubs(self, client: TestClient) -> None:
        response = client.get(
            "/risk/compare", params=DATES | {"hubs": ["miami", "denver"], "hazards": ["hurricane", "flood"]}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["hub_ids"] == ["miami", "denver"]
        assert [c["hazard_type"] for c in body["hazard_comparisons"]] == ["flood", "hurricane"]
        [diff] = body["overall_differences"]
        assert diff["difference"] == pytest.approx(
            body["overall_scores"]["miami"] - body["overall_scores"]["denver"], abs=0.02
        )
        assert len(body["assessments"]) == 2

    @pytest.mark.parametrize("hubs", [["miami"], ["miami", "miami"]])
    def test_needs_two_distinct_hubs(self, client: TestClient, hubs: list[str]) -> None:
        assert client.get("/risk/compare", params=DATES | {"hubs": hubs}).status_code == 422


class TestWeatherMetrics:
    def test_snowfall_percentage_and_thresholds(self, client: TestClient) -> None:
        response = client.get(
            "/hubs/denver/weather/metrics",
            params={"start_date": "2024-01-01", "end_date": "2024-01-10"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["days"] == 10
        # Fake weather: 0 cm snowfall every day, Tmax 12.5, gust 45 km/h.
        assert body["snowfall_days"] == 0
        assert body["snowfall_day_percentage"] == 0.0
        assert body["max_temperature_c"] == 12.5
        assert body["thresholds"]["snowfall_day_cm"] == 0.25
        assert "score" not in body
