# Configuration

All settings live in `Settings` (`infrastructure/config/settings.py`) and can be overridden
with `WRI_`-prefixed environment variables or a `.env` file (see `.env.example`). Nested groups
use `__`, for example `WRI_HURRICANE__SEARCH_RADIUS_KM=150`.

| Setting                          | Default                              | Notes |
|----------------------------------|--------------------------------------|-------|
| `log_level`                      | `INFO`                               | |
| `hubs_file`                      | `data/hubs.json`                     | Re-read automatically when the file changes |
| `cache.ttl_seconds`              | `1800`                               | Weather cache TTL; 0 disables |
| `cache.max_entries`              | `1024`                               | Per cache instance |
| `weather.base_url`               | `https://archive-api.open-meteo.com` | |
| `weather.timeout_seconds`        | `10.0`                               | |
| `weather.max_retries`            | `2`                                  | |
| `weather.retry_backoff_seconds`  | `0.5`                                | |
| `weather.max_history_days`       | `366`                                | |
| `hazard.cache_ttl_seconds`       | `21600`                              | Flood and hurricane search results |
| `hazard.max_history_days`        | `11000`                              | ~30 years (hurricane climatology) |
| `hazard.max_retries`             | `2`                                  | |
| `hazard.retry_backoff_seconds`   | `0.5`                                | |
| `flood.base_url`                 | `https://flood-api.open-meteo.com`   | |
| `flood.timeout_seconds`          | `10.0`                               | |
| `hurricane.dataset_urls`         | NHC Atlantic + NE Pacific HURDAT2    | JSON list in env |
| `hurricane.timeout_seconds`      | `60.0`                               | Files are several MB |
| `hurricane.search_radius_km`     | `200.0`                              | |
| `hurricane.dataset_ttl_seconds`  | `86400`                              | Parsed dataset |
| `metrics.snowfall_day_cm`        | `0.25`                               | See Thresholds |
| `metrics.very_cold_day_c`        | `-15`                                | |
| `metrics.hot_day_c` / `extreme_heat_day_c` | `32` / `38`                | |
| `metrics.heavy_precipitation_mm` | `25`                                 | |
| `metrics.high_wind_gust_kmh` / `severe_wind_gust_kmh` | `72` / `93`     | |
| `risk.hazard_weights`            | winter .25, flood .25, hurricane .30, heat .20 | JSON in env; re-normalized |
| `risk.winter.factor_weights`     | frequency .4, severity .4, cold .2   | Same for `flood`, `hurricane`, `heat` |
| `risk.max_history_days`          | `3660`                               | |
| `risk.hurricane_climatology_years` | `30`                               | |
| `risk.max_concurrent_hubs`       | `2`                                  | Protects Open-Meteo rate limits |
| `llm.provider`                   | `anthropic`                          | `anthropic` or `openai` (this project was developed and evaluated with `openai`) |
| `llm.api_key`                    | unset                                | Secret. Falls back to `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`; without any key `/chat` returns 503 |
| `llm.workspace_id`               | unset                                | Anthropic only, for keys not scoped to a workspace |
| `llm.model`                      | provider default                     | `claude-opus-5-5` (anthropic) / `gpt-6-luna` (openai) |
| `llm.effort`                     | `medium`                             | Anthropic `effort` / OpenAI `reasoning_effort` |
| `llm.max_tokens` / `llm.timeout_seconds` | `16000` / `120`              | |
| `llm.transport_max_retries`      | `2`                                  | SDK retries: timeouts, 429, 5xx |
| `llm.blank_response_max_retries` | `2`                                  | OpenAI: extra requests when a successful response has no text |
| `llm.max_retries`                | `2`                                  | Structured-output repair attempts (invalid JSON / schema) |
| `llm.refusal_fallback`           | `true`                               | Anthropic server-side refusal fallback |
| `agent.max_iterations`           | `3`                                  | Planning rounds per turn |
| `agent.max_actions_per_iteration`| `4`                                  | |
| `conversation.store`             | `sqlite`                             | `sqlite` (saved in `db_file`) or `memory` (process-local; tests and eval runs) |
| `conversation.db_file`           | `data/weather_risk.db`               | Created on first run |
| `conversation.max_messages`      | `20`                                 | Per session, kept as whole turns (10 question/answer pairs) |
| `conversation.max_sessions`      | `1000`                               | `memory` store only (LRU eviction) |

Weights must be ≥ 0 with at least one positive, and must name exactly the hazards/factors that
exist. Invalid weights stop the application at startup.

All retry settings count retries after the first attempt (2 = at most 3 attempts).
