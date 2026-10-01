import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';

/** Staged progress while the agent works. Stages are time-based: the API does not stream. */
export const THINKING_STAGES: { afterMs: number; text: string }[] = [
  { afterMs: 0, text: 'Understanding your question…' },
  { afterMs: 1500, text: 'Gathering weather & hazard data…' },
  { afterMs: 4000, text: 'Calculating exposure scores…' },
  { afterMs: 7000, text: 'Writing the answer…' },
];

@Component({
  selector: 'app-thinking-bubble',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="bubble" role="status" aria-live="polite">
      <span class="dots"><i></i><i></i><i></i></span>
      <span>{{ stage() }}</span>
    </div>
  `,
  styles: `
    .bubble { display: inline-flex; align-items: center; gap: 10px; padding: 12px 14px; border-radius: 14px;
      border: 1px solid var(--wr-line); background: #fff; font-size: 14px; color: var(--wr-muted); }
    .dots { display: inline-flex; gap: 3px; }
    .dots i { width: 6px; height: 6px; border-radius: 50%; background: var(--wr-brand); animation: pulse 1.2s infinite ease-in-out; }
    .dots i:nth-child(2) { animation-delay: .15s; }
    .dots i:nth-child(3) { animation-delay: .3s; }
    @keyframes pulse { 0%, 80%, 100% { opacity: .25; transform: scale(.8); } 40% { opacity: 1; transform: scale(1); } }
  `,
})
export class ThinkingBubble {
  protected readonly stage = signal(THINKING_STAGES[0].text);

  constructor() {
    const timers = THINKING_STAGES.slice(1).map((s) => setTimeout(() => this.stage.set(s.text), s.afterMs));
    inject(DestroyRef).onDestroy(() => timers.forEach(clearTimeout));
  }
}
