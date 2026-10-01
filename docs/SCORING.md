# Data sources and risk scoring

What the numbers are, where they come from and how they are computed. Everything here is
deterministic Python (`src/weather_risk/domain/risk/`); the LLM never computes a value.

## Summary of assumptions and uncertainty

- **Exposure, not loss.** Scores (0-100) express *relative* weather/hazard operational exposure
  for comparing hubs over the same period. They are not probabilities of closure or financial
  loss, not actuarial estimates and not official (e.g. FEMA) risk scores. Every answer ends with
  this caveat, and the agent's instructions forbid presenting scores as probabilities.
- **Modelled inputs.** Weather is Open-Meteo reanalysis (modelled, not station readings); river
  discharge is Copernicus GloFAS for the nearest modelled river cell (about 5 km), not a gauge
  and not a site-level flood probability.
- **Thresholds and scales are modelling choices**, documented below with their rationale, and
  calibrated to these six US hubs over 2025. They are configurable without code changes.
- **Coverage gaps are reported, not hidden.** NHC HURDAT2 is published after each season's review;
  when a period extends past `data_coverage_end` a warning is attached to the result and shown to
  the user. Missing weather values drop the affected factor, re-normalize the remaining weights
  and add a warning.
- **Hurricanes use a 30-year climatology** (one place sees a tropical cyclone only every few
  years), stated in every hurricane assessment's assumptions. Other hazards use exactly the
  requested period; periods under a year reflect seasons and get a warning.
- **Not modelled:** ice storms and freezing rain (winter), humidity/heat index (heat), storm surge,
  urban drainage, elevation and flood defences (flood), building vulnerability, asset value,
  insurance and business continuity plans.
- **Scope:** four hazards (winter, flood, hurricane, heat) for six hubs. Other hazards are declined
  explicitly by the agent.
- **Default period:** when the user names none, the last complete calendar year.

## Weather data source

[Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api)
(`/v1/archive`). Requested daily variables: `precipitation_sum`, `rain_sum`, `snowfall_sum`,
`temperature_2m_max`, `temperature_2m_min`, `wind_speed_10m_max`, `wind_gusts_10m_max`, with
`timezone=auto` and explicit units (`celsius`, `kmh`, `mm`; snowfall is then reported in cm).

The adapter rejects responses with the wrong shape, mismatched array lengths, dates that do not
exactly cover the requested range, unexpected units, or values that fail domain validation.

## Hazards

### Weather providers vs. hazard providers

- A **`WeatherProvider`** returns general daily weather observations for a location
  (temperature, precipitation, wind). It is one generic data feed.
- A **hazard provider** returns data about one specific hazard, shaped for that hazard: river
  discharge for floods, storm tracks and closest approach for hurricanes. There is one port per
  hazard (`FloodHazardProvider`, `HurricaneHazardProvider`), not one generic port, because the
  data shapes have nothing in common.

### Architecture

```
            HazardDataService          (application: orchestration only, no scoring)
                    │
                    ▼
             HazardRegistry            HazardType ──► Hazard
            ┌───────┴────────┐
            ▼                ▼
       FloodHazard     HurricaneHazard          (application)
            │                │
            ▼                ▼
  FloodHazardProvider  HurricaneHazardProvider  (application ports)
            ▲                ▲
            │ implements     │ implements
  OpenMeteoFlood…      NoaaHurricane…           (infrastructure, @cached)
            │                │
            ▼                ▼
  Open-Meteo Flood API   NHC HURDAT2 files
```

- **`Hazard`** (`hazard_type`, `get_data(location, date_range)`) is the application's view of a
  kind of hazard. `FloodHazard` and `HurricaneHazard` delegate to their own provider port; they
  contain no HTTP logic. Adding another flood data source means writing a new
  `FloodHazardProvider` and changing one line in `container.py`; `FloodHazard` is untouched.
- **`HazardRegistry`** receives the hazards by constructor injection, maps each `HazardType` to
  exactly one `Hazard`, rejects duplicates, and raises `UnsupportedHazardError` for unregistered
  types. There are no if/elif chains, no reflection and no plugin discovery.
- **`HazardDataService.get_hub_hazard_data(hub_id, hazard_type, start_date, end_date)`**
  resolves the hub, picks the hazard from the registry, validates the date range and returns
  typed `HazardData`.
- Adding a hazard type means adding a `HazardType` value, a data model, a provider port, a
  `Hazard`, an infrastructure provider, one registry entry and one response schema.

