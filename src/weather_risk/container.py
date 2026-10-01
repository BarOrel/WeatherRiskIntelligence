"""Composition root: the single place where concrete implementations are wired."""

import os
from dataclasses import dataclass
from typing import Any

import anthropic
import httpx
import openai

from weather_risk.agents.core import (
    Agent,
    ChatRuntime,
    ConversationRepository,
    LlmProvider,
    ReasoningEngine,
    StructuredLlmClient,
)
from weather_risk.agents.weather_risk import WeatherRiskAgent, build_capabilities

from weather_risk.application.hazards import (
    FloodHazard,
    HazardDataService,
    HazardRegistry,
    HurricaneHazard,
)
from weather_risk.application.hubs import HubService
from weather_risk.application.ports import WeatherProvider
from weather_risk.application.risk import HubRiskAssessor
from weather_risk.application.use_cases import (
    AnalyzeHubRiskHandler,
    CompareHubsHandler,
    GetWeatherMetricsHandler,
    RankHubsHandler,
)
from weather_risk.application.weather import WeatherService
from weather_risk.domain.models import WeatherHistory
from weather_risk.domain.repositories import HubRepository
from weather_risk.domain.risk import (
    FloodRiskStrategy,
    HeatRiskStrategy,
    HurricaneRiskStrategy,
    RiskScoringEngine,
    WeatherMetricsCalculator,
    WeatherThresholds,
    WinterRiskStrategy,
)
from weather_risk.infrastructure.cache import InMemoryTTLCache
from weather_risk.infrastructure.config import Settings
from weather_risk.infrastructure.conversation import (
    InMemoryConversationRepository,
    SqliteConversationRepository,
)
from weather_risk.infrastructure.hazards.flood import (
    OpenMeteoFloodConfig,
    OpenMeteoFloodHazardProvider,
)
from weather_risk.infrastructure.hazards.hurricane import (
    NoaaHurricaneConfig,
    NoaaHurricaneHazardProvider,
)
from weather_risk.infrastructure.http import RetryPolicy
from weather_risk.infrastructure.llm import (
    AnthropicConfig,
    AnthropicLlmProvider,
    OpenAiConfig,
    OpenAiLlmProvider,
    UnconfiguredLlmProvider,
)
from weather_risk.infrastructure.persistence import JsonHubRepository
from weather_risk.infrastructure.weather import OpenMeteoConfig, OpenMeteoWeatherProvider


@dataclass(frozen=True)
class Container:
    settings: Settings
    hub_repository: HubRepository
    hub_service: HubService
    weather_provider: WeatherProvider
    weather_service: WeatherService
    hazard_data_service: HazardDataService
    analyze_hub_risk: AnalyzeHubRiskHandler
    rank_hubs: RankHubsHandler
    compare_hubs: CompareHubsHandler
    get_weather_metrics: GetWeatherMetricsHandler
    agent: Agent
    chat_runtime: ChatRuntime
    http_client: httpx.AsyncClient
    llm_client: anthropic.AsyncAnthropic | openai.AsyncOpenAI | None = None

    async def aclose(self) -> None:
        await self.http_client.aclose()
        if self.llm_client is not None:
            await self.llm_client.close()


def build_container(
    settings: Settings,
    http_client: httpx.AsyncClient | None = None,
    llm_provider: LlmProvider | None = None,
) -> Container:
    """Build the object graph. ``http_client`` and ``llm_provider`` may be injected (e.g. a mock
    transport or scripted LLM in tests); the container owns and closes what it creates."""
    http_client = http_client or httpx.AsyncClient()
    hub_repository = JsonHubRepository(settings.hubs_file)

    weather_provider = OpenMeteoWeatherProvider(
        client=http_client,
        cache=InMemoryTTLCache[WeatherHistory](max_entries=settings.cache.max_entries),
        config=OpenMeteoConfig(
            base_url=settings.weather.base_url,
            timeout_seconds=settings.weather.timeout_seconds,
            retry_policy=RetryPolicy(
                max_retries=settings.weather.max_retries,
                backoff_seconds=settings.weather.retry_backoff_seconds,
            ),
            cache_ttl_seconds=settings.cache.ttl_seconds,
        ),
    )

    metrics_calculator = WeatherMetricsCalculator(
        WeatherThresholds(**settings.metrics.model_dump())
    )
    hazard_data_service = _build_hazard_data_service(settings, http_client, hub_repository)
    hub_service = HubService(hub_repository)
    weather_service = WeatherService(
        hub_repository=hub_repository,
        weather_provider=weather_provider,
        max_history_days=settings.weather.max_history_days,
    )
    assessor = HubRiskAssessor(
        weather_provider=weather_provider,
        hazard_data_service=hazard_data_service,
        engine=_build_risk_engine(settings),
        metrics_calculator=metrics_calculator,
        max_history_days=settings.risk.max_history_days,
        hurricane_climatology_years=settings.risk.hurricane_climatology_years,
        max_concurrent_hubs=settings.risk.max_concurrent_hubs,
    )
    analyze_hub_risk = AnalyzeHubRiskHandler(hub_service, assessor)
    rank_hubs = RankHubsHandler(hub_service, assessor)
    compare_hubs = CompareHubsHandler(hub_service, assessor)
    get_weather_metrics = GetWeatherMetricsHandler(weather_service, metrics_calculator)

    llm_client = None
    if llm_provider is None:
        llm_provider, llm_client = _build_llm(settings)
    agent = WeatherRiskAgent(
        capabilities=build_capabilities(
            hub_service=hub_service,
            hazard_data_service=hazard_data_service,
            get_weather_metrics=get_weather_metrics,
            analyze_hub_risk=analyze_hub_risk,
            rank_hubs=rank_hubs,
            compare_hubs=compare_hubs,
        ),
        max_actions_per_plan=settings.agent.max_actions_per_iteration,
    )
    chat_runtime = ChatRuntime(
        agent=agent,
        reasoning=ReasoningEngine(
            StructuredLlmClient(llm_provider, max_repair_attempts=settings.llm.max_retries),
            llm_provider,
        ),
        conversations=_build_conversations(settings),
        max_iterations=settings.agent.max_iterations,
    )

    return Container(
        settings=settings,
        hub_repository=hub_repository,
        hub_service=hub_service,
        weather_provider=weather_provider,
        weather_service=weather_service,
        hazard_data_service=hazard_data_service,
        analyze_hub_risk=analyze_hub_risk,
        rank_hubs=rank_hubs,
        compare_hubs=compare_hubs,
        get_weather_metrics=get_weather_metrics,
        agent=agent,
        chat_runtime=chat_runtime,
        http_client=http_client,
        llm_client=llm_client,
    )


