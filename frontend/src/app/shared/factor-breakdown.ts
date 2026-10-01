import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { MatTooltip } from '@angular/material/tooltip';

import { RiskFactor } from '../core/api.models';
import { factorLabel, formatValue } from '../core/hazards';

/** What drives a hazard score: each factor's measured value and the points it contributes. */
@Component({
  selector: 'app-factor-breakdown',
  imports: [DecimalPipe, MatTooltip],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <ul class="factors">
      @for (f of sorted(); track f.name) {
        <li [matTooltip]="f.description" matTooltipPosition="left">
          <div class="head">
            <span class="name">{{ label(f.name) }}</span>
            <span class="points">+{{ f.contribution | number: '1.1-2' }} pts</span>
          </div>
          <div class="track"><div class="fill" [style.width.%]="f.normalized_score" [style.background]="color()"></div></div>
          <div class="meta">{{ value(f) }} · weight {{ f.weight * 100 | number: '1.0-0' }}%</div>
        </li>
      }
    </ul>
  `,
  styles: `
    .factors { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
    li { cursor: help; }
    .head { display: flex; justify-content: space-between; font-size: 13px; }
    .name { color: var(--wr-text); }
    .points { font: 600 13px var(--wr-mono); color: var(--wr-text); }
    .track { height: 6px; border-radius: 3px; background: var(--wr-track); margin: 4px 0 2px; overflow: hidden; }
    .fill { height: 100%; border-radius: 3px; opacity: 0.85; }
    .meta { font-size: 12px; color: var(--wr-muted); }
  `,
})
export class FactorBreakdown {
  readonly factors = input.required<RiskFactor[]>();
  readonly color = input<string>('var(--wr-brand)');

  protected readonly sorted = computed(() =>
    [...this.factors()].sort((a, b) => b.contribution - a.contribution),
  );
  protected label = factorLabel;
  protected value(f: RiskFactor): string {
    return formatValue(f.raw_value, f.unit);
  }
}
