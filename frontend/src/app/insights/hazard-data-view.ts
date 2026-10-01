import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { MatIcon } from '@angular/material/icon';

import { CapabilityResult } from '../core/api.models';
import { hubName, periodLabel } from '../core/describe';
import { hazardInfo, humanize } from '../core/hazards';

/** Raw hazard signals (no score): river discharge statistics or the storms that passed nearby. */
@Component({
  selector: 'app-hazard-data-view',
  imports: [DecimalPipe, MatIcon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @let info = hazardInfo(d()['hazard']);
    <h3 class="title"><mat-icon [style.color]="info.color">{{ info.icon }}</mat-icon> {{ info.label }} data · {{ hub() }}</h3>
    <div class="sub">{{ period() }}</div>

    @if (d()['hazard'] === 'flood') {
      <div class="stats">
        <div><span>Peak river flow</span><b>{{ d()['max_discharge_m3s'] | number: '1.0-2' }} m³/s</b></div>
        <div><span>Typical (median) flow</span><b>{{ d()['median_discharge_m3s'] | number: '1.0-2' }} m³/s</b></div>
        <div><span>Peak vs. typical</span><b>{{ d()['peak_to_median_ratio'] | number: '1.0-2' }}×</b></div>
        <div><span>Days with data</span><b>{{ d()['observed_days'] }}</b></div>
      </div>
    } @else {
      <div class="stats">
        <div><span>Storms within {{ d()['search_radius_km'] }} km</span><b>{{ d()['event_count'] }}</b></div>
        <div><span>Data available through</span><b>{{ d()['data_coverage_end'] }}</b></div>
      </div>
      @if (events().length) {
        <table class="events">
          <thead><tr><th>Storm</th><th>Closest</th><th>Strength there</th><th>Peak</th></tr></thead>
          <tbody>
            @for (e of events(); track e.storm_id) {
              <tr>
                <td>{{ e.name }} <span class="muted">{{ e.start_date.slice(0, 4) }}</span></td>
                <td>{{ e.closest_approach_km | number: '1.0-0' }} km</td>
                <td>{{ classification(e.classification_at_closest_approach) }}</td>
                <td>{{ e.peak_saffir_simpson_category ? 'Cat ' + e.peak_saffir_simpson_category : classification(e.peak_classification) }}</td>
              </tr>
            }
          </tbody>
        </table>
      } @else {
        <p class="muted">No tropical storms passed within the search radius in this period.</p>
      }
    }
  `,
  styles: `
    .title { display: flex; align-items: center; gap: 6px; font: 600 16px var(--wr-font); margin: 0; color: var(--wr-ink); }
    .sub { font-size: 12px; color: var(--wr-muted); margin: 2px 0 12px; }
    .stats { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .stats div { border: 1px solid var(--wr-line); border-radius: 10px; padding: 10px 12px; display: grid; gap: 4px; }
    .stats span { font-size: 12px; color: var(--wr-muted); }
    .stats b { font: 700 18px var(--wr-mono); color: var(--wr-ink); }
    .events { width: 100%; border-collapse: collapse; margin-top: 14px; font-size: 12px; }
    .events th { text-align: left; color: var(--wr-muted); font-weight: 500; padding: 6px 4px; border-bottom: 1px solid var(--wr-line); }
    .events td { padding: 6px 4px; border-bottom: 1px solid var(--wr-line); }
    .muted { color: var(--wr-muted); font-size: 12px; }
  `,
})
export class HazardDataView {
  readonly result = input.required<CapabilityResult>();
  readonly names = input<Record<string, string>>({});

  protected readonly hazardInfo = hazardInfo;
  protected readonly d = computed(() => this.result().data);
  protected readonly hub = computed(() => hubName(this.d()['hub_id'], this.names()));
  protected readonly period = computed(() => periodLabel(this.d()['period']?.start, this.d()['period']?.end));
  protected readonly events = computed(() => (this.d()['events'] ?? []) as any[]);
  protected classification(value: string): string {
    return humanize(value ?? '');
  }
}
