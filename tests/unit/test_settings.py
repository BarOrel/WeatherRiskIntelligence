import pytest
from pydantic import ValidationError

from weather_risk.container import build_container
from weather_risk.domain.errors import DomainValidationError
from weather_risk.domain.models import HazardType
from weather_risk.infrastructure.config import Settings


def test_defaults_point_at_seed_hubs_file() -> None:
    settings = Settings(_env_file=None)

    assert settings.hubs_file.name == "hubs.json"
    assert settings.hubs_file.exists()


def test_weather_and_cache_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.cache.ttl_seconds == 1800
    assert settings.weather.base_url == "https://archive-api.open-meteo.com"
    assert settings.weather.timeout_seconds > 0


def test_nested_values_are_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WRI_CACHE__TTL_SECONDS", "42")
    monkeypatch.setenv("WRI_CACHE__MAX_ENTRIES", "7")
    monkeypatch.setenv("WRI_WEATHER__BASE_URL", "http://localhost:9999")
    monkeypatch.setenv("WRI_WEATHER__TIMEOUT_SECONDS", "2.5")
    monkeypatch.setenv("WRI_WEATHER__MAX_RETRIES", "0")
    monkeypatch.setenv("WRI_LLM__MAX_RETRIES", "5")
    monkeypatch.setenv("WRI_RISK__HAZARD_WEIGHTS", '{"winter": 1, "flood": 0, "hurricane": 0, "heat": 1}')
    monkeypatch.setenv("WRI_RISK__WINTER__FACTOR_WEIGHTS", '{"snowfall_frequency": 1, "snowfall_severity": 1, "cold_exposure": 0}')
    monkeypatch.setenv("WRI_METRICS__SNOWFALL_DAY_CM", "1.0")
    monkeypatch.setenv("WRI_LOG_LEVEL", "debug")

    settings = Settings(_env_file=None)

    assert settings.cache.ttl_seconds == 42
    assert settings.cache.max_entries == 7
    assert settings.weather.base_url == "http://localhost:9999"
    assert settings.weather.timeout_seconds == 2.5
    assert settings.weather.max_retries == 0
    assert settings.llm.max_retries == 5
    assert settings.risk.hazard_weights[HazardType.WINTER] == 1
    assert settings.risk.winter.factor_weights["cold_exposure"] == 0
    assert settings.metrics.snowfall_day_cm == 1.0
    assert settings.log_level == "DEBUG"


def test_hazard_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.hazard.cache_ttl_seconds > 0
    assert settings.flood.base_url == "https://flood-api.open-meteo.com"
    assert all(url.startswith("https://www.nhc.noaa.gov/") for url in settings.hurricane.dataset_urls)
    assert settings.hurricane.search_radius_km == 200.0


def test_hazard_values_are_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WRI_HAZARD__CACHE_TTL_SECONDS", "60")
    monkeypatch.setenv("WRI_FLOOD__BASE_URL", "http://flood.local")
    monkeypatch.setenv("WRI_FLOOD__TIMEOUT_SECONDS", "3")
    monkeypatch.setenv("WRI_HURRICANE__SEARCH_RADIUS_KM", "150")
    monkeypatch.setenv("WRI_HURRICANE__DATASET_URLS", '["http://nhc.local/a.txt"]')

    settings = Settings(_env_file=None)

    assert settings.hazard.cache_ttl_seconds == 60
    assert settings.flood.base_url == "http://flood.local"
    assert settings.flood.timeout_seconds == 3
    assert settings.hurricane.search_radius_km == 150
    assert settings.hurricane.dataset_urls == ["http://nhc.local/a.txt"]


def test_risk_defaults() -> None:
    risk = Settings(_env_file=None).risk

    assert risk.hazard_weights == {
        HazardType.WINTER: 0.25,
        HazardType.FLOOD: 0.25,
        HazardType.HURRICANE: 0.30,
        HazardType.HEAT: 0.20,
    }
    assert risk.winter.factor_weights == {
        "snowfall_frequency": 0.4,
        "snowfall_severity": 0.4,
        "cold_exposure": 0.2,
    }


