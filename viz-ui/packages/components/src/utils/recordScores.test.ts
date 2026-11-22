import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import type { MemoryRecord } from '../types';
import { recordScoreSource, proxyOnlyRecordIds } from './recordScores';

const cases = JSON.parse(readFileSync(new URL(
  '../../../../../src/tests/fixtures/record_score_presence.json', import.meta.url,
), 'utf8'));

describe('record score presence', () => {
  for (const sample of cases) {
    it(sample.id, () => expect(recordScoreSource(sample.score)).toBe(sample.source));
  }
  it('keeps an absent score object unavailable', () => {
    expect(recordScoreSource(undefined)).toBe('Not recorded');
    expect(recordScoreSource(null)).toBe('Not recorded');
  });
  it('counts unique proxy-only records without changing the inventory', () => {
    const records = cases.map((sample: { id: string; score: unknown }) => ({
      id: sample.id, causalScore: sample.score,
    })) as MemoryRecord[];
    const original = JSON.stringify(records);
    expect(proxyOnlyRecordIds([...records, records[0]])).toEqual(['proxy_positive', 'proxy_zero']);
    expect(JSON.stringify(records)).toBe(original);
    expect(proxyOnlyRecordIds([])).toEqual([]);
  });
});
