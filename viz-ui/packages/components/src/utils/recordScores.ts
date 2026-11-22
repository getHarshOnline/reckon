import type { CausalScore, MemoryRecord } from '../types';

/** Classify supplied fields, without validating the experiment behind a delta. */
export function recordScoreSource(score: CausalScore | null | undefined): string {
  if (score == null) return 'Not recorded';
  if (score.ablationDelta != null || score.counterfactualDelta != null) {
    return 'Measurement supplied';
  }
  return score.influenceProxy != null ? 'Proxy only' : 'Unscored';
}

/** Identify proxy-only records in the supplied inventory, independently of graph edges. */
export function proxyOnlyRecordIds(records: readonly MemoryRecord[]): string[] {
  return [...new Set(records
    .filter(record => recordScoreSource(record.causalScore) === 'Proxy only')
    .map(record => record.id))].sort();
}