@pytest.mark.parametrize(
    "risk",
    [
        {"hazard_weights": {"winter": -1, "flood": 1, "hurricane": 1, "heat": 1}},
        {"hazard_weights": {"winter": 0, "flood": 0, "hurricane": 0, "heat": 0}},
        {"hazard_weights": {"winter": 1}},
        {"winter": {"factor_weights": {"snowfall_frequency": 1}}},
        {"heat": {"factor_weights": {"hot_day_frequency": 1, "extreme_heat_frequency": 1, "peak_temperature": 1, "typo": 1}}},
    ],
    ids=["negative", "all-zero", "missing-hazard", "missing-factor", "unknown-factor"],
)
def test_invalid_risk_weights_fail_at_startup(risk: dict) -> None:
    with pytest.raises(DomainValidationError):
        build_container(Settings(_env_file=None, risk=risk))


def test_unknown_hazard_weight_key_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, risk={"hazard_weights": {"tornado": 1}})


@pytest.mark.parametrize(
    "overrides",
    [
        {"cache": {"ttl_seconds": -1}},
        {"cache": {"max_entries": 0}},
        {"weather": {"timeout_seconds": 0}},
        {"weather": {"max_retries": 10}},
        {"weather": {"retry_backoff_seconds": 60}},
        {"hazard": {"cache_ttl_seconds": -1}},
        {"hurricane": {"search_radius_km": 0}},
        {"hurricane": {"dataset_urls": []}},
        {"flood": {"timeout_seconds": 0}},
        {"log_level": "LOUD"},
        {"llm": {"blank_response_max_retries": -1}},
        {"llm": {"blank_response_max_retries": 6}},
    ],
)
def test_rejects_invalid_operational_values(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)


def test_llm_workspace_header_is_sent_only_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    with_ws = build_container(Settings(_env_file=None, llm={"workspace_id": "wrkspc_123"}))
    without = build_container(Settings(_env_file=None))

    assert with_ws.llm_client is not None and without.llm_client is not None
    assert with_ws.llm_client.default_headers.get("anthropic-workspace-id") == "wrkspc_123"
    assert "anthropic-workspace-id" not in without.llm_client.default_headers


@pytest.mark.parametrize(
    ("provider", "env_key", "client_type", "default_model"),
    [
        ("anthropic", "ANTHROPIC_API_KEY", "AsyncAnthropic", "claude-opus-5-5"),
        ("openai", "OPENAI_API_KEY", "AsyncOpenAI", "gpt-6-luna"),
    ],
)
def test_llm_provider_selection(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    env_key: str,
    client_type: str,
    default_model: str,
) -> None:
    for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv(env_key, "test-key")

    settings = Settings(_env_file=None, llm={"provider": provider})
    container = build_container(settings)

    assert settings.llm.resolved_model == default_model
    assert type(container.llm_client).__name__ == client_type


def test_llm_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WRI_LLM__PROVIDER", "openai")
    monkeypatch.setenv("WRI_LLM__MODEL", "gpt-6.1-sol")

    assert Settings(_env_file=None).llm.resolved_model == "gpt-6.1-sol"


def test_provider_without_its_credentials_is_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "only-anthropic")

    container = build_container(Settings(_env_file=None, llm={"provider": "openai"}))

    assert container.llm_client is None


def test_blank_response_retries_default_and_reach_the_openai_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert Settings(_env_file=None).llm.blank_response_max_retries == 2

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("WRI_LLM__BLANK_RESPONSE_MAX_RETRIES", "4")
    settings = Settings(_env_file=None, llm={"provider": "openai"})
    container = build_container(settings)

    assert settings.llm.blank_response_max_retries == 4
    provider = container.chat_runtime._reasoning._llm  # composition-root wiring check
    assert provider._config.blank_response_max_retries == 4


def test_conversations_default_to_a_sqlite_file_in_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WRI_CONVERSATION__STORE")  # set to memory for every test by conftest
    settings = Settings(_env_file=None)

    assert settings.conversation.store == "sqlite"
    assert settings.conversation.db_file.name == "weather_risk.db"
    assert settings.conversation.db_file.parent.name == "data"
