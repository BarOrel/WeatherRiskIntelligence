import { ChangeDetectionStrategy, Component, ElementRef, input, output, signal, viewChild } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIcon } from '@angular/material/icon';

/** Question input: Enter sends, Shift+Enter adds a new line. */
@Component({
  selector: 'app-composer',
  imports: [MatButtonModule, MatIcon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <form class="composer" (submit)="submit($event)">
      <textarea #box rows="1" [value]="text()" (input)="onInput(box)" (keydown.enter)="onEnter($event)"
                placeholder="Ask about your hubs, e.g. “Which hubs are most exposed to flooding?”"
                aria-label="Your question" maxlength="4000" [disabled]="disabled()"></textarea>
      <button mat-flat-button type="submit" class="send" [disabled]="disabled() || !text().trim()" aria-label="Send">
        <mat-icon>send</mat-icon>
      </button>
    </form>
    <div class="note">Answers use public data and transparent scoring. The AI explains results but doesn't calculate them.</div>
  `,
  styles: `
    .composer { display: flex; gap: 8px; align-items: flex-end; background: #fff; border: 1px solid var(--wr-line);
      border-radius: 14px; padding: 8px 8px 8px 14px; box-shadow: 0 1px 4px rgb(11 37 69 / 6%); }
    .composer:focus-within { border-color: var(--wr-brand); }
    textarea { flex: 1; border: 0; outline: none; resize: none; font: 15px/1.5 var(--wr-font); color: var(--wr-ink);
      max-height: 140px; padding: 6px 0; background: transparent; }
    .send { min-width: 44px; height: 40px; padding: 0 10px; }
    .send mat-icon { margin: 0; }
    .note { font-size: 11px; color: var(--wr-muted); text-align: center; margin-top: 6px; }
  `,
})
export class Composer {
  readonly disabled = input(false);
  readonly send = output<string>();

  protected readonly text = signal('');
  private readonly box = viewChild.required<ElementRef<HTMLTextAreaElement>>('box');

  protected onInput(box: HTMLTextAreaElement): void {
    this.text.set(box.value);
    box.style.height = 'auto';
    box.style.height = `${box.scrollHeight}px`;
  }

  protected onEnter(event: Event): void {
    if ((event as KeyboardEvent).shiftKey) return;
    this.submit(event);
  }

  protected submit(event: Event): void {
    event.preventDefault();
    const question = this.text().trim();
    if (!question || this.disabled()) return;
    this.send.emit(question);
    this.text.set('');
    const box = this.box().nativeElement;
    box.value = '';
    box.style.height = 'auto';
  }

  focus(): void {
    this.box().nativeElement.focus();
  }
}
