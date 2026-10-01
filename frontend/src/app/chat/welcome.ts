import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { MatIcon } from '@angular/material/icon';

import { Hub } from '../core/api.models';
import { STARTER_QUESTIONS } from '../core/describe';
import { HAZARD_ORDER, HAZARDS, humanize } from '../core/hazards';

/** First screen: what the product does, example questions, the hubs and the hazards. */
@Component({
  selector: 'app-welcome',
  imports: [MatIcon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="hero">
      <h1>Which hubs should we protect from severe weather?</h1>
      <p>Ask about the weather and natural-hazard exposure of your distribution hubs. Answers are
        built from public weather and hazard data, scored with transparent rules, and explained in
        plain language.</p>
    </div>

    <div class="section-label">Try a question</div>
    <div class="questions">
      @for (q of questions; track q) {
        <button type="button" class="question" (click)="ask.emit(q)">
          <mat-icon>chat_bubble_outline</mat-icon><span>{{ q }}</span>
        </button>
      }
    </div>

    <div class="facts">
      <div>
        <div class="section-label">Your hubs</div>
        @for (group of hubsByRegion(); track group.region) {
          <div class="region"><b>{{ group.region }}</b> {{ group.names }}</div>
        } @empty {
          <div class="region muted">Loading hubs…</div>
        }
      </div>
      <div>
        <div class="section-label">Hazards we score</div>
        <div class="hazards">
          @for (h of hazards; track h.label) {
            <span class="chip"><mat-icon [style.color]="h.color">{{ h.icon }}</mat-icon>{{ h.label }}</span>
          }
        </div>
      </div>
    </div>
  `,
  styles: `
    :host { display: block; max-width: 720px; margin: 0 auto; padding: 32px 8px 8px; }
    .hero h1 { font: 600 26px/1.25 var(--wr-font); color: var(--wr-ink); margin: 0 0 8px; }
    .hero p { font-size: 15px; line-height: 1.55; color: var(--wr-text); margin: 0 0 24px; }
    .section-label { font: 600 11px var(--wr-font); text-transform: uppercase; letter-spacing: .06em; color: var(--wr-muted); margin-bottom: 8px; }
    .questions { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 28px; }
    .question { display: flex; gap: 10px; align-items: flex-start; text-align: left; padding: 14px; border-radius: 12px;
      border: 1px solid var(--wr-line); background: #fff; font: 14px/1.4 var(--wr-font); color: var(--wr-ink); cursor: pointer;
      transition: border-color .15s, box-shadow .15s; }
    .question:hover, .question:focus-visible { border-color: var(--wr-brand); box-shadow: 0 2px 8px rgb(11 37 69 / 10%); outline: none; }
    .question mat-icon { color: var(--wr-brand); font-size: 20px; width: 20px; height: 20px; flex: none; }
    .facts { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
    .region { font-size: 13px; color: var(--wr-text); margin-bottom: 4px; }
    .region b { margin-right: 4px; }
    .muted { color: var(--wr-muted); }
    .hazards { display: flex; flex-wrap: wrap; gap: 6px; }
    .chip { display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; border-radius: 16px; background: #fff;
      border: 1px solid var(--wr-line); font-size: 13px; }
    .chip mat-icon { font-size: 18px; width: 18px; height: 18px; }
    @media (max-width: 700px) { .questions, .facts { grid-template-columns: 1fr; } }
  `,
})
export class Welcome {
  readonly hubs = input<Hub[]>([]);
  readonly ask = output<string>();

  protected readonly questions = STARTER_QUESTIONS;
  protected readonly hazards = HAZARD_ORDER.map((h) => HAZARDS[h]);
  protected readonly hubsByRegion = computed(() => {
    const groups = new Map<string, string[]>();
    for (const hub of this.hubs()) {
      const region = humanize(hub.region);
      groups.set(region, [...(groups.get(region) ?? []), hub.name]);
    }
    return [...groups].map(([region, names]) => ({ region, names: names.join(' · ') }));
  });
}
