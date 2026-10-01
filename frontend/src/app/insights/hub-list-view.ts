import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { CapabilityResult } from '../core/api.models';
import { humanize } from '../core/hazards';

/** The hubs the agent looked up. */
@Component({
  selector: 'app-hub-list-view',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h3 class="title">Hubs</h3>
    <ul>
      @for (h of hubs(); track h.hub_id) {
        <li><b>{{ h.name }}</b> <span>{{ h.state }} · {{ region(h.region) }}</span></li>
      }
    </ul>
  `,
  styles: `
    .title { font: 600 16px var(--wr-font); margin: 0 0 8px; color: var(--wr-ink); }
    ul { list-style: none; padding: 0; margin: 0; display: grid; gap: 6px; font-size: 13px; }
    span { color: var(--wr-muted); margin-left: 6px; }
  `,
})
export class HubListView {
  readonly result = input.required<CapabilityResult>();
  protected readonly hubs = computed(() => (this.result().data['hubs'] ?? []) as any[]);
  protected region = humanize;
}