### Data sources

| Hazard | Source | Endpoint |
|--------|--------|----------|
| Flood | Open-Meteo Flood API (Copernicus GloFAS v4 river discharge, 1984 onwards) | `https://flood-api.open-meteo.com/v1/flood?latitude=…&longitude=…&daily=river_discharge&start_date=…&end_date=…` |
| Hurricane | NOAA National Hurricane Center HURDAT2 best-track data | `https://www.nhc.noaa.gov/data/hurdat/hurdat2-1851-2025-092326.txt` (Atlantic) and `…/hurdat2-nepac-1949-2025-092926.txt` (NE/Central Pacific) |

**Why HURDAT2.** NOAA offers no public query API for historical hurricane tracks.
- NOAA's own `coast.noaa.gov` hurricane services require a token.
- The public "Historical Hurricane Tracks" ArcGIS layer is hosted by the Esri Federal User
  Community, not by NOAA.

HURDAT2 is NHC's official, machine-readable best-track dataset: 6-hourly position, status,
maximum sustained wind and central pressure for every storm. The provider:
1. Downloads the files.
2. Parses them into domain track points.
3. Caches the parsed dataset.
4. Searches it locally.

**Proximity.** Distance is computed with a Haversine function (`GeoLocation.distance_km`, no
GIS library). Each 6-hour segment is linearly interpolated at about 30-minute steps, so a fast
storm passing between two fixes is still detected. A storm becomes an event when its centre
came within `hurricane.search_radius_km` of the hub at a time inside the requested range. The
event records:
- the closest approach (distance, time, status, wind);
- peak status, Saffir-Simpson category (from peak wind, only if the storm reached hurricane
  status), maximum wind and minimum pressure;
- the full track.

### Caching

Both providers use the generic `@cached` decorator; there are no `Cached…Provider` wrappers. TTLs
come from settings, and failures are never cached.

| Namespace | What is cached | TTL setting |
|-----------|----------------|-------------|
| `hazard:flood:open-meteo:v1` | Flood result per lat/lon/start/end | `hazard.cache_ttl_seconds` |
| `hazard:hurricane:noaa:v1` | Search result per lat/lon/start/end/radius | `hazard.cache_ttl_seconds` |
| `hazard:hurricane:noaa:hurdat2:v1` | Parsed HURDAT2 dataset (~87k track points) | `hurricane.dataset_ttl_seconds` |

The dataset entry means the about 10 MB of HURDAT2 files are downloaded once per TTL, not per
request. Single-flight ensures concurrent first requests trigger a single download.

### Hazard limitations

These are returned in every response's `limitations` list as well.

- **No scoring.** These are exposure signals; nothing here is a risk score or probability.
- **Flood:**
  - Discharge is for the nearest modelled river grid cell (about 5 km), which may not be the
    river closest to the site (see `cell_location`).
  - It ignores urban drainage, rainfall (pluvial) flooding, storm surge, building elevation,
    local topography and infrastructure resilience.
  - Values are modelled, not gauge measurements.
- **Hurricane:**
  - Distance is to the storm centre; wind, rain and surge extend beyond it.
  - Best track is 6-hourly and interpolated in between.
  - Covers the Atlantic and NE/Central Pacific basins only. Times are UTC.
  - NHC publishes HURDAT2 after each season's review, so the most recent season may be missing.
    `data_coverage_end` reports the last covered date, and a limitation is added when the
    requested range goes past it. Point `hurricane.dataset_urls` at newer files as NHC releases
    them.


## Risk scoring (deterministic)

### Weather data, hazard data and risk scores

| Layer | What it is | Example |
|-------|------------|---------|
| Weather data | Observed daily weather (`WeatherHistory`) | 7.35 cm snow on one day |
| Hazard data | Hazard-specific signals (`FloodHazardData`, `HurricaneHazardData`) | Irma passed 151 km away |
| Weather metrics | Deterministic statistics (`WeatherMetrics`); no judgement | 8.49 % of 2025 days had snowfall |
| Risk scores | Our exposure model on top of the above (`OverallRiskAssessment`) | Denver winter = 36.1 |

**What 0–100 means.** Scores express **relative weather/hazard operational exposure**, for
comparing hubs over the same period. They are **not** a probability of hub closure or financial
loss, not actuarial risk, and not an official (e.g. FEMA National Risk Index) score. The scores
are authoritative and deterministic. The LLM only *explains* them, never produces them.

