import { ChangeDetectionStrategy, Component, computed, input, output, signal } from '@angular/core';
import { MatIcon } from '@angular/material/icon';

import { SessionSummary } from '../core/api.models';
import { relativeTime } from '../core/time';

const COLLAPSED = 5;

/** Saved conversations (stored by the server); clicking one reopens it. */
@Component({
  selector: 'app-conversation-list',
  imports: [MatIcon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="title">Conversations</div>
    @for (session of visible(); track session.session_id) {
      <button type="button" class="conversation" [class.current]="session.session_id === currentId()"
              [disabled]="disabled()" [attr.aria-current]="session.session_id === currentId() ? 'true' : null"
              [title]="session.title" (click)="open.emit(session.session_id)">
        <mat-icon>{{ session.session_id === currentId() ? 'chat' : 'chat_bubble_outline' }}</mat-icon>
        <span class="text">
          <span class="name">{{ session.title }}</span>
          <span class="meta">{{ when(session.updated_at) }} · {{ session.turn_count }} {{ session.turn_count === 1 ? 'turn' : 'turns' }}</span>
        </span>
      </button>
    } @empty {
      <div class="empty">No saved conversations yet.</div>
    }
    @if (sessions().length > collapsed) {
      <button type="button" class="more" (click)="expanded.set(!expanded())">
        {{ expanded() ? 'Show less' : 'Show all (' + sessions().length + ')' }}
      </button>
    }
  `,
  styles: `
    :host { display: block; padding: 16px 12px 12px; border-bottom: 1px solid var(--wr-line); }
    .title { font: 600 11px var(--wr-font); text-transform: uppercase; letter-spacing: .06em; color: var(--wr-muted); margin-bottom: 8px; }
    .conversation { display: grid; grid-template-columns: 20px minmax(0, 1fr); gap: 8px; align-items: start; width: 100%;
      padding: 7px 8px; border: 0; border-radius: 8px; background: none; color: var(--wr-text); cursor: pointer; text-align: left; }
    .conversation:hover:not(:disabled), .conversation:focus-visible { background: var(--wr-subtle); outline: none; }
    .conversation.current { background: var(--wr-subtle); }
    .conversation.current .name { font-weight: 600; }
    .conversation:disabled { opacity: .5; cursor: default; }
    .conversation mat-icon { font-size: 18px; width: 18px; height: 18px; color: var(--wr-muted); margin-top: 1px; }
    .text { display: grid; min-width: 0; }
    .name { font: 13px var(--wr-font); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .meta { font: 11px var(--wr-font); color: var(--wr-muted); }
    .empty { font-size: 13px; color: var(--wr-muted); }
    .more { margin-top: 4px; padding: 4px 8px; border: 0; background: none; font: 600 12px var(--wr-font); color: var(--wr-brand); cursor: pointer; }
  `,
})
export class ConversationList {
  readonly sessions = input<SessionSummary[]>([]);
  readonly currentId = input<string | null>(null);
  readonly disabled = input(false);
  readonly open = output<string>();

  protected readonly collapsed = COLLAPSED;
  protected readonly expanded = signal(false);
  protected readonly visible = computed(() =>
    this.expanded() ? this.sessions() : this.sessions().slice(0, COLLAPSED),
  );

  protected when(iso: string): string {
    return relativeTime(iso);
  }
}
