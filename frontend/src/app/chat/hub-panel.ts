import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { MatIcon } from '@angular/material/icon';
import { MatTooltip } from '@angular/material/tooltip';

import { Hub } from '../core/api.models';
import { humanize } from '../core/hazards';

/** The company's hubs by region; clicking one asks for its overall risk. */
@Component({
  selector: 'app-hub-panel',
  imports: [MatIcon, MatTooltip],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="title">Hubs</div>
    @for (group of groups(); track group.region) {
      <div class="region">{{ group.region }}</div>
      @for (hub of group.hubs; track hub.id) {
        <button type="button" class="hub" [disabled]="disabled()" (click)="analyze.emit(hub)"
                [matTooltip]="'Analyze ' + hub.name + '\\'s overall weather risk'" matTooltipPosition="right">
          <mat-icon>warehouse</mat-icon>
          <span class="name">{{ hub.name }}</span>
          <span class="state">{{ hub.state }}</span>
        </button>
      }
    } @empty {
      <div class="empty">No hubs loaded.</div>
    }
  `,
  styles: `
    :host { display: block; padding: 16px 12px; }
    .title { font: 600 11px var(--wr-font); text-transform: uppercase; letter-spacing: .06em; color: var(--wr-muted); margin-bottom: 8px; }
    .region { font: 600 12px var(--wr-font); color: var(--wr-ink); margin: 12px 4px 4px; }
    .hub { display: grid; grid-template-columns: 20px 1fr auto; gap: 8px; align-items: center; width: 100%; padding: 7px 8px;
      border: 0; border-radius: 8px; background: none; font: 13px var(--wr-font); color: var(--wr-text); cursor: pointer; text-align: left; }
    .hub:hover:not(:disabled), .hub:focus-visible { background: var(--wr-subtle); outline: none; }
    .hub:disabled { opacity: .5; cursor: default; }
    .hub mat-icon { font-size: 18px; width: 18px; height: 18px; color: var(--wr-muted); }
    .state { font-size: 11px; color: var(--wr-muted); }
    .empty { font-size: 13px; color: var(--wr-muted); }
  `,
})
export class HubPanel {
  readonly hubs = input<Hub[]>([]);
  readonly disabled = input(false);
  readonly analyze = output<Hub>();

  protected readonly groups = computed(() => {
    const groups = new Map<string, Hub[]>();
    for (const hub of this.hubs()) {
      const region = humanize(hub.region);
      groups.set(region, [...(groups.get(region) ?? []), hub]);
    }
    return [...groups].map(([region, hubs]) => ({ region, hubs }));
  });
}