LlmClient = anthropic.AsyncAnthropic | openai.AsyncOpenAI

# Environment variables each SDK reads by itself when no explicit key is configured.
_PROVIDER_ENV_KEYS = {
    "anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"),
    "openai": ("OPENAI_API_KEY",),
}


def _build_llm(settings: Settings) -> tuple[LlmProvider, LlmClient | None]:
    llm = settings.llm
    api_key = llm.api_key.get_secret_value() if llm.api_key else None
    has_env_credentials = any(os.environ.get(k) for k in _PROVIDER_ENV_KEYS[llm.provider])
    if api_key is None and not has_env_credentials:
        return UnconfiguredLlmProvider(), None

    if llm.provider == "openai":
        openai_client = openai.AsyncOpenAI(
            api_key=api_key,  # None -> the SDK reads OPENAI_API_KEY
            timeout=llm.timeout_seconds,
            max_retries=llm.transport_max_retries,
        )
        openai_provider = OpenAiLlmProvider(
            openai_client,
            OpenAiConfig(
                model=llm.resolved_model,
                max_tokens=llm.max_tokens,
                reasoning_effort=llm.effort,
                blank_response_max_retries=llm.blank_response_max_retries,
            ),
        )
        return openai_provider, openai_client

    client = anthropic.AsyncAnthropic(
        api_key=api_key,  # None -> the SDK reads ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN
        timeout=llm.timeout_seconds,
        max_retries=llm.transport_max_retries,
        default_headers=(
            {"anthropic-workspace-id": llm.workspace_id} if llm.workspace_id else None
        ),
    )
    provider = AnthropicLlmProvider(
        client,
        AnthropicConfig(
            model=llm.resolved_model,
            max_tokens=llm.max_tokens,
            effort=llm.effort,
            refusal_fallback=llm.refusal_fallback,
        ),
    )
    return provider, client


def _build_conversations(settings: Settings) -> ConversationRepository:
    conversation = settings.conversation
    if conversation.store == "sqlite":
        return SqliteConversationRepository(conversation.db_file, conversation.max_messages)
    return InMemoryConversationRepository(conversation.max_messages, conversation.max_sessions)


def _build_risk_engine(settings: Settings) -> RiskScoringEngine:
    risk = settings.risk
    return RiskScoringEngine(
        strategies=[
            WinterRiskStrategy(risk.winter.factor_weights),
            FloodRiskStrategy(risk.flood.factor_weights),
            HurricaneRiskStrategy(risk.hurricane.factor_weights),
            HeatRiskStrategy(risk.heat.factor_weights),
        ],
        hazard_weights=risk.hazard_weights,
    )


def _build_hazard_data_service(
    settings: Settings, http_client: httpx.AsyncClient, hub_repository: HubRepository
) -> HazardDataService:
    # One cache for all hazard providers; their namespaces keep entries apart.
    hazard_cache = InMemoryTTLCache[Any](max_entries=settings.cache.max_entries)
    retry_policy = RetryPolicy(
        max_retries=settings.hazard.max_retries,
        backoff_seconds=settings.hazard.retry_backoff_seconds,
    )

    flood_provider = OpenMeteoFloodHazardProvider(
        client=http_client,
        cache=hazard_cache,
        config=OpenMeteoFloodConfig(
            base_url=settings.flood.base_url,
            timeout_seconds=settings.flood.timeout_seconds,
            retry_policy=retry_policy,
            cache_ttl_seconds=settings.hazard.cache_ttl_seconds,
        ),
    )
    hurricane_provider = NoaaHurricaneHazardProvider(
        client=http_client,
        cache=hazard_cache,
        config=NoaaHurricaneConfig(
            dataset_urls=tuple(settings.hurricane.dataset_urls),
            timeout_seconds=settings.hurricane.timeout_seconds,
            retry_policy=retry_policy,
            search_radius_km=settings.hurricane.search_radius_km,
            cache_ttl_seconds=settings.hazard.cache_ttl_seconds,
            dataset_ttl_seconds=settings.hurricane.dataset_ttl_seconds,
        ),
    )

    return HazardDataService(
        hub_repository=hub_repository,
        registry=HazardRegistry([FloodHazard(flood_provider), HurricaneHazard(hurricane_provider)]),
        max_history_days=settings.hazard.max_history_days,
    )
