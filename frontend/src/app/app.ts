import {
  afterRenderEffect,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  inject,
  OnInit,
  signal,
  viewChild,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatIcon } from '@angular/material/icon';
import { MatTooltip } from '@angular/material/tooltip';

import { ChatMessageView } from './chat/chat-message';
import { Composer } from './chat/composer';
import { ConversationList } from './chat/conversation-list';
import { HubPanel } from './chat/hub-panel';
import { ScoreExplainerDialog } from './chat/score-explainer-dialog';
import { ThinkingBubble } from './chat/thinking-bubble';
import { Welcome } from './chat/welcome';
import { Hub } from './core/api.models';
import { ChatStore } from './core/chat-store';
import { conversationToMarkdown, downloadText } from './core/export';
import { InsightPanel } from './insights/insight-panel';

type Pane = 'chat' | 'evidence';

@Component({
  selector: 'app-root',
  imports: [
    MatButtonModule,
    MatIcon,
    MatTooltip,
    ChatMessageView,
    Composer,
    ConversationList,
    HubPanel,
    InsightPanel,
    ThinkingBubble,
    Welcome,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App implements OnInit {
  protected readonly store = inject(ChatStore);
  private readonly dialog = inject(MatDialog);

  protected readonly hubsOpen = signal(true);
  /** On narrow screens only one pane is visible at a time. */
  protected readonly pane = signal<Pane>('chat');

  private readonly scroller = viewChild<ElementRef<HTMLElement>>('scroller');
  private readonly composer = viewChild(Composer);

  constructor() {
    // While waiting: show the newest messages. When an answer arrives: show its beginning.
    afterRenderEffect(() => {
      const messages = this.store.messages();
      const loading = this.store.loading();
      const el = this.scroller()?.nativeElement;
      if (!el) return;
      const last = el.querySelector<HTMLElement>('app-chat-message:last-of-type');
      if (!loading && last && messages[messages.length - 1]?.role === 'agent') {
        el.scrollTop = last.offsetTop - el.offsetTop - 12;
      } else {
        el.scrollTop = el.scrollHeight;
      }
    });
  }

  ngOnInit(): void {
    void this.store.init();
  }

  protected ask(question: string): void {
    this.pane.set('chat');
    void this.store.send(question);
  }

  protected openConversation(sessionId: string): void {
    this.pane.set('chat');
    void this.store.open(sessionId);
  }

  protected analyzeHub(hub: Hub): void {
    this.ask(`Analyze ${hub.name}'s overall weather risk`);
  }

  protected newChat(): void {
    this.store.newChat();
    this.pane.set('chat');
    this.composer()?.focus();
  }

  protected exportChat(): void {
    const markdown = conversationToMarkdown(this.store.messages(), this.store.hubNames());
    downloadText(`weather-risk-conversation-${new Date().toISOString().slice(0, 10)}.md`, markdown);
  }

  protected openExplainer(): void {
    this.dialog.open(ScoreExplainerDialog, { maxWidth: '560px', autoFocus: false });
  }

  protected isLastAgent(index: number): boolean {
    const messages = this.store.messages();
    return messages[index]?.role === 'agent' && !messages.slice(index + 1).some((m) => m.role === 'agent');
  }
}
