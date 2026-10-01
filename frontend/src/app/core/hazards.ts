import { HazardType } from './api.models';

export interface HazardInfo {
  label: string;
  icon: string; // Material Symbols name
  color: string;
  summary: string;
  sources: string[];
}

export const WEATHER_SOURCE = 'Open-Meteo Historical Weather (ERA5 reanalysis)';
export const FLOOD_SOURCE = 'Open-Meteo Flood API (Copernicus GloFAS river discharge)';
export const HURRICANE_SOURCE = 'NOAA National Hurricane Center (HURDAT2 best tracks)';

export const HAZARDS: Record<HazardType, HazardInfo> = {
  winter: {
    label: 'Winter',
    icon: 'ac_unit',
    color: '#3f8fd2',
    summary: 'Snow days, biggest snowfall day and very cold days (−15 °C or colder).',
    sources: [WEATHER_SOURCE],
  },
  flood: {
    label: 'Flood',
    icon: 'water',
    color: '#0f8b8d',
    summary: 'Heavy rain days, biggest rain day and how far the nearby river surged above normal.',
    sources: [WEATHER_SOURCE, FLOOD_SOURCE],
  },
  hurricane: {
    label: 'Hurricane',
    icon: 'cyclone',
    color: '#7b4fb5',
    summary: 'Tropical storms passing within 200 km, weighted by strength and distance (30-year history).',
    sources: [HURRICANE_SOURCE],
  },
  heat: {
    label: 'Heat',
    icon: 'thermostat',
    color: '#e07b24',
    summary: 'Hot days (32 °C+), extreme heat days (38 °C+) and the peak temperature.',
    sources: [WEATHER_SOURCE],
  },
};

export const HAZARD_ORDER: HazardType[] = ['winter', 'flood', 'hurricane', 'heat'];

export function hazardInfo(hazard: string): HazardInfo {
  return HAZARDS[hazard as HazardType] ?? {
    label: hazard,
    icon: 'help',
    color: '#64748b',
    summary: '',
    sources: [],
  };
}

const FACTOR_LABELS: Record<string, string> = {
  snowfall_frequency: 'Snow days',
  snowfall_severity: 'Biggest snowfall day',
  cold_exposure: 'Very cold days',
  hot_day_frequency: 'Hot days',
  extreme_heat_frequency: 'Extreme heat days',
  peak_temperature: 'Peak temperature',
  heavy_precipitation_frequency: 'Heavy rain days',
  peak_daily_precipitation: 'Biggest rain day',
  river_discharge_peak_ratio: 'River surge vs. normal flow',
  cyclone_frequency: 'Storms passing nearby per year',
  impact_rate: 'Storm impact per year',
  worst_event_impact: 'Worst single storm',
};

export function factorLabel(name: string): string {
  return FACTOR_LABELS[name] ?? humanize(name);
}

export function formatValue(value: number, unit: string): string {
  const rounded = Number.isInteger(value) ? value : Number(value.toFixed(2));
  switch (unit) {
    case 'percent':
      return `${rounded}% of days`;
    case 'ratio':
      return `${rounded}× normal`;
    case 'events/year':
      return `${rounded} per year`;
    case 'impact/year':
      return `${rounded} per year`;
    case 'impact':
      return `${rounded} (0–1)`;
    default:
      return `${rounded} ${unit}`;
  }
}

export function humanize(value: string): string {
  const text = value.replace(/_/g, ' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}
