from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from weather_risk.domain.models import HazardType
from weather_risk.domain.risk import WeatherThresholds
from weather_risk.domain.risk.strategies import flood as flood_strategy
from weather_risk.domain.risk.strategies import heat as heat_strategy
from weather_risk.domain.risk.strategies import hurricane as hurricane_strategy
from weather_risk.domain.risk.strategies import winter as winter_strategy

PROJECT_ROOT = Path(__file__).resolve().parents[4]


class CacheSettings(BaseModel):
    """Weather data caching. A TTL of 0 disables caching."""

    ttl_seconds: int = Field(default=1800, ge=0)
    max_entries: int = Field(default=1024, ge=1)


class WeatherSettings(BaseModel):
    """Historical weather provider (Open-Meteo archive API)."""

    base_url: str = "https://archive-api.open-meteo.com"
    timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    max_retries: int = Field(default=2, ge=0, le=3)
    retry_backoff_seconds: float = Field(default=0.5, ge=0, le=2)
    max_history_days: int = Field(default=366, ge=1)


class HazardSettings(BaseModel):
    """Settings shared by all hazard data providers."""

    cache_ttl_seconds: int = Field(default=21600, ge=0)
    max_history_days: int = Field(default=11000, ge=1)  # ~30 years (hurricane climatology)
    max_retries: int = Field(default=2, ge=0, le=3)
    retry_backoff_seconds: float = Field(default=0.5, ge=0, le=2)


class FloodSettings(BaseModel):
    """Open-Meteo Flood API (GloFAS river discharge)."""

    base_url: str = "https://flood-api.open-meteo.com"
    timeout_seconds: float = Field(default=10.0, gt=0, le=60)


class HurricaneSettings(BaseModel):
    """NOAA NHC HURDAT2 best-track files (Atlantic + Eastern/Central North Pacific).

    NHC republishes these with a new date suffix after each season's review; update the URLs
    (e.g. via ``WRI_HURRICANE__DATASET_URLS='["...", "..."]'``) to pick up newer seasons.
    """

    dataset_urls: list[str] = Field(
        default_factory=lambda: [
            "https://www.nhc.noaa.gov/data/hurdat/hurdat2-1851-2025-092326.txt",
            "https://www.nhc.noaa.gov/data/hurdat/hurdat2-nepac-1949-2025-092926.txt",
        ],
        min_length=1,
    )
    timeout_seconds: float = Field(default=60.0, gt=0, le=300)
    search_radius_km: float = Field(default=200.0, gt=0, le=2000)
    dataset_ttl_seconds: int = Field(default=86400, ge=0)


_THRESHOLDS = WeatherThresholds()  # single source of the default values


class MetricsSettings(BaseModel):
    """What counts as a notable weather day (used by weather statistics and risk strategies)."""

    snowfall_day_cm: float = Field(default=_THRESHOLDS.snowfall_day_cm, gt=0)
    very_cold_day_c: float = _THRESHOLDS.very_cold_day_c
    hot_day_c: float = _THRESHOLDS.hot_day_c
    extreme_heat_day_c: float = _THRESHOLDS.extreme_heat_day_c
    heavy_precipitation_mm: float = Field(default=_THRESHOLDS.heavy_precipitation_mm, gt=0)
    high_wind_gust_kmh: float = Field(default=_THRESHOLDS.high_wind_gust_kmh, gt=0)
    severe_wind_gust_kmh: float = Field(default=_THRESHOLDS.severe_wind_gust_kmh, gt=0)


class StrategySettings(BaseModel):
    """Relative weights of one strategy's factors (>= 0, at least one positive; re-normalized)."""

    factor_weights: dict[str, float]


def _strategy_settings(defaults: dict[str, float]) -> Any:
    return Field(default_factory=lambda: StrategySettings(factor_weights=dict(defaults)))


class RiskSettings(BaseModel):
    """Deterministic risk scoring. Weights are validated when the application starts."""

    max_history_days: int = Field(default=3660, ge=1)
    hurricane_climatology_years: int = Field(default=30, ge=1, le=100)
    max_concurrent_hubs: int = Field(default=2, ge=1, le=10)
    hazard_weights: dict[HazardType, float] = Field(
        default_factory=lambda: {
            HazardType.WINTER: 0.25,
            HazardType.FLOOD: 0.25,
            HazardType.HURRICANE: 0.30,
            HazardType.HEAT: 0.20,
        }
    )
    winter: StrategySettings = _strategy_settings(winter_strategy.DEFAULT_WEIGHTS)
    flood: StrategySettings = _strategy_settings(flood_strategy.DEFAULT_WEIGHTS)
    hurricane: StrategySettings = _strategy_settings(hurricane_strategy.DEFAULT_WEIGHTS)
    heat: StrategySettings = _strategy_settings(heat_strategy.DEFAULT_WEIGHTS)


