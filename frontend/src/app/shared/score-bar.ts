import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { DecimalPipe } from '@angular/common';

/** A 0–100 score as a labelled horizontal bar. Shows the exact value it is given. */
@Component({
  selector: 'app-score-bar',
  imports: [DecimalPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="row" [class.compact]="compact()">
      @if (label()) {
        <span class="label" [title]="label()">{{ label() }}</span>
      }
      <div class="track" role="meter" [attr.aria-valuenow]="value()" aria-valuemin="0"
           aria-valuemax="100" [attr.aria-label]="label() || 'score'">
        <div class="fill" [style.width.%]="width()" [style.background]="color()"></div>
      </div>
      <span class="value">{{ value() | number: '1.1-2' }}</span>
    </div>
  `,
  styles: `
    .row { display: grid; grid-template-columns: minmax(84px, 34%) 1fr 48px; align-items: center; gap: 10px; }
    .row.compact { grid-template-columns: 1fr 44px; }
    .label { font-size: 13px; color: var(--wr-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .track { height: 10px; border-radius: 5px; background: var(--wr-track); overflow: hidden; }
    .fill { height: 100%; border-radius: 5px; transition: width 400ms ease; }
    .value { font: 600 13px/1 var(--wr-mono); text-align: right; color: var(--wr-text); }
  `,
})
export class ScoreBar {
  readonly value = input.required<number>();
  readonly label = input<string>('');
  readonly color = input<string>('var(--wr-brand)');
  readonly compact = input(false);

  protected readonly width = computed(() => Math.max(0, Math.min(100, this.value())));
}
