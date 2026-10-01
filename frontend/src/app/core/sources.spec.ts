import { COMPARISON, RANKING, WEATHER } from '../testing/fixtures';
import { FLOOD_SOURCE, HURRICANE_SOURCE, WEATHER_SOURCE } from './hazards';
import { collectCaveats, collectSources, resultHazards } from './sources';

describe('collectSources', () => {
  it('lists the public datasets behind the hazards that were scored', () => {
    expect(collectSources([RANKING])).toEqual([WEATHER_SOURCE]);
    expect(collectSources([COMPARISON])).toEqual([WEATHER_SOURCE, FLOOD_SOURCE, HURRICANE_SOURCE]);
    expect(collectSources([WEATHER, RANKING])).toEqual([WEATHER_SOURCE]);
  });

  it('uses the source named by a hazard dataset', () => {
    const hazard = { capability: 'get_hazard_data', arguments: {}, data: { source: 'NOAA X' }, warnings: [] };
    expect(collectSources([hazard])).toEqual(['NOAA X']);
  });
});

describe('resultHazards', () => {
  it('reads the selection from rankings, comparisons and assessments', () => {
    expect(resultHazards(RANKING)).toEqual(['winter']);
    expect(resultHazards(COMPARISON)).toEqual(['flood', 'hurricane']);
    const analysis = { capability: 'analyze_hub_risk', arguments: {}, data: RANKING.data['assessments'][0], warnings: [] };
    expect(resultHazards(analysis)).toEqual(['winter']);
  });
});

describe('collectCaveats', () => {
  it('separates warnings from assumptions and de-duplicates them', () => {
    const { warnings, assumptions } = collectCaveats([COMPARISON, COMPARISON]);
    expect(warnings).toEqual(['NHC best-track data only covers storms through 2025-10-29.']);
    expect(assumptions).toContain('Based on modelled daily weather.');
    expect(new Set(assumptions).size).toBe(assumptions.length);
  });
});
