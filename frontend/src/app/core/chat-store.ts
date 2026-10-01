import { computed, inject, Injectable, signal } from '@angular/core';

import { ActionRecord, CapabilityResult, Conversation, Hub, SessionSummary } from './api.models';
import { ChatApiService, friendlyError } from './chat-api.service';
import { HubNames, suggestFollowUps } from './describe';

export type MessageRole = 'user' | 'agent' | 'error';

export interface ChatMessage {
  id: string;
  role: MessageRole;
  text: string;
  at: string;
  actions?: ActionRecord[];
  results?: CapabilityResult[];
  warnings?: string[];
  followUps?: string[];
  /** For error messages: the question to send again on "Try again". */
  retryText?: string;
  /** For error messages: the failed turn's id, reused on "Try again". */
  retryTurnId?: string;
}

/**
 * Conversation state for the whole app (signals). Conversations are stored by the server
 * (SQLite), so they survive restarts and can be reopened on any machine using that database.
 */
@Injectable({ providedIn: 'root' })
export class ChatStore {
  private readonly api = inject(ChatApiService);

  readonly messages = signal<ChatMessage[]>([]);
  readonly sessionId = signal<string | null>(null);
  /** A question is being answered. */
  readonly loading = signal(false);
  /** A stored conversation is being opened. */
  readonly opening = signal(false);
  /** Either of the above: controls that start a request are disabled. */
  readonly busy = computed(() => this.loading() || this.opening());
  readonly hubs = signal<Hub[]>([]);
  /** Stored conversations, most recently active first. */
  readonly conversations = signal<SessionSummary[]>([]);
  private readonly selectedId = signal<string | null>(null);

  readonly hubNames = computed<HubNames>(() =>
    Object.fromEntries(this.hubs().map((h) => [h.id, h.name])),
  );
  readonly hasConversation = computed(() => this.messages().length > 0);

  /** The agent answer whose evidence the insight panel shows (selected, else the latest). */
  readonly selectedAnswer = computed<ChatMessage | null>(() => {
    const answers = this.messages().filter((m) => m.role === 'agent');
    const id = this.selectedId();
    return answers.find((m) => m.id === id) ?? answers[answers.length - 1] ?? null;
  });

  /** Loads hubs and stored conversations, then reopens the most recent conversation. */
  async init(): Promise<void> {
    await Promise.all([this.loadHubs(), this.loadConversations()]);
    const latest = this.conversations()[0];
    if (latest && !this.hasConversation() && !this.busy()) {
      await this.open(latest.session_id);
    }
  }

  async loadHubs(): Promise<void> {
    try {
      this.hubs.set(await this.api.hubs());
    } catch {
      this.hubs.set([]);
    }
  }

  async loadConversations(): Promise<void> {
    try {
      this.conversations.set(await this.api.sessions());
    } catch {
      // The chat still works without the list; it is refreshed after the next answer.
    }
  }

  /** Shows a stored conversation with all its answers and evidence. */
  async open(sessionId: string): Promise<void> {
    if (this.busy()) return;
    this.opening.set(true);
    try {
      const conversation = await this.api.conversation(sessionId);
      this.sessionId.set(conversation.session_id);
      this.messages.set(this.toMessages(conversation));
      this.selectedId.set(null);
    } catch (error) {
      this.messages.set([]);
      this.sessionId.set(null);
      this.append({ role: 'error', text: `This conversation couldn't be loaded. ${friendlyError(error)}` });
    } finally {
      this.opening.set(false);
    }
  }

  async send(text: string, turnId: string = crypto.randomUUID()): Promise<void> {
    const question = text.trim();
    if (!question || this.busy()) return;

    this.append({ role: 'user', text: question });
    this.loading.set(true);
    try {
      const response = await this.api.chat({
        message: question,
        turn_id: turnId,
        ...(this.sessionId() ? { session_id: this.sessionId()! } : {}),
      });
      this.sessionId.set(response.session_id);
      const answer = this.append({
        role: 'agent',
        text: response.answer,
        actions: response.actions_performed,
        results: response.results,
        warnings: response.warnings,
        followUps: suggestFollowUps(response.results, this.hubNames()),
      });
      this.selectedId.set(answer.id);
      void this.loadConversations();
    } catch (error) {
      this.append({ role: 'error', text: friendlyError(error), retryText: question, retryTurnId: turnId });
    } finally {
      this.loading.set(false);
    }
  }

  /** Re-sends the question of a failed turn (removing the error and the original question).
   *  The turn id is reused: if the server did save that turn, it is replaced, not duplicated. */
  async retry(errorMessage: ChatMessage): Promise<void> {
    if (!errorMessage.retryText) return;
    const messages = this.messages();
    const index = messages.findIndex((m) => m.id === errorMessage.id);
    this.messages.set(messages.filter((_, i) => i !== index && i !== index - 1));
    await this.send(errorMessage.retryText, errorMessage.retryTurnId);
  }

  select(message: ChatMessage): void {
    if (message.role === 'agent') this.selectedId.set(message.id);
  }

  newChat(): void {
    this.messages.set([]);
    this.sessionId.set(null);
    this.selectedId.set(null);
  }

  private toMessages(conversation: Conversation): ChatMessage[] {
    const last = conversation.turns.length - 1;
    return conversation.turns.flatMap((turn, i) => [
      { id: `${turn.turn_id}-q`, role: 'user' as const, text: turn.question, at: turn.asked_at },
      {
        id: `${turn.turn_id}-a`,
        role: 'agent' as const,
        text: turn.answer,
        at: turn.answered_at,
        actions: turn.actions_performed,
        results: turn.results,
        warnings: turn.warnings,
        followUps: i === last ? suggestFollowUps(turn.results, this.hubNames()) : [],
      },
    ]);
  }

  private append(message: Omit<ChatMessage, 'id' | 'at'>): ChatMessage {
    const full: ChatMessage = { ...message, id: crypto.randomUUID(), at: new Date().toISOString() };
    this.messages.update((list) => [...list, full]);
    return full;
  }
}
