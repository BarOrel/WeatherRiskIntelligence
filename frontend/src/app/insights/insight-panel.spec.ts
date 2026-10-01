import { TestBed } from '@angular/core/testing';

import { CapabilityResult } from '../core/api.models';
import { ChatMessage } from '../core/chat-store';
import { COMPARISON, NAMES, RANKING, WEATHER } from '../testing/fixtures';
import { InsightPanel } from './insight-panel';

function render(results: CapabilityResult[] | null): HTMLElement {
  const fixture = TestBed.createComponent(InsightPanel);
  const message: ChatMessage | null = results
    ? { id: 'a', role: 'agent', text: 'answer', at: '', results }
    : null;
  fixture.componentRef.setInput('message', message);
  fixture.componentRef.setInput('names', NAMES);
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

describe('InsightPanel', () => {
  it('explains how scores work before the first answer', () => {
    const el = render(null);
    expect(el.textContent).toContain('Getting started');
    expect(el.querySelector('app-how-scores-work')).toBeTruthy();
  });

  it('shows a ranking with exact scores and why #1 ranks first', () => {
    const el = render([RANKING]);
    expect(el.querySelector('app-ranking-view h3')?.textContent).toContain('Midwest hubs by winter exposure');
    const bars = [...el.querySelectorAll('app-ranking-view ol app-score-bar')].map((b) => b.textContent);
    expect(bars[0]).toContain('Minneapolis');
    expect(bars[0]).toContain('59.53');
    expect(bars[1]).toContain('45.17');
    expect(el.textContent).toContain('Why Minneapolis ranks #1');
  });

  it('shows a comparison per hazard with the leader and difference', () => {
    const el = render([COMPARISON]);
    const text = el.textContent ?? '';
    expect(text).toContain('Miami vs. Houston');
    expect(text).toContain('Houston higher by 22.03');
    expect(text).toContain('Miami higher by 6.29');
    expect(text).toContain('Houston has the higher exposure overall (6.58 points ahead)');
  });

  it('shows weather facts as KPI tiles with their thresholds', () => {
    const el = render([WEATHER]);
    const text = el.textContent ?? '';
    expect(text).toContain('Weather facts · Denver');
    expect(text).toContain('8.49%');
    expect(text).toContain('31 of 365 days');
    expect(text).toContain('≥ 0.25 cm');
  });

  it('always lists data sources and the exposure caveat, with warnings', () => {
    const el = render([COMPARISON]);
    const text = el.textContent ?? '';
    expect(text).toContain('Data sources');
    expect(text).toContain('NOAA National Hurricane Center');
    expect(text).toContain('not the probability of a closure or financial loss');
    expect(text).toContain('NHC best-track data only covers storms through 2025-10-29.');
  });

  it('hides the hub lookup when other evidence exists', () => {
    const lookup: CapabilityResult = { capability: 'list_hubs', arguments: {}, data: { hubs: [] }, warnings: [] };
    const el = render([lookup, RANKING]);
    expect(el.querySelector('app-hub-list-view')).toBeNull();
    expect(el.querySelector('app-ranking-view')).toBeTruthy();
  });
});
