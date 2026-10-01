import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatIcon } from '@angular/material/icon';

import { CapabilityResult } from '../core/api.models';
import { collectCaveats, collectSources } from '../core/sources';

/** Which public datasets an answer used, its warnings, and (on demand) its assumptions. */
@Component({
  selector: 'app-sources-caveats',
  imports: [MatExpansionModule, MatIcon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (sources().length) {
      <div class="block">
        <div class="head"><mat-icon>database</mat-icon> Data sources</div>
        <ul>
          @for (s of sources(); track s) { <li>{{ s }}</li> }
        </ul>
      </div>
    }
    <div class="block caveat">
      <div class="head"><mat-icon>info</mat-icon> How to read this</div>
      <p>Scores show <b>relative</b> weather exposure between hubs (0–100). They are not the
        probability of a closure or financial loss.</p>
      @for (w of caveats().warnings; track w) {
        <p class="warn"><mat-icon>warning</mat-icon>{{ w }}</p>
      }
    </div>
    @if (caveats().assumptions.length) {
      <mat-expansion-panel class="assumptions">
        <mat-expansion-panel-header>Assumptions & limitations ({{ caveats().assumptions.length }})</mat-expansion-panel-header>
        <ul>
          @for (a of caveats().assumptions; track a) { <li>{{ a }}</li> }
        </ul>
      </mat-expansion-panel>
    }
  `,
  styles: `
    .block { margin-top: 16px; font-size: 12px; color: var(--wr-text); }
    .head { display: flex; align-items: center; gap: 6px; font-weight: 600; color: var(--wr-ink); margin-bottom: 4px; }
    .head mat-icon { font-size: 18px; width: 18px; height: 18px; }
    ul { margin: 4px 0 0; padding-left: 18px; display: grid; gap: 3px; }
    p { margin: 4px 0; line-height: 1.45; }
    .caveat { background: var(--wr-subtle); padding: 10px 12px; border-radius: 8px; }
    .warn { display: flex; gap: 6px; color: #8a5a00; }
    .warn mat-icon { font-size: 16px; width: 16px; height: 16px; flex: none; margin-top: 1px; }
    .assumptions { margin-top: 10px; font-size: 12px; }
  `,
})
export class SourcesCaveats {
  readonly results = input.required<CapabilityResult[]>();
  protected readonly sources = computed(() => collectSources(this.results()));
  protected readonly caveats = computed(() => collectCaveats(this.results()));
}
