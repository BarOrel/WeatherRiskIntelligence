import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { MatIcon } from '@angular/material/icon';

import { CapabilityResult } from '../core/api.models';
import { hubName, periodLabel } from '../core/describe';

interface Tile {
  icon: string;
  value: string;
  label: string;
  detail: string;
  color: string;
}

/** Factual weather statistics as KPI tiles, with the thresholds that define each count. */
@Component({
  selector: 'app-weather-facts-view',
  imports: [DecimalPipe, MatIcon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h3 class="title">Weather facts · {{ hub() }}</h3>
    <div class="sub">{{ period() }} · {{ d()['period']?.days }} days of observations</div>

    <div class="tiles">
      @for (t of tiles(); track t.label) {
        <div class="tile">
          <mat-icon [style.color]="t.color">{{ t.icon }}</mat-icon>
          <div class="value">{{ t.value }}</div>
          <div class="label">{{ t.label }}</div>
          <div class="detail">{{ t.detail }}</div>
        </div>
      }
    </div>

    <div class="extremes">
      <span>Max temperature <b>{{ d()['max_temperature_c'] | number: '1.0-2' }} °C</b></span>
      <span>Min temperature <b>{{ d()['min_temperature_c'] | number: '1.0-2' }} °C</b></span>
      <span>Total precipitation <b>{{ d()['total_precipitation_mm'] | number: '1.0-0' }} mm</b></span>
      <span>Strongest gust <b>{{ d()['max_wind_gust_kmh'] | number: '1.0-1' }} km/h</b></span>
    </div>
  `,
  styles: `
    .title { font: 600 16px var(--wr-font); margin: 0; color: var(--wr-ink); }
    .sub { font-size: 12px; color: var(--wr-muted); margin: 2px 0 12px; }
    .tiles { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
    .tile { border: 1px solid var(--wr-line); border-radius: 10px; padding: 10px 12px; background: #fff; }
    .tile mat-icon { font-size: 20px; width: 20px; height: 20px; }
    .value { font: 700 22px/1.2 var(--wr-mono); color: var(--wr-ink); margin-top: 4px; }
    .label { font-size: 13px; color: var(--wr-text); }
    .detail { font-size: 11px; color: var(--wr-muted); margin-top: 2px; }
    .extremes { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 12px; margin-top: 14px; font-size: 12px; color: var(--wr-muted); }
    .extremes b { color: var(--wr-text); font-weight: 600; }
  `,
})
export class WeatherFactsView {
  readonly result = input.required<CapabilityResult>();
  readonly names = input<Record<string, string>>({});

  protected readonly d = computed(() => this.result().data);
  protected readonly hub = computed(() => hubName(this.d()['hub_id'], this.names()));
  protected readonly period = computed(() => periodLabel(this.d()['period']?.start, this.d()['period']?.end));

  protected readonly tiles = computed<Tile[]>(() => {
    const d = this.d();
    const t = d['thresholds'] ?? {};
    const days = d['period']?.days ?? 0;
    return [
      {
        icon: 'ac_unit', color: '#3f8fd2',
        value: `${d['snowfall_day_percentage']}%`,
        label: 'Days with snowfall',
        detail: `${d['snowfall_days']} of ${days} days · ≥ ${t['snowfall_day_cm']} cm · max ${d['max_daily_snowfall_cm']} cm/day`,
      },
      {
        icon: 'severe_cold', color: '#3f8fd2',
        value: `${d['very_cold_days']}`,
        label: 'Very cold days',
        detail: `of ${days} days · min ≤ ${t['very_cold_day_min_temperature_c']} °C · low ${d['min_temperature_c']} °C`,
      },
      {
        icon: 'thermostat', color: '#e07b24',
        value: `${d['hot_day_percentage']}%`,
        label: 'Hot days',
        detail: `${d['hot_days']} days ≥ ${t['hot_day_c']} °C · ${d['extreme_heat_days']} days ≥ ${t['extreme_heat_day_c']} °C`,
      },
      {
        icon: 'rainy', color: '#0f8b8d',
        value: `${d['heavy_precipitation_days']}`,
        label: 'Heavy rain days',
        detail: `≥ ${t['heavy_precipitation_mm']} mm/day · max ${d['max_daily_precipitation_mm']} mm`,
      },
    ];
  });
}