### Flow

```
WeatherProvider ─► WeatherHistory ─► WeatherMetricsCalculator ─► WeatherMetrics ──┐
HazardDataService ─► FloodHazardData / HurricaneHazardData ───────────────────────┤
                                                                                  ▼
                                                                    RiskAssessmentContext
                      ┌──────────────────┬──────────────────┬──────────────────┤
                WinterStrategy     FloodStrategy    HurricaneStrategy     HeatStrategy
                      └──────────────────┴────────┬─────────┴──────────────────┘
                                                  ▼
                                RiskScoringEngine (configured hazard weights)
                                                  ▼
                                       OverallRiskAssessment
                                         ┌────────┴────────┐
                                   rank_assessments  compare_assessments
```

- **`RiskStrategy`** (Strategy pattern) scores ONE hazard, 0–100, from 2–3 factors. It declares
  which data it needs (`requires_weather`, `required_hazard_data`). It never knows its hazard's
  weight in the overall score.
- **`RiskScoringEngine`** gets the strategies and the hazard weights through constructor
  injection. It runs only the selected strategies, then combines their scores. There are no
  if/elif chains.
- **Use cases** (`application/use_cases/`) are the entry points: `AnalyzeHubRiskHandler`,
  `RankHubsHandler` and `CompareHubsHandler`. Each takes a request object and has one
  `execute` method; use cases never call each other.
- **`HubRiskAssessor`** (`application/risk/`) is the shared orchestration they all use:
  - it validates the period and the hazard selection;
  - it asks the engine what data the selection needs and fetches only that, so a winter-only
    analysis never calls the flood or hurricane providers and a hurricane-only analysis fetches
    no weather;
  - for several hubs it runs concurrently, capped by `risk.max_concurrent_hubs` so Open-Meteo
    rate limits aren't hit.
- **Ranking and comparison** consume existing `OverallRiskAssessment` objects. They never
  re-score.
  - Ranking sorts by overall score descending, then hub id ascending.
  - Comparison returns pairwise differences, overall and per hazard.

### Formulas

Every factor is `normalize_linear(raw, low, high)`: 0 at or below `low`, 100 at or above `high`,
linear in between. A hazard score is `Σ weight_i × normalized_i`, with factor weights normalized
to sum to 1. A factor with no data is dropped, the remaining weights are re-normalized, and a
warning is added. The overall score is `Σ hazard_weight_h × score_h`, with hazard weights
re-normalized over the selected hazards.

| Hazard | Data | Factor (raw value) | Scale low → high | Weight |
|--------|------|--------------------|------------------|--------|
| Winter | weather | `snowfall_frequency`: % of days with snowfall ≥ snow-day threshold | 0 → 15 % | 0.40 |
| | | `snowfall_severity`: largest daily snowfall | 0 → 30 cm | 0.40 |
| | | `cold_exposure`: % of days with Tmin ≤ very-cold threshold | 0 → 15 % | 0.20 |
| Heat | weather | `hot_day_frequency`: % of days with Tmax ≥ hot threshold | 0 → 35 % | 0.40 |
| | | `extreme_heat_frequency`: % of days with Tmax ≥ extreme threshold | 0 → 5 % | 0.30 |
| | | `peak_temperature`: highest Tmax | 30 → 43 °C | 0.30 |
| Flood | weather + GloFAS | `heavy_precipitation_frequency`: % of days with precipitation ≥ heavy threshold | 0 → 6 % | 0.35 |
| | | `peak_daily_precipitation`: largest daily precipitation | 25 → 150 mm | 0.25 |
| | | `river_discharge_peak_ratio`: peak ÷ max(median, 1 m³/s) of the period | 1 → 50 | 0.40 |
| Hurricane | NOAA HURDAT2 | `cyclone_frequency`: storms within the search radius per year | 0 → 1.5 | 0.30 |
| | | `impact_rate`: Σ event impact per year | 0 → 0.5 | 0.40 |
| | | `worst_event_impact`: max event impact | 0 → 1 | 0.30 |

**Hurricane event impact** = intensity × proximity, a value from 0 to 1.

| Wind at closest approach | Intensity | | Centre distance | Proximity |
|---|---|---|---|---|
| ≥ 178 km/h (Cat 3+, major) | 1.0 | | ≤ 50 km | 1.0 |
| 119–177 km/h (Cat 1–2) | 0.6 | | ≤ 100 km | 0.6 |
| 63–118 km/h (tropical storm) | 0.3 | | ≤ search radius | 0.3 |
| < 63 km/h or unknown | 0.1 | | | |

