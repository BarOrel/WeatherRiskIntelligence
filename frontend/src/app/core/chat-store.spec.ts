import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { chatResponse, CONVERSATION, SESSION } from '../testing/fixtures';
import { ChatStore } from './chat-store';

async function flushMicrotasks(): Promise<void> {
  for (let i = 0; i < 5; i++) await Promise.resolve();
}

describe('ChatStore', () => {
  let store: ChatStore;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    store = TestBed.inject(ChatStore);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    // Each answer refreshes the conversation list in the background.
    http.match('/chat/sessions').forEach((request) => request.flush([]));
    http.verify();
  });

  it('sends a question, stores the answer with its evidence and the session', async () => {
    const pending = store.send('  Which Midwest hubs?  ');
    expect(store.loading()).toBe(true);
    const request = http.expectOne('/chat');
    expect(request.request.body).toEqual({ message: 'Which Midwest hubs?', turn_id: expect.any(String) });
    request.flush(chatResponse());
    await pending;

    expect(store.loading()).toBe(false);
    expect(store.sessionId()).toBe('session-1');
    const [question, answer] = store.messages();
    expect(question).toMatchObject({ role: 'user', text: 'Which Midwest hubs?' });
    expect(answer).toMatchObject({ role: 'agent', text: '**Minneapolis** ranks first.' });
    expect(answer.results?.[0].capability).toBe('rank_hubs');
    expect(answer.followUps?.length).toBeGreaterThan(0);
    expect(store.selectedAnswer()?.id).toBe(answer.id);
  });

  it('continues the same session for follow-up questions', async () => {
    const first = store.send('Rank Midwest');
    http.expectOne('/chat').flush(chatResponse());
    await first;

    const second = store.send('Why?');
    const request = http.expectOne('/chat');
    expect(request.request.body).toEqual({ message: 'Why?', session_id: 'session-1', turn_id: expect.any(String) });
    request.flush(chatResponse({ answer: 'Because…' }));
    await second;
    expect(store.messages()).toHaveLength(4);
  });

  it('turns API failures into friendly messages that can be retried', async () => {
    const pending = store.send('Hello');
    http.expectOne('/chat').flush({ detail: 'No LLM is configured.' }, { status: 503, statusText: 'Unavailable' });
    await pending;

    const error = store.messages()[1];
    expect(error.role).toBe('error');
    expect(error.text).toContain('The AI assistant is not available right now');
    expect(error.text).toContain('No LLM is configured.');

    const retry = store.retry(error);
    http.expectOne('/chat').flush(chatResponse());
    await retry;
    expect(store.messages().map((m) => m.role)).toEqual(['user', 'agent']);
  });

  it('gives each question its own turn id and reuses it on "Try again"', async () => {
    const first = store.send('Hello');
    const failed = http.expectOne('/chat');
    failed.flush({ detail: 'The language model returned no text' }, { status: 502, statusText: 'Bad Gateway' });
    await first;
    const turnId = failed.request.body.turn_id;
    expect(turnId).toMatch(/^[A-Za-z0-9_-]+$/);

    const retry = store.retry(store.messages()[1]);
    const retried = http.expectOne('/chat');
    expect(retried.request.body.turn_id).toBe(turnId);
    retried.flush(chatResponse());
    await retry;

    const next = store.send('Next question');
    const nextRequest = http.expectOne('/chat');
    expect(nextRequest.request.body.turn_id).not.toBe(turnId);
    nextRequest.flush(chatResponse());
    await next;
    expect(store.messages().map((m) => m.role)).toEqual(['user', 'agent', 'user', 'agent']);
  });

  it('ignores empty questions and questions sent while busy', async () => {
    await store.send('   ');
    http.expectNone('/chat');

    const pending = store.send('First');
    await store.send('Second');
    http.expectOne('/chat').flush(chatResponse());
    await pending;
    expect(store.messages().filter((m) => m.role === 'user')).toHaveLength(1);
  });

  it('new chat clears the conversation and the session', async () => {
    const pending = store.send('Rank');
    http.expectOne('/chat').flush(chatResponse());
    await pending;

    store.newChat();
    expect(store.messages()).toEqual([]);
    expect(store.sessionId()).toBeNull();
    expect(store.selectedAnswer()).toBeNull();
  });

  it('refreshes the saved conversations after each answer', async () => {
    const pending = store.send('Rank');
    http.expectOne('/chat').flush(chatResponse());
    await pending;

    http.expectOne('/chat/sessions').flush([SESSION]);
    await Promise.resolve();
    expect(store.conversations()).toEqual([SESSION]);
  });

  describe('stored conversations', () => {
    it('on start loads hubs and conversations, then reopens the most recent one', async () => {
      const init = store.init();
      http.expectOne('/hubs').flush([]);
      http.expectOne('/chat/sessions').flush([SESSION, { ...SESSION, session_id: 'older' }]);
      await flushMicrotasks();
      expect(store.opening()).toBe(true);
      expect(store.loading()).toBe(false); // no "thinking" bubble while opening
      http.expectOne('/chat/sessions/session-1').flush(CONVERSATION);
      await init;

      expect(store.sessionId()).toBe('session-1');
      expect(store.messages().map((m) => [m.role, m.text])).toEqual([
        ['user', 'Which Midwest hubs are most exposed to winter?'],
        ['agent', 'Minneapolis ranks first.'],
        ['user', 'Why?'],
        ['agent', '**Minneapolis** ranks first.'],
      ]);
      const [, first, , last] = store.messages();
      expect(last.results?.[0].capability).toBe('rank_hubs');
      expect(last.actions?.[0].duration_ms).toBe(502);
      expect(first.followUps).toEqual([]);
      expect(last.followUps?.length).toBeGreaterThan(0);
      expect(store.selectedAnswer()?.id).toBe(last.id);
    });

    it('on start with no saved conversations shows the welcome state', async () => {
      const init = store.init();
      http.expectOne('/hubs').flush([]);
      http.expectOne('/chat/sessions').flush([]);
      await init;

      expect(store.hasConversation()).toBe(false);
      expect(store.sessionId()).toBeNull();
    });

    it('continues an opened conversation in the same session', async () => {
      const opened = store.open('session-1');
      http.expectOne('/chat/sessions/session-1').flush(CONVERSATION);
      await opened;

      const pending = store.send('And heat?');
      const request = http.expectOne('/chat');
      expect(request.request.body.session_id).toBe('session-1');
      request.flush(chatResponse());
      await pending;
      expect(store.messages()).toHaveLength(6);
    });

    it('shows an error when a conversation cannot be loaded', async () => {
      const opened = store.open('gone');
      http.expectOne('/chat/sessions/gone').flush({ detail: "Unknown session 'gone'" }, { status: 404, statusText: 'Not Found' });
      await opened;

      expect(store.sessionId()).toBeNull();
      expect(store.messages().map((m) => m.role)).toEqual(['error']);
      expect(store.messages()[0].text).toContain("couldn't be loaded");
    });

    it('does not send while a conversation is opening', async () => {
      const opened = store.open('session-1');
      await store.send('Too early');
      http.expectNone('/chat');
      http.expectOne('/chat/sessions/session-1').flush(CONVERSATION);
      await opened;
    });
  });
});
