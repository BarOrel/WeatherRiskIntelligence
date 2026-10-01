import { ChangeDetectionStrategy, Component, computed, input, output, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIcon } from '@angular/material/icon';
import { MatTooltip } from '@angular/material/tooltip';

import { ChatMessage } from '../core/chat-store';
import { describeAction } from '../core/describe';
import { MarkdownPipe } from '../shared/markdown.pipe';

/** One chat bubble. Agent answers add "How I got this", copy, and follow-up suggestions. */
@Component({
  selector: 'app-chat-message',
  imports: [MatButtonModule, MatIcon, MatTooltip, MarkdownPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @let m = message();
    @switch (m.role) {
      @case ('user') {
        <div class="bubble user">{{ m.text }}</div>
      }
      @case ('error') {
        <div class="bubble error" role="alert">
          <mat-icon>error_outline</mat-icon>
          <div>
            <div>{{ m.text }}</div>
            @if (m.retryText && retryable()) {
              <button mat-stroked-button type="button" (click)="retry.emit(m)">Try again</button>
            }
          </div>
        </div>
      }
      @default {
        <div class="bubble agent" [class.selected]="selected()" (click)="select.emit(m)">
          <div class="answer" [innerHTML]="m.text | markdown"></div>

          @if (steps().length) {
            <button type="button" class="trace-toggle" (click)="toggleTrace($event)" [attr.aria-expanded]="traceOpen()">
              <mat-icon>{{ traceOpen() ? 'expand_less' : 'expand_more' }}</mat-icon>
              How I got this ({{ steps().length }} {{ steps().length === 1 ? 'step' : 'steps' }})
            </button>
            @if (traceOpen()) {
              <ol class="trace">
                @for (s of steps(); track $index) {
                  <li [class]="s.status">
                    <mat-icon>{{ s.icon }}</mat-icon>
                    <span>{{ s.text }}</span>
                    <span class="ms">{{ s.ms }}</span>
                  </li>
                }
              </ol>
            }
          }

          <div class="actions">
            <button mat-icon-button type="button" (click)="copy($event)" [matTooltip]="copied() ? 'Copied' : 'Copy answer'"
                    aria-label="Copy answer">
              <mat-icon>{{ copied() ? 'check' : 'content_copy' }}</mat-icon>
            </button>
            @if (m.results?.length) {
              <span class="evidence-hint">{{ selected() ? 'Evidence shown on the right' : 'Click to show evidence' }}</span>
            }
          </div>
        </div>
        @if (showFollowUps() && m.followUps?.length) {
          <div class="follow-ups">
            @for (q of m.followUps; track q) {
              <button type="button" class="chip" (click)="ask.emit(q)">{{ q }}</button>
            }
          </div>
        }
      }
    }
  `,
  styles: `
    :host { display: block; }
    .bubble { max-width: 88%; padding: 12px 14px; border-radius: 14px; font-size: 14px; line-height: 1.55; }
    .user { margin-left: auto; width: fit-content; background: var(--wr-brand); color: #fff; border-bottom-right-radius: 4px; }
    .agent { background: #fff; border: 1px solid var(--wr-line); border-bottom-left-radius: 4px; cursor: pointer;
      transition: border-color .15s, box-shadow .15s; }
    .agent.selected { border-color: var(--wr-brand); box-shadow: 0 0 0 1px var(--wr-brand); }
    .error { display: flex; gap: 10px; background: #fff4f2; border: 1px solid #f3c2b9; color: #8c2f1d; }
    .error button { margin-top: 8px; }
    .answer :first-child { margin-top: 0; }
    .answer :last-child { margin-bottom: 0; }
    .answer { overflow-wrap: anywhere; }
    .trace-toggle { display: inline-flex; align-items: center; gap: 2px; margin-top: 10px; padding: 2px 6px 2px 0; border: 0;
      background: none; color: var(--wr-brand); font: 600 12px var(--wr-font); cursor: pointer; }
    .trace-toggle mat-icon { font-size: 18px; width: 18px; height: 18px; }
    .trace { list-style: none; margin: 6px 0 0; padding: 8px 10px; background: var(--wr-subtle); border-radius: 8px; display: grid; gap: 6px; }
    .trace li { display: grid; grid-template-columns: 18px 1fr auto; gap: 8px; align-items: center; font-size: 12px; }
    .trace mat-icon { font-size: 16px; width: 16px; height: 16px; }
    .trace .success mat-icon { color: #1e8e3e; }
    .trace .error mat-icon { color: #c5221f; }
    .trace .skipped mat-icon { color: var(--wr-muted); }
    .ms { color: var(--wr-muted); font-family: var(--wr-mono); }
    .actions { display: flex; align-items: center; gap: 4px; margin: 6px -8px -8px; }
    .evidence-hint { font-size: 11px; color: var(--wr-muted); }
    .follow-ups { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0 0; }
    .chip { padding: 6px 12px; border-radius: 16px; border: 1px solid var(--wr-line); background: #fff; color: var(--wr-brand);
      font: 13px var(--wr-font); cursor: pointer; }
    .chip:hover, .chip:focus-visible { border-color: var(--wr-brand); outline: none; }
  `,
})
export class ChatMessageView {
  readonly message = input.required<ChatMessage>();
  readonly names = input<Record<string, string>>({});
  readonly selected = input(false);
  readonly showFollowUps = input(false);
  readonly retryable = input(true);
  readonly select = output<ChatMessage>();
  readonly ask = output<string>();
  readonly retry = output<ChatMessage>();

  protected readonly traceOpen = signal(false);
  protected readonly copied = signal(false);

  protected readonly steps = computed(() =>
    (this.message().actions ?? []).map((a) => ({
      status: a.status,
      icon: a.status === 'success' ? 'check_circle' : a.status === 'error' ? 'cancel' : 'replay',
      text:
        describeAction(a, this.names()) +
        (a.status === 'error' ? `: ${a.error ?? 'failed'}` : a.status === 'skipped' ? ' (reused an earlier result)' : ''),
      ms: a.duration_ms >= 1000 ? `${(a.duration_ms / 1000).toFixed(1)} s` : `${a.duration_ms} ms`,
    })),
  );

  protected toggleTrace(event: Event): void {
    event.stopPropagation();
    this.traceOpen.update((open) => !open);
  }

  protected async copy(event: Event): Promise<void> {
    event.stopPropagation();
    try {
      await navigator.clipboard.writeText(this.message().text);
      this.copied.set(true);
      setTimeout(() => this.copied.set(false), 1500);
    } catch {
      // Clipboard not available (e.g. insecure context); nothing else to do.
    }
  }
}
