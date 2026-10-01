import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { CapabilityResult, RankingData } from '../core/api.models';
import { hazardsLabel, periodLabel } from '../core/describe';
import { hazardInfo, humanize } from '../core/hazards';
import { ScoreBar } from '../shared/score-bar';
import { HubScoreView } from './hub-score-view';

/** Ranked hubs with score bars, then why the #1 hub scores highest. */
@Component({
  selector: 'app-ranking-view',
  imports: [ScoreBar, HubScoreView],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h3 class="title">{{ title() }}</h3>
    <div class="sub">{{ period() }} · highest exposure first</div>

    <ol class="ranks">
      @for (r of data().rankings; track r.hub_id) {
        <li [class.first]="r.rank === 1">
          <span class="rank">{{ r.rank }}</span>
          <app-score-bar [value]="r.overall_score" [label]="r.hub_name" [color]="barColor()" />
        </li>
      }
    </ol>

    @if (top(); as top) {
      <h4 class="why">Why {{ top.hub_name }} ranks #1</h4>
      <app-hub-score-view [assessment]="top" />
    }
  `,
  styles: `
    .title { font: 600 16px var(--wr-font); margin: 0; color: var(--wr-ink); }
    .sub { font-size: 12px; color: var(--wr-muted); margin: 2px 0 12px; }
    .ranks { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
    li { display: grid; grid-template-columns: 22px 1fr; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 8px; }
    li.first { background: var(--wr-subtle); }
    .rank { font: 700 13px var(--wr-mono); color: var(--wr-muted); text-align: center; }
    .why { font: 600 14px var(--wr-font); margin: 20px 0 10px; color: var(--wr-ink); }
  `,
})
export class RankingView {
  readonly result = input.required<CapabilityResult>();

  protected readonly data = computed(() => this.result().data as RankingData);
  protected readonly top = computed(() => this.data().assessments[0] ?? null);
  protected readonly title = computed(() => {
    const args = this.result().arguments;
    const region = args['region'];
    const scope = region
      ? `${humanize(String(region))} hubs`
      : Array.isArray(args['hub_ids']) ? 'Selected hubs' : 'All hubs';
    return `${scope} by ${hazardsLabel(this.data().hazards)} exposure`;
  });
  protected readonly period = computed(() => {
    const a = this.result().arguments;
    return periodLabel(a['start_date'], a['end_date']);
  });
  protected readonly barColor = computed(() =>
    this.data().hazards.length === 1 ? hazardInfo(this.data().hazards[0]).color : 'var(--wr-brand)',
  );
}
