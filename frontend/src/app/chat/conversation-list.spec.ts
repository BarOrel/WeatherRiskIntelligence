import { TestBed } from '@angular/core/testing';

import { SessionSummary } from '../core/api.models';
import { relativeTime } from '../core/time';
import { SESSION } from '../testing/fixtures';
import { ConversationList } from './conversation-list';

function sessions(count: number): SessionSummary[] {
  return Array.from({ length: count }, (_, i) => ({ ...SESSION, session_id: `s${i}`, title: `Question ${i}` }));
}

function render(list: SessionSummary[], currentId: string | null = null) {
  const fixture = TestBed.createComponent(ConversationList);
  fixture.componentRef.setInput('sessions', list);
  fixture.componentRef.setInput('currentId', currentId);
  fixture.detectChanges();
  return { fixture, el: fixture.nativeElement as HTMLElement };
}

describe('ConversationList', () => {
  it('shows each conversation with its title, age and turn count, current highlighted', () => {
    const { el } = render(sessions(2), 's1');
    const items = el.querySelectorAll('.conversation');
    expect(items.length).toBe(2);
    expect(items[0].querySelector('.name')?.textContent).toBe('Question 0');
    expect(items[0].querySelector('.meta')?.textContent).toContain('2 turns');
    expect(items[1].classList).toContain('current');
    expect(items[1].getAttribute('aria-current')).toBe('true');
  });

  it('emits the session to open', () => {
    const { fixture, el } = render(sessions(2));
    const opened: string[] = [];
    fixture.componentInstance.open.subscribe((id) => opened.push(id));
    (el.querySelectorAll('.conversation')[1] as HTMLButtonElement).click();
    expect(opened).toEqual(['s1']);
  });

  it('shows five at first and the rest on demand', () => {
    const { fixture, el } = render(sessions(7));
    expect(el.querySelectorAll('.conversation').length).toBe(5);
    const more = el.querySelector('.more') as HTMLButtonElement;
    expect(more.textContent).toContain('Show all (7)');
    more.click();
    fixture.detectChanges();
    expect(el.querySelectorAll('.conversation').length).toBe(7);
  });

  it('has an empty state', () => {
    expect(render([]).el.textContent).toContain('No saved conversations yet.');
  });
});

describe('relativeTime', () => {
  const now = new Date('2026-10-01T12:00:00Z');
  it.each([
    ['2026-10-01T11:59:40Z', 'just now'],
    ['2026-10-01T11:55:00Z', '5 min ago'],
    ['2026-10-01T09:00:00Z', '3 h ago'],
    ['2026-09-30T10:00:00Z', 'yesterday'],
    ['2026-09-27T12:00:00Z', '4 days ago'],
  ])('%s -> %s', (iso, expected) => {
    expect(relativeTime(iso, now)).toBe(expected);
  });
});
