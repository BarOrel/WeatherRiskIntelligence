import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { MatIcon } from '@angular/material/icon';

import { CapabilityResult, ComparisonData } from '../core/api.models';
import { hubName, periodLabel } from '../core/describe';
import { hazardInfo } from '../core/hazards';
import { ScoreBar } from '../shared/score-bar';
import { FactorBreakdown } from '../shared/factor-breakdown';

/** Hubs side by side: each hazard's score per hub, the overall scores and the difference. */
@Component({
  selector: 'app-comparison-view',
  imports: [DecimalPipe, MatIcon, ScoreBar, FactorBreakdown],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h3 class="title">{{ hubsTitle() }}</h3>
    <div class="sub">{{ period() }}</div>

    @for (c of data().hazard_comparisons; track c.hazard) {
      @let info = hazardInfo(c.hazard);
      <section class="hazard">
        <div class="hazard-head">
          <mat-icon [style.color]="info.color">{{ info.icon }}</mat-icon>
          <span>{{ info.label }}</span>
          <span class="leader">{{ name(c.highest_hub_id) }} higher by {{ c.spread | number: '1.1-2' }}</span>
        </div>
        @for (id of data().hub_ids; track id) {
          <app-score-bar [value]="c.scores[id]" [label]="name(id)" [color]="info.color" />
        }
      </section>
    }

    @if (data().hazard_comparisons.length > 1) {
      <section class="hazard overall">
        <div class="hazard-head"><mat-icon>functions</mat-icon><span>Overall (weighted)</span></div>
        @for (id of data().hub_ids; track id) {
          <app-score-bar [value]="data().overall_scores[id]" [label]="name(id)" />
        }
      </section>
    }

    <div class="verdict">
      <mat-icon>flag</mat-icon>
      <span><b>{{ name(data().highest_overall_hub_id) }}</b> has the higher exposure{{ verdictDetail() }}.</span>
    </div>

    <h4 class="drivers-title">Main drivers</h4>
    @for (a of data().assessments; track a.hub_id) {
      @let top = topHazard(a.hazards);
      @if (top) {
        <div class="driver">
          <div class="driver-head">{{ a.hub_name }}: {{ hazardInfo(top.hazard).label }} {{ top.score | number: '1.1-2' }}</div>
          <app-factor-breakdown [factors]="top.factors" [color]="hazardInfo(top.hazard).color" />
        </div>
      }
    }
  `,
  styles: `
    .title { font: 600 16px var(--wr-font); margin: 0; color: var(--wr-ink); }
    .sub { font-size: 12px; color: var(--wr-muted); margin: 2px 0 12px; }
    .hazard { display: grid; gap: 6px; padding: 10px 0; border-bottom: 1px solid var(--wr-line); }
    .hazard-head { display: flex; align-items: center; gap: 6px; font: 600 13px var(--wr-font); }
    .hazard-head mat-icon { font-size: 20px; width: 20px; height: 20px; }
    .leader { margin-left: auto; font-weight: 400; font-size: 12px; color: var(--wr-muted); }
    .verdict { display: flex; gap: 8px; align-items: center; margin: 14px 0; padding: 10px 12px;
      background: var(--wr-subtle); border-radius: 8px; font-size: 13px; }
    .drivers-title { font: 600 14px var(--wr-font); margin: 16px 0 8px; }
    .driver { margin-bottom: 14px; }
    .driver-head { font-size: 13px; font-weight: 600; margin-bottom: 6px; }
  `,
})
export class ComparisonView {
  readonly result = input.required<CapabilityResult>();
  readonly names = input<Record<string, string>>({});

  protected readonly hazardInfo = hazardInfo;
  protected readonly data = computed(() => this.result().data as ComparisonData);
  protected readonly period = computed(() => {
    const a = this.result().arguments;
    return periodLabel(a['start_date'], a['end_date']);
  });
  protected readonly hubsTitle = computed(() => this.data().hub_ids.map((id) => this.name(id)).join(' vs. '));
  protected readonly verdictDetail = computed(() => {
    const data = this.data();
    if (data.hub_ids.length !== 2) return ' overall';
    const diff = data.overall_differences[0];
    if (!diff) return '';
    return ` overall (${Math.abs(diff.difference).toFixed(2)} points ahead)`;
  });

  protected name(id: string): string {
    const fromAssessment = this.data().assessments.find((a) => a.hub_id === id)?.hub_name;
    return fromAssessment ?? hubName(id, this.names());
  }

  protected topHazard<T extends { contribution_to_overall: number }>(hazards: T[]): T | null {
    return hazards.reduce<T | null>((best, h) => (!best || h.contribution_to_overall > best.contribution_to_overall ? h : best), null);
  }
}
