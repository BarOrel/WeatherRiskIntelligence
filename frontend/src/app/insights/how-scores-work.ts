import { ChangeDetectionStrategy, Component } from '@angular/core';
import { MatIcon } from '@angular/material/icon';

import { HAZARD_ORDER, HAZARDS } from '../core/hazards';

/** Business-level explanation of the scores. Used in the empty insight panel and the ⓘ dialog. */
@Component({
  selector: 'app-how-scores-work',
  imports: [MatIcon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h3 class="title">How scores work</h3>
    <p class="lead">Every hub gets a <b>0–100 exposure score</b> per hazard. Higher means the hub
      faced more of that weather than the other hubs. Scores come from fixed, transparent rules
      applied to public data. The AI explains them but never invents or changes them.</p>

    <ul class="hazards">
      @for (h of hazards; track h.label) {
        <li>
          <mat-icon [style.color]="h.color">{{ h.icon }}</mat-icon>
          <div><b>{{ h.label }}</b><span>{{ h.summary }}</span></div>
        </li>
      }
    </ul>

    <h4>Overall score</h4>
    <p>A weighted mix of the four hazards (default weights: winter 25%, flood 25%, hurricane 30%,
      heat 20%). When you ask about specific hazards, only those are combined. Each answer's
      evidence shows the exact weights used.</p>

    <h4>Data</h4>
    <p>Daily weather from Open-Meteo, river flow from the Copernicus GloFAS flood model, and
      hurricane tracks from the U.S. National Hurricane Center.</p>

    <h4>Keep in mind</h4>
    <p>Scores compare hubs; they are not the probability of a closure or a financial loss. They
      don't include building resilience, drainage, insurance or local infrastructure.</p>
  `,
  styles: `
    :host { display: block; font-size: 13px; color: var(--wr-text); line-height: 1.5; }
    .title { font: 600 16px var(--wr-font); margin: 0 0 6px; color: var(--wr-ink); }
    .lead { margin-top: 0; }
    h4 { font: 600 13px var(--wr-font); margin: 14px 0 2px; color: var(--wr-ink); }
    p { margin: 2px 0; }
    .hazards { list-style: none; padding: 0; margin: 10px 0; display: grid; gap: 8px; }
    .hazards li { display: grid; grid-template-columns: 24px 1fr; gap: 8px; align-items: start; }
    .hazards b { display: block; }
    .hazards span { color: var(--wr-muted); font-size: 12px; }
  `,
})
export class HowScoresWork {
  protected readonly hazards = HAZARD_ORDER.map((h) => HAZARDS[h]);
}