DEFAULT_LLM_MODELS = {"anthropic": "claude-opus-5-5", "openai": "gpt-6-luna"}


class LLMSettings(BaseModel):
    """Language model provider: "anthropic" (Claude) or "openai".

    ``api_key`` falls back to the provider's own environment variable (ANTHROPIC_API_KEY /
    ANTHROPIC_AUTH_TOKEN, or OPENAI_API_KEY); without any credentials the API still runs and
    /chat returns 503. ``model`` defaults per provider (see DEFAULT_LLM_MODELS).
    ``max_retries`` = structured-output repair attempts (invalid JSON/schema);
    ``transport_max_retries`` = SDK retries for timeouts, 429 and 5xx;
    ``blank_response_max_retries`` = extra requests when a successful response has no text
    (OpenAI). All are retries after the first attempt. Separate concerns.
    """

    provider: Literal["anthropic", "openai"] = "anthropic"
    api_key: SecretStr | None = None
    workspace_id: str | None = None
    """Anthropic only: for API keys not scoped to a workspace (anthropic-workspace-id)."""
    model: str | None = None
    effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    """Anthropic: output_config.effort. OpenAI: reasoning_effort."""
    max_tokens: int = Field(default=16000, ge=256, le=64000)
    timeout_seconds: float = Field(default=120.0, gt=0, le=600)
    transport_max_retries: int = Field(default=2, ge=0, le=5)
    max_retries: int = Field(default=2, ge=0, le=5)
    blank_response_max_retries: int = Field(default=2, ge=0, le=5)
    refusal_fallback: bool = True
    """Anthropic only: server-side refusal fallback."""

    @property
    def resolved_model(self) -> str:
        return self.model or DEFAULT_LLM_MODELS[self.provider]


class AgentSettings(BaseModel):
    """Bounds for the agent's plan -> execute loop."""

    max_iterations: int = Field(default=3, ge=1, le=10)
    max_actions_per_iteration: int = Field(default=4, ge=1, le=10)


class ConversationSettings(BaseModel):
    """Chat history store.

    ``sqlite`` (default) keeps every conversation in ``db_file`` so it survives restarts and
    moves with the file; ``memory`` is process-local (tests, evaluation runs).
    ``max_messages`` bounds the history sent to the LLM (whole turns); ``max_sessions`` bounds
    the memory store only.
    """

    store: Literal["sqlite", "memory"] = "sqlite"
    db_file: Path = PROJECT_ROOT / "data" / "weather_risk.db"
    max_messages: int = Field(default=20, ge=2, le=200)
    max_sessions: int = Field(default=1000, ge=1)


class Settings(BaseSettings):
    """Centralized application settings.

    Values come from (highest priority first): init kwargs, environment
    variables prefixed with ``WRI_``, a ``.env`` file, then the defaults below.
    Nested groups use ``__``, e.g. ``WRI_CACHE__TTL_SECONDS=300``.
    """

    model_config = SettingsConfigDict(
        env_prefix="WRI_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )

    app_name: str = "Weather Risk Intelligence"
    environment: Literal["local", "test", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    hubs_file: Path = PROJECT_ROOT / "data" / "hubs.json"
    frontend_dir: Path = PROJECT_ROOT / "frontend" / "dist" / "weather-risk-ui" / "browser"
    """Built chat UI (``ng build``). Served at ``/`` when present."""

    cache: CacheSettings = Field(default_factory=CacheSettings)
    weather: WeatherSettings = Field(default_factory=WeatherSettings)
    hazard: HazardSettings = Field(default_factory=HazardSettings)
    flood: FloodSettings = Field(default_factory=FloodSettings)
    hurricane: HurricaneSettings = Field(default_factory=HurricaneSettings)
    metrics: MetricsSettings = Field(default_factory=MetricsSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    conversation: ConversationSettings = Field(default_factory=ConversationSettings)

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value


@lru_cache
def get_settings() -> Settings:
    return Settings()
