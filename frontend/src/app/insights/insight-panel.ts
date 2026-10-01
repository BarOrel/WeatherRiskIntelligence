import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { CapabilityResult, HubAssessment } from '../core/api.models';
import { ChatMessage } from '../core/chat-store';
import { ComparisonView } from './comparison-view';
import { HazardDataView } from './hazard-data-view';
import { HowScoresWork } from './how-scores-work';
import { HubListView } from './hub-list-view';
import { HubScoreView } from './hub-score-view';
import { RankingView } from './ranking-view';
import { SourcesCaveats } from './sources-caveats';
import { WeatherFactsView } from './weather-facts-view';

/** The evidence behind the selected answer: one tailored view per result, then sources. */
@Component({
  selector: 'app-insight-panel',
  imports: [
    ComparisonView,
    HazardDataView,
    HowScoresWork,
    HubListView,
    HubScoreView,
    RankingView,
    SourcesCaveats,
    WeatherFactsView,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="eyebrow">{{ results().length ? 'Evidence for this answer' : 'Getting started' }}</div>
    @if (results().length) {
      @for (r of results(); track $index) {
        <section class="card">
          @switch (r.capability) {
            @case ('rank_hubs') { <app-ranking-view [result]="r" /> }
            @case ('compare_hubs') { <app-comparison-view [result]="r" [names]="names()" /> }
            @case ('analyze_hub_risk') { <app-hub-score-view [assessment]="asAssessment(r)" /> }
            @case ('get_weather_metrics') { <app-weather-facts-view [result]="r" [names]="names()" /> }
            @case ('get_hazard_data') { <app-hazard-data-view [result]="r" [names]="names()" /> }
            @case ('list_hubs') { <app-hub-list-view [result]="r" /> }
          }
        </section>
      }
      <app-sources-caveats [results]="results()" />
    } @else {
      <section class="card"><app-how-scores-work /></section>
    }
  `,
  styles: `
    :host { display: block; }
    .eyebrow { font: 600 11px var(--wr-font); text-transform: uppercase; letter-spacing: .06em; color: var(--wr-muted); margin-bottom: 8px; }
    .card { background: #fff; border: 1px solid var(--wr-line); border-radius: 12px; padding: 16px; margin-bottom: 12px; }
  `,
})
export class InsightPanel {
  readonly message = input<ChatMessage | null>(null);
  readonly names = input<Record<string, string>>({});

  /** Results to visualize; the hub list is shown only when it was the whole answer. */
  protected readonly results = computed<CapabilityResult[]>(() => {
    const all = this.message()?.results ?? [];
    const substantive = all.filter((r) => r.capability !== 'list_hubs');
    return substantive.length ? substantive : all;
  });

  protected asAssessment(result: CapabilityResult): HubAssessment {
    return result.data as HubAssessment;
  }
}
