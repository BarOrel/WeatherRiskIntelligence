import { CapabilityResult, ChatResponse, Conversation, HubAssessment, SessionSummary } from '../core/api.models';

export const NAMES = { minneapolis: 'Minneapolis', chicago: 'Chicago', miami: 'Miami', houston: 'Houston', denver: 'Denver' };

const winter = (score: number, contribution: number) => ({
  hazard: 'winter' as const,
  score,
  weight_in_overall: 1,
  contribution_to_overall: score,
  factors: [
    { name: 'snowfall_frequency', description: 'Share of days with snowfall', raw_value: 9.86, unit: 'percent',
      scale: [0, 15] as [number, number], normalized_score: 65.73, weight: 0.4, contribution },
    { name: 'cold_exposure', description: 'Very cold days', raw_value: 12.6, unit: 'percent',
      scale: [0, 15] as [number, number], normalized_score: 84, weight: 0.2, contribution: 16.8 },
  ],
  assumptions: ['Based on modelled daily weather.'],
  warnings: [],
});

export function assessment(id: string, name: string, score: number): HubAssessment {
  return {
    hub_id: id, hub_name: name, region: 'midwest', period: { start: '2025-01-01', end: '2025-12-31' },
    overall_score: score, hazards: [winter(score, 26.3)],
    assumptions: ['Scores (0-100) express RELATIVE exposure.'], warnings: [],
  };
}

export const RANKING: CapabilityResult = {
  capability: 'rank_hubs',
  arguments: { region: 'midwest', hazards: ['winter'], start_date: '2025-01-01', end_date: '2025-12-31' },
  data: {
    hazards: ['winter'],
    applied_weights: { winter: 1 },
    rankings: [
      { rank: 1, hub_id: 'minneapolis', hub_name: 'Minneapolis', overall_score: 59.53, hazard_scores: { winter: 59.53 } },
      { rank: 2, hub_id: 'chicago', hub_name: 'Chicago', overall_score: 45.17, hazard_scores: { winter: 45.17 } },
    ],
    assessments: [assessment('minneapolis', 'Minneapolis', 59.53), assessment('chicago', 'Chicago', 45.17)],
  },
  warnings: [],
};

export const COMPARISON: CapabilityResult = {
  capability: 'compare_hubs',
  arguments: { hub_ids: ['miami', 'houston'], hazards: ['flood', 'hurricane'], start_date: '2025-01-01', end_date: '2025-12-31' },
  data: {
    hub_ids: ['miami', 'houston'],
    highest_overall_hub_id: 'houston',
    overall_scores: { miami: 36.5, houston: 43.08 },
    overall_differences: [{ hub_id: 'miami', other_hub_id: 'houston', difference: -6.58 }],
    hazard_comparisons: [
      { hazard: 'flood', scores: { miami: 23.04, houston: 45.08 }, highest_hub_id: 'houston', lowest_hub_id: 'miami', spread: 22.03 },
      { hazard: 'hurricane', scores: { miami: 47.71, houston: 41.41 }, highest_hub_id: 'miami', lowest_hub_id: 'houston', spread: 6.29 },
    ],
    assessments: [assessment('miami', 'Miami', 36.5), assessment('houston', 'Houston', 43.08)],
  },
  warnings: ['NHC best-track data only covers storms through 2025-10-29.'],
};

export const WEATHER: CapabilityResult = {
  capability: 'get_weather_metrics',
  arguments: { hub_id: 'denver', start_date: '2025-01-01', end_date: '2025-12-31' },
  data: {
    hub_id: 'denver', period: { start: '2025-01-01', end: '2025-12-31', days: 365 }, days_with_missing_values: 0,
    thresholds: { snowfall_day_cm: 0.25, very_cold_day_min_temperature_c: -15, hot_day_c: 32, extreme_heat_day_c: 38, heavy_precipitation_mm: 25 },
    snowfall_days: 31, snowfall_day_percentage: 8.49, total_snowfall_cm: 57.54, max_daily_snowfall_cm: 7.35,
    very_cold_days: 10, min_temperature_c: -25.6, hot_days: 49, hot_day_percentage: 13.42, extreme_heat_days: 2,
    max_temperature_c: 38.7, heavy_precipitation_days: 0, total_precipitation_mm: 430, max_daily_precipitation_mm: 23.7,
    max_wind_gust_kmh: 76.7,
  },
  warnings: [],
};

export function chatResponse(overrides: Partial<ChatResponse> = {}): ChatResponse {
  return {
    session_id: 'session-1',
    answer: '**Minneapolis** ranks first.',
    actions_performed: [{ capability: 'rank_hubs', arguments: RANKING.arguments, status: 'success', duration_ms: 502, error: null }],
    warnings: [],
    results: [RANKING],
    ...overrides,
  };
}

export const SESSION: SessionSummary = {
  session_id: 'session-1',
  title: 'Which Midwest hubs are most exposed to winter?',
  created_at: '2026-10-01T12:00:00Z',
  updated_at: '2026-10-01T12:05:00Z',
  turn_count: 2,
};

export const CONVERSATION: Conversation = {
  session_id: 'session-1',
  turns: [
    {
      turn_id: 't1',
      question: 'Which Midwest hubs are most exposed to winter?',
      asked_at: '2026-10-01T12:00:00Z',
      answer: 'Minneapolis ranks first.',
      answered_at: '2026-10-01T12:00:05Z',
      ...pick(chatResponse()),
    },
    {
      turn_id: 't2',
      question: 'Why?',
      asked_at: '2026-10-01T12:05:00Z',
      answer: '**Minneapolis** ranks first.',
      answered_at: '2026-10-01T12:05:04Z',
      ...pick(chatResponse()),
    },
  ],
};

function pick(response: ChatResponse) {
  return { actions_performed: response.actions_performed, warnings: response.warnings, results: response.results };
}
