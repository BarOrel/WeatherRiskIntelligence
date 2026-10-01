import { CapabilityResult, HazardType } from './api.models';
import { HAZARD_ORDER, HAZARDS, WEATHER_SOURCE } from './hazards';

/** Public datasets used by a set of results, in a stable order. */
export function collectSources(results: CapabilityResult[]): string[] {
  const sources: string[] = [];
  const add = (source: string) => {
    if (source && !sources.includes(source)) sources.push(source);
  };
  for (const result of results) {
    switch (result.capability) {
      case 'get_weather_metrics':
        add(WEATHER_SOURCE);
        break;
      case 'get_hazard_data':
        add(String(result.data['source'] ?? ''));
        break;
      case 'analyze_hub_risk':
      case 'rank_hubs':
      case 'compare_hubs':
        for (const hazard of resultHazards(result)) HAZARDS[hazard].sources.forEach(add);
        break;
    }
  }
  return sources;
}

/** Hazards scored in a risk result (all four when none were selected). */
export function resultHazards(result: CapabilityResult): HazardType[] {
  const fromData = result.data['hazards'];
  if (Array.isArray(fromData) && typeof fromData[0] === 'string') return fromData as HazardType[];
  const compared = result.data['hazard_comparisons'];
  if (Array.isArray(compared) && compared.length) {
    return compared.map((c: { hazard: HazardType }) => c.hazard);
  }
  const assessments = result.data['assessments'] ?? (result.data['hazards'] ? [result.data] : []);
  const found = new Set<HazardType>();
  for (const assessment of assessments as { hazards?: { hazard: HazardType }[] }[]) {
    assessment.hazards?.forEach((h) => found.add(h.hazard));
  }
  return found.size ? HAZARD_ORDER.filter((h) => found.has(h)) : [];
}

/** Warnings (always shown) and assumptions (shown on demand), de-duplicated. */
export function collectCaveats(results: CapabilityResult[]): { warnings: string[]; assumptions: string[] } {
  const warnings = new Set<string>();
  const assumptions = new Set<string>();
  const visit = (value: unknown, key = ''): void => {
    if (Array.isArray(value)) {
      if (key === 'warnings') value.forEach((v) => typeof v === 'string' && warnings.add(v));
      else if (key === 'assumptions' || key === 'limitations')
        value.forEach((v) => typeof v === 'string' && assumptions.add(v));
      else value.forEach((v) => visit(v));
    } else if (value && typeof value === 'object') {
      for (const [k, v] of Object.entries(value)) visit(v, k);
    }
  };
  for (const result of results) {
    result.warnings.forEach((w) => warnings.add(w));
    visit(result.data);
  }
  return { warnings: [...warnings], assumptions: [...assumptions].filter((a) => !warnings.has(a)) };
}
