import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatIcon } from '@angular/material/icon';

import { HazardAssessment, HubAssessment } from '../core/api.models';
import { factorLabel, hazardInfo } from '../core/hazards';
import { periodLabel } from '../core/describe';
import { FactorBreakdown } from '../shared/factor-breakdown';
import { ScoreBar } from '../shared/score-bar';

/** One hub: overall score, each hazard's score and weight, and what drives each hazard. */
@Component({
  selector: 'app-hub-score-view',
  imports: [DecimalPipe, MatExpansionModule, MatIcon, FactorBreakdown, ScoreBar],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @let a = assessment();
    <div class="headline">
      <div>
        <div class="hub">{{ a.hub_name }}</div>
        <div class="sub">{{ hazardCount() }} · {{ period() }}</div>
      </div>
      <div class="overall" [attr.aria-label]="'Overall exposure ' + a.overall_score">
        <span class="num">{{ a.overall_score | number: '1.1-2' }}</span><span class="of">/100</span>
        <div class="cap">overall exposure</div>
      </div>
    </div>

    @if (topDriver(); as d) {
      <div class="driver">
        <mat-icon [style.color]="d.color">{{ d.icon }}</mat-icon>
        <span>Biggest driver: <b>{{ d.hazard }}</b>, mainly {{ d.factor }}</span>
      </div>
    }

    <mat-accordion multi displayMode="flat" class="hazards">
      @for (h of sortedHazards(); track h.hazard) {
        @let info = hazardInfo(h.hazard);
        <mat-expansion-panel>
          <mat-expansion-panel-header>
            <div class="hazard-row">
              <mat-icon [style.color]="info.color">{{ info.icon }}</mat-icon>
              <app-score-bar [value]="h.score" [label]="info.label" [color]="info.color" />
            </div>
          </mat-expansion-panel-header>
          <div class="weight">
            Counts for {{ h.weight_in_overall * 100 | number: '1.0-0' }}% of the overall score
            (+{{ h.contribution_to_overall | number: '1.1-2' }} pts)
          </div>
          <app-factor-breakdown [factors]="h.factors" [color]="info.color" />
        </mat-expansion-panel>
      }
    </mat-accordion>
    <p class="hint">Expand a hazard to see the measurements behind its score.</p>
  `,
  styles: `
    :host { display: block; }
    .headline { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
    .hub { font: 600 18px/1.2 var(--wr-font); color: var(--wr-ink); }
    .sub { font-size: 12px; color: var(--wr-muted); margin-top: 2px; }
    .overall { text-align: right; }
    .num { font: 700 28px/1 var(--wr-mono); color: var(--wr-ink); }
    .of { font-size: 13px; color: var(--wr-muted); }
    .cap { font-size: 11px; color: var(--wr-muted); text-transform: uppercase; letter-spacing: .04em; }
    .driver { display: flex; align-items: center; gap: 8px; margin: 12px 0 4px; padding: 8px 10px;
      background: var(--wr-subtle); border-radius: 8px; font-size: 13px; }
    .hazards { display: block; margin-top: 8px; }
    .hazard-row { display: grid; grid-template-columns: 24px 1fr; align-items: center; gap: 8px; width: 100%; padding-right: 8px; }
    .weight { font-size: 12px; color: var(--wr-muted); margin-bottom: 10px; }
    .hint { font-size: 12px; color: var(--wr-muted); margin: 8px 0 0; }
  `,
})
export class HubScoreView {
  readonly assessment = input.required<HubAssessment>();

  protected readonly hazardInfo = hazardInfo;
  protected readonly period = computed(() =>
    periodLabel(this.assessment().period.start, this.assessment().period.end),
  );
  protected readonly hazardCount = computed(() => {
    const n = this.assessment().hazards.length;
    return n === 4 ? 'All 4 hazards' : n === 1 ? `${hazardInfo(this.assessment().hazards[0].hazard).label} only` : `${n} hazards`;
  });
  protected readonly sortedHazards = computed(() =>
    [...this.assessment().hazards].sort((a, b) => b.contribution_to_overall - a.contribution_to_overall),
  );
  protected readonly topDriver = computed(() => {
    const top: HazardAssessment | undefined = this.sortedHazards()[0];
    const factor = top?.factors.reduce((best, f) => (f.contribution > best.contribution ? f : best), top.factors[0]);
    if (!top || !factor) return null;
    const info = hazardInfo(top.hazard);
    return { hazard: info.label.toLowerCase(), icon: info.icon, color: info.color, factor: factorLabel(factor.name).toLowerCase() };
  });
}
