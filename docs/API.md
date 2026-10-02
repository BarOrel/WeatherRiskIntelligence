# HTTP API

Interactive documentation (Swagger UI) is served at `/docs` when the API runs.

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Liveness |
| `GET /hubs?region=<region>` | List hubs, optionally by region |
| `GET /hubs/{hub_id}` | One hub |
| `GET /hubs/{hub_id}/weather/history?start_date=…&end_date=…` | Daily historical weather |
| `GET /hubs/{hub_id}/hazards/{flood\|hurricane}?start_date=…&end_date=…` | Hazard data (no scoring) |
| `GET /hubs/{hub_id}/weather/metrics?start_date=…&end_date=…` | Factual weather statistics (e.g. % of snowfall days) |
| `GET /hubs/{hub_id}/risk?start_date=…&end_date=…&hazards=winter&hazards=flood` | Risk assessment with full evidence |
| `GET /risk/rank?start_date=…&end_date=…&region=midwest&hazards=winter` | Rank hubs (optional `region`, repeated `hubs`) |
| `GET /risk/compare?hubs=miami&hubs=houston&start_date=…&end_date=…&hazards=hurricane&hazards=flood` | Compare hubs |
| `POST /chat` `{"message": "…", "session_id"?: "…", "turn_id"?: "…"}` | Conversational agent (needs an LLM API key; see [Chat](#chat)) |

Dates are `YYYY-MM-DD`. List parameters are repeated, not comma-separated: `hazards` takes any of
`winter`, `flood`, `hurricane`, `heat` (omit it for all four), and `hubs` takes hub ids.

## Weather example

```bash
curl "http://127.0.0.1:8000/hubs/denver/weather/history?start_date=2024-01-10&end_date=2024-01-14"
```

```json
{
  "hub_id": "denver",
  "location": { "latitude": 39.7392, "longitude": -104.9903 },
  "timezone": "America/Denver",
  "start_date": "2024-01-10",
  "end_date": "2024-01-14",
  "days": [
    {
      "date": "2024-01-13",
      "precipitation_mm": 4.6, "rain_mm": 0.0, "snowfall_cm": 3.22,
      "temperature_max_c": -10.7, "temperature_min_c": -23.7,
      "wind_speed_max_kmh": 19.5, "wind_gust_max_kmh": 33.5
    }
  ]
}
```

Weather dates are local to the hub's `timezone`. Any value may be `null` when the provider has
no measurement for that day.

## Hazard examples (real responses, abridged)

Houston during Hurricane Harvey:

```bash
curl "http://127.0.0.1:8000/hubs/houston/hazards/flood?start_date=2017-08-24&end_date=2017-09-03"
```

```json
{
  "hazard_type": "flood",
  "hub_id": "houston",
  "location": { "latitude": 29.7604, "longitude": -95.3698 },
  "cell_location": { "latitude": 29.775002, "longitude": -95.37499 },
  "start_date": "2017-08-24", "end_date": "2017-09-03",
  "source": { "name": "Open-Meteo Flood API (Copernicus GloFAS river discharge)", "url": "…" },
  "limitations": ["River discharge is a flood-exposure signal, not a flood probability or risk score.", "…"],
  "days": [
    { "date": "2017-08-24", "discharge_m3s": 13.55 },
    { "date": "2017-08-29", "discharge_m3s": 695.63 }
  ]
}
```

Tropical cyclones that passed within 200 km of Miami, 2015–2024 (11 events):

```bash
curl "http://127.0.0.1:8000/hubs/miami/hazards/hurricane?start_date=2015-01-01&end_date=2024-12-31"
```

```json
{
  "hazard_type": "hurricane",
  "hub_id": "miami",
  "search_radius_km": 200.0,
  "data_coverage_end": "2025-10-29",
  "source": { "name": "NOAA National Hurricane Center HURDAT2 best-track data", "url": "https://www.nhc.noaa.gov/data/#hurdat" },
  "events": [
    {
      "storm_id": "AL112017", "name": "IRMA",
      "start_date": "2017-08-30", "end_date": "2017-09-13",
      "closest_approach_km": 151.0,
      "closest_approach_time": "2017-09-10T18:52:30Z",
      "classification_at_closest_approach": "hurricane",
      "wind_at_closest_approach_kmh": 185.2,
      "peak_classification": "hurricane", "peak_category": 5,
      "max_wind_kmh": 287.1, "min_pressure_hpa": 914.0,
      "track": [{ "time": "2017-08-30T00:00:00Z", "latitude": 16.1, "longitude": -26.9, "classification": "tropical_depression", "wind_kmh": 55.6, "pressure_hpa": 1008.0 }, "…"]
    }
  ],
  "limitations": ["…"]
}
```

## Errors

Every error uses one format, [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) problem details
(`Content-Type: application/problem+json`). Branch on `code`, not on the text:

```json
{"type": "about:blank", "title": "Not Found", "status": 404,
 "detail": "Unknown hub 'atlantis'", "code": "hub_not_found"}
```

Validation errors add `errors`: a list of `{loc, msg, type}` (the submitted value is never echoed).
Upstream and unexpected failures return a generic `detail`; the cause is logged on the server.

| Status | `code` | Meaning |
|---|---|---|
| 404 | `hub_not_found`, `session_not_found`, `not_found` | Unknown hub, unknown saved conversation, unknown route |
| 405 | `method_not_allowed` | Wrong HTTP method |
| 422 | `validation_error` | Malformed or missing parameters (dates, unknown hazard or region, missing `hubs`) |
| 422 | `invalid_date_range` | `start_date > end_date`, future dates, range too long |
| 422 | `invalid_risk_request` | Fewer than two distinct hubs to compare, selection with zero configured weight |
| 501 | `hazard_data_unsupported` | No hazard dataset for that type (`winter` and `heat` are derived from weather) |
| 502 | `weather_provider_bad_response`, `weather_provider_invalid_data`, `hazard_provider_bad_response`, `hazard_provider_invalid_data` | A data provider returned an unexpected status or invalid data |
| 503 | `weather_provider_unavailable`, `hazard_provider_unavailable` | A data provider is unreachable |
| 504 | `weather_provider_timeout`, `hazard_provider_timeout` | A data provider timed out |
| 502 | `llm_bad_response`, `llm_invalid_plan` | The LLM refused, returned no text after retries, or no valid plan after repairs |
| 503 | `llm_unavailable` | No LLM configured, credentials rejected, rate limited or out of quota |
| 504 | `llm_timeout` | The LLM timed out |
| 500 | `internal_error` | Unexpected server error |

Every route documents its possible errors in Swagger UI (`/docs`).

## Chat

`POST /chat` runs one conversational turn.

| Field | Type | Notes |
|---|---|---|
| `message` | string, 1-4000 chars | The user's question |
| `session_id` | string, optional | Continue a conversation; omit to start one (the response returns it) |
| `turn_id` | string, optional | Client id for this question. Send the same id when retrying it, so the server replaces that turn instead of duplicating it |

Response:

| Field | Notes |
|---|---|
| `session_id` | Use it for follow-up questions |
| `answer` | Plain-language answer written by the LLM from the deterministic results |
| `actions_performed` | Safe trace: capability, arguments, status, `duration_ms`, error. No model reasoning |
| `warnings` | Collected from the capability results (e.g. NHC data coverage), not written by the LLM |
| `results` | Each successful capability's structured output (`capability`, `arguments`, `data`, `warnings`), so a client never parses numbers from prose |

Example:

```bash
curl -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" \
  -d '{"message": "Compare Miami and Houston for hurricane exposure"}'
# -> {"session_id": "4f…", "answer": "…", "actions_performed": [{"capability": "compare_hubs", …}], "warnings": […]}

curl -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" \
  -d '{"session_id": "4f…", "message": "What about flooding?"}'
```

### Saved conversations

| Endpoint | Description |
|---|---|
| `GET /chat/sessions?limit=50` | Saved conversations, most recently active first: `session_id`, `title` (first question), `created_at`, `updated_at`, `turn_count` |
| `GET /chat/sessions/{session_id}` | The whole conversation: each turn's `turn_id`, `question`, `asked_at`, `answer`, `answered_at`, `actions_performed`, `warnings`, `results` (same fields as a `/chat` response). 404 if unknown |

Both are sent with `Cache-Control: no-store`.

Chat errors use the same format (see [Errors](#errors)): `llm_unavailable` (503), `llm_timeout`
(504), `llm_bad_response` / `llm_invalid_plan` (502).
