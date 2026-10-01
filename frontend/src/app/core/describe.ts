/** Plain-language descriptions of what the agent did, and suggested follow-up questions. */

import { ActionRecord, CapabilityResult } from './api.models';
import { HAZARD_ORDER, hazardInfo, humanize } from './hazards';

export type HubNames = Record<string, string>;

export function hubName(id: unknown, names: HubNames): string {
  const key = String(id ?? '');
  return names[key] ?? humanize(key);
}

export function periodLabel(start: unknown, end: unknown): string {
  const s = String(start ?? '');
  const e = String(end ?? '');
  if (!s || !e) return '';
  if (s.slice(0, 4) === e.slice(0, 4) && s.endsWith('-01-01') && e.endsWith('-12-31')) {
    return s.slice(0, 4);
  }
  return `${s} → ${e}`;
}

export function hazardsLabel(hazards: unknown): string {
  const list = Array.isArray(hazards) ? hazards.map(String) : [];
  if (list.length === 0 || list.length === HAZARD_ORDER.length) return 'all hazards';
  return joinWords(list.map((h) => hazardInfo(h).label.toLowerCase()));
}

export function joinWords(items: string[]): string {
  if (items.length <= 1) return items[0] ?? '';
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;
}

/** e.g. "Ranked Midwest hubs by winter exposure (2025)". */
export function describeAction(action: Pick<ActionRecord, 'capability' | 'arguments'>, names: HubNames): string {
  const a = action.arguments ?? {};
  const period = periodLabel(a['start_date'], a['end_date']);
  const when = period ? ` (${period})` : '';
  const hub = hubName(a['hub_id'], names);

  switch (action.capability) {
    case 'list_hubs':
      return a['region'] ? `Looked up ${humanize(String(a['region']))} hubs` : 'Looked up all hubs';
    case 'get_weather_metrics':
      return `Calculated weather statistics for ${hub}${when}`;
    case 'get_hazard_data':
      return `Fetched ${hazardInfo(String(a['hazard'])).label.toLowerCase()} data for ${hub}${when}`;
    case 'analyze_hub_risk':
      return `Scored ${hub} for ${hazardsLabel(a['hazards'])}${when}`;
    case 'rank_hubs': {
      const scope = a['region']
        ? `${humanize(String(a['region']))} hubs`
        : Array.isArray(a['hub_ids'])
          ? joinWords((a['hub_ids'] as unknown[]).map((id) => hubName(id, names)))
          : 'all hubs';
      return `Ranked ${scope} by ${hazardsLabel(a['hazards'])} exposure${when}`;
    }
    case 'compare_hubs': {
      const hubs = Array.isArray(a['hub_ids']) ? (a['hub_ids'] as unknown[]).map((id) => hubName(id, names)) : [];
      return `Compared ${joinWords(hubs)} for ${hazardsLabel(a['hazards'])}${when}`;
    }
    default:
      return humanize(action.capability);
  }
}

const FOLLOW_UP_TOPIC: Record<string, string> = {
  winter: 'winter disruption',
  flood: 'flooding',
  hurricane: 'hurricanes',
  heat: 'heat',
};

function whatAbout(hazard: string): string {
  return `What about ${FOLLOW_UP_TOPIC[hazard] ?? hazard}?`;
}

export const STARTER_QUESTIONS = [
  'Which hubs in the Midwest are most exposed to winter disruption?',
  'Compare Miami and Houston in terms of hurricane and flood exposure.',
  'What percentage of days in Denver last year had snowfall?',
  "Why is the Dallas hub's weather disruption risk high?",
];

/** Up to three natural next questions, based on what the last answer covered. */
export function suggestFollowUps(results: CapabilityResult[], names: HubNames): string[] {
  const last = results[results.length - 1];
  if (!last) return [];
  const a = last.arguments ?? {};
  const chosen = Array.isArray(a['hazards']) ? (a['hazards'] as string[]) : [];
  const missing = HAZARD_ORDER.filter((h) => !chosen.includes(h));
  const hub = hubName(a['hub_id'], names);

  switch (last.capability) {
    case 'rank_hubs':
      return [
        ...((last.data['rankings']?.length ?? 0) >= 2 ? ['Why is the first one higher?'] : []),
        ...(chosen.length ? missing.slice(0, 1).map(whatAbout) : []),
        'Which hub should we prioritize for investment?',
      ];
    case 'compare_hubs':
      return [
        ...(chosen.length ? missing.slice(0, 2).map(whatAbout) : []),
        'Which of them should we prioritize?',
      ].slice(0, 3);
    case 'analyze_hub_risk':
      return [`What drives ${hub}'s highest hazard score?`, `How does ${hub} rank against the other hubs?`];
    case 'get_weather_metrics':
      return [`How many hot days did ${hub} have?`, `Analyze ${hub}'s winter risk`];
    case 'get_hazard_data':
      return [`What is ${hub}'s overall risk score?`];
    default:
      return [];
  }
}
