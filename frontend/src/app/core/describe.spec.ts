import { COMPARISON, NAMES, RANKING, WEATHER } from '../testing/fixtures';
import { describeAction, hazardsLabel, periodLabel, suggestFollowUps } from './describe';

describe('describeAction', () => {
  it('turns capability calls into plain language', () => {
    expect(describeAction(RANKING, NAMES)).toBe('Ranked Midwest hubs by winter exposure (2025)');
    expect(describeAction(COMPARISON, NAMES)).toBe('Compared Miami and Houston for flood and hurricane (2025)');
    expect(describeAction(WEATHER, NAMES)).toBe('Calculated weather statistics for Denver (2025)');
    expect(describeAction({ capability: 'list_hubs', arguments: {} }, NAMES)).toBe('Looked up all hubs');
  });

  it('falls back to readable names for unknown hubs and capabilities', () => {
    expect(describeAction({ capability: 'analyze_hub_risk', arguments: { hub_id: 'new_york' } }, {})).toBe(
      'Scored New york for all hazards',
    );
    expect(describeAction({ capability: 'some_new_tool', arguments: {} }, {})).toBe('Some new tool');
  });
});

describe('labels', () => {
  it('shows a full calendar year as the year, otherwise the range', () => {
    expect(periodLabel('2025-01-01', '2025-12-31')).toBe('2025');
    expect(periodLabel('2025-03-01', '2025-05-31')).toBe('2025-03-01 → 2025-05-31');
  });

  it('names hazard selections', () => {
    expect(hazardsLabel(undefined)).toBe('all hazards');
    expect(hazardsLabel(['flood', 'hurricane'])).toBe('flood and hurricane');
  });
});

describe('suggestFollowUps', () => {
  it('suggests why/what-about questions after a ranking', () => {
    expect(suggestFollowUps([RANKING], NAMES)).toEqual([
      'Why is the first one higher?',
      'What about flooding?',
      'Which hub should we prioritize for investment?',
    ]);
  });

  it('skips "why is the first one higher" when only one hub was ranked', () => {
    const single = { ...RANKING, data: { ...RANKING.data, rankings: [RANKING.data['rankings'][0]] } };
    expect(suggestFollowUps([single], NAMES)).not.toContain('Why is the first one higher?');
  });

  it('suggests the hazards not yet compared', () => {
    expect(suggestFollowUps([COMPARISON], NAMES)).toEqual([
      'What about winter disruption?',
      'What about heat?',
      'Which of them should we prioritize?',
    ]);
  });

  it('returns nothing without results', () => {
    expect(suggestFollowUps([], NAMES)).toEqual([]);
  });
});