So a tropical depression passing over the hub scores 0.1, while a Category 4 storm within 50 km
scores 1.0. The wind bands are the Saffir-Simpson thresholds. The impact weights and proximity
bands are my modelling choices.

**Hurricane climatology window.** A single place sees a tropical cyclone only every few years,
so hurricane exposure is measured over the `risk.hurricane_climatology_years` (default 30)
ending at the requested end date. This is stated in the assessment's assumptions. Other hazards
use exactly the requested period.

**Overall hazard weights** (configurable): winter 0.25, flood 0.25, hurricane 0.30, heat 0.20.

### Thresholds

These are operational choices for an explainable model. They are not official standards unless
stated otherwise.

| Threshold | Default | Rationale |
|-----------|---------|-----------|
| Snowfall day | ≥ 0.25 cm | NWS "measurable snowfall" is 0.1 in (0.254 cm) |
| Very cold day | Tmin ≤ −15 °C | Sustained cold that affects equipment, vehicles and staff |
| Hot day | Tmax ≥ 32 °C | ≈ 90 °F, the "hot day" count used in NOAA climate normals |
| Extreme heat day | Tmax ≥ 38 °C | ≈ 100 °F |
| Heavy precipitation day | ≥ 25 mm | ≈ 1 inch per day |
| High wind day | gust ≥ 72 km/h | ≈ 45 mph, typical NWS Wind Advisory gust (metrics only) |
| Severe wind day | gust ≥ 93 km/h | 58 mph, the NWS severe-thunderstorm wind criterion (metrics only) |
| Hurricane / major wind | ≥ 119 / ≥ 178 km/h | Saffir-Simpson Category 1 / 3 (official) |
| Discharge | relative to the period's own median | So rivers of very different sizes are comparable |

The normalization scales were calibrated against 2025 data for the six hubs, so that no factor
sits at 0 or 100 for most hubs.

### Worked example: Denver winter, 2025 (reproducible)

`GET /hubs/denver/risk?start_date=2025-01-01&end_date=2025-12-31&hazards=winter`

| Factor | Raw (from `WeatherMetrics`) | Normalized | × weight | = contribution |
|--------|-----------------------------|-----------|----------|----------------|
| snowfall_frequency | 31 of 365 days = 8.49 % | 8.49 / 15 × 100 = 56.62 | × 0.40 | 22.65 |
| snowfall_severity | max day 7.35 cm | 7.35 / 30 × 100 = 24.50 | × 0.40 | 9.80 |
| cold_exposure | 10 of 365 days = 2.74 % | 2.74 / 15 × 100 = 18.26 | × 0.20 | 3.65 |
| **Winter score** | | | | **36.10** |

Winter is the only hazard selected, so its weight is re-normalized to 1.0 and the overall
score is 36.10. In a full analysis, this winter score contributes 0.25 × 36.10 = 9.03 to the
overall score.

### Results with real data (2025)

| Query | Result |
|-------|--------|
| Denver snowfall days, 2025 | 31 / 365 = **8.49 %** (≥ 0.25 cm) |
| Midwest winter ranking | 1. Minneapolis 59.53 · 2. Chicago 45.17 |
| Miami vs Houston: hurricane | Miami 47.71 vs Houston 41.41 (+6.29) |
| Miami vs Houston: flood | Miami 23.04 vs Houston 45.08 (−22.03) |
| Dallas overall | **37.49**: flood 73.54 (×0.25), heat 67.19 (×0.20), winter 12.94 (×0.25), hurricane 8.09 (×0.30) |

### Scoring limitations

- **Exposure, not loss.** These are relative exposure scores. Nothing models vulnerability,
  asset value, insurance or the probability of an outcome.
- **Scale and period.**
  - Normalization scales are calibrated to these six US hubs, not to global extremes.
  - "Max" factors grow with longer periods, so compare hubs over the same period (ranking and
    comparison always do).
  - Periods under a year reflect seasons; a warning is added.
- **Hazard-specific limits:**
  - Flood: the river ratio is a GloFAS signal for the nearest modelled river cell, and
    snowmelt-fed rivers peak every spring.
  - Winter: no ice storms. Heat: no humidity.
  - Hurricane: no storm surge.
- **Hurricane recency.** HURDAT2 is published after each season's review, so the latest storms
  can be missing; a warning is added.
