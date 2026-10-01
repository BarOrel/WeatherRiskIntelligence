import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { App } from './app';
import { STARTER_QUESTIONS } from './core/describe';
import { SessionSummary } from './core/api.models';
import { chatResponse, CONVERSATION, SESSION } from './testing/fixtures';

describe('App', () => {
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
  });

  async function create(sessions: SessionSummary[] = []) {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    http.expectOne('/hubs').flush([
      { id: 'chicago', name: 'Chicago', state: 'IL', region: 'midwest', location: { latitude: 0, longitude: 0 } },
      { id: 'minneapolis', name: 'Minneapolis', state: 'MN', region: 'midwest', location: { latitude: 0, longitude: 0 } },
    ]);
    http.expectOne('/chat/sessions').flush(sessions);
    if (sessions.length) {
      await new Promise((resolve) => setTimeout(resolve));
      http.expectOne(`/chat/sessions/${sessions[0].session_id}`).flush(CONVERSATION);
    }
    await fixture.whenStable();
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  it('welcomes the user with the example questions and the hubs', async () => {
    const { el } = await create();
    expect(el.querySelector('.brand')?.textContent).toContain('Weather Risk Intelligence');
    const questions = [...el.querySelectorAll('app-welcome .question span')].map((q) => q.textContent?.trim());
    expect(questions).toEqual(STARTER_QUESTIONS);
    expect(el.querySelector('app-hub-panel')?.textContent).toContain('Minneapolis');
  });

  it('asks a starter question and shows the answer, trace and follow-ups', async () => {
    const { fixture, el } = await create();
    (el.querySelector('app-welcome .question') as HTMLButtonElement).click();
    fixture.detectChanges();
    expect(el.querySelector('app-thinking-bubble')).toBeTruthy();

    const request = http.expectOne('/chat');
    expect(request.request.body.message).toBe(STARTER_QUESTIONS[0]);
    request.flush(chatResponse());
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el.querySelector('app-thinking-bubble')).toBeNull();
    expect(el.querySelector('.answer strong')?.textContent).toBe('Minneapolis');
    expect(el.querySelector('.trace-toggle')?.textContent).toContain('How I got this (1 step)');
    (el.querySelector('.trace-toggle') as HTMLButtonElement).click();
    fixture.detectChanges();
    expect(el.querySelector('.trace')?.textContent).toContain('Ranked Midwest hubs by winter exposure (2025)');
    expect(el.querySelectorAll('.follow-ups .chip').length).toBeGreaterThan(0);
    expect(el.querySelector('app-insight-panel app-ranking-view')).toBeTruthy();
  });

  it('shows a friendly error with a retry button', async () => {
    const { fixture, el } = await create();
    (el.querySelector('app-welcome .question') as HTMLButtonElement).click();
    http.expectOne('/chat').flush({ detail: 'down' }, { status: 504, statusText: 'Timeout' });
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el.querySelector('.bubble.error')?.textContent).toContain('took too long to respond');
    expect(el.querySelector('.bubble.error button')?.textContent).toContain('Try again');
  });

  it('reopens the most recent saved conversation and lists the others', async () => {
    const older: SessionSummary = { ...SESSION, session_id: 'older', title: 'Compare Miami and Houston', turn_count: 1 };
    const { fixture, el } = await create([SESSION, older]);

    const items = [...el.querySelectorAll('app-conversation-list .conversation')];
    expect(items.map((i) => i.querySelector('.name')?.textContent?.trim())).toEqual([SESSION.title, older.title]);
    expect(items[0].classList).toContain('current');
    expect(el.querySelector('app-welcome')).toBeNull();
    expect(el.querySelectorAll('app-chat-message').length).toBe(4);
    expect(el.querySelector('app-insight-panel app-ranking-view')).toBeTruthy();

    (items[1] as HTMLButtonElement).click();
    http.expectOne('/chat/sessions/older').flush({ session_id: 'older', turns: [CONVERSATION.turns[0]] });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(el.querySelectorAll('app-chat-message').length).toBe(2);
    expect(el.querySelectorAll('app-conversation-list .conversation')[1].classList).toContain('current');
  });
});
