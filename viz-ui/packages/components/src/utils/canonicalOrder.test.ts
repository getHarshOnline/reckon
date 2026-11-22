/**
 * Tests for canonical ordering utilities.
 *
 * Verifies that (episodeId, step, sequence) ordering takes precedence
 * over wall-clock timestamp, per docs/12-Reproducibility.md.
 */

// @ts-expect-error vitest types will be available after pnpm install
import { describe, it, expect } from 'vitest';
import {
  compareCanonical,
  sortedCanonical,
  hasCanonicalFields,
  isDegradedOrdering,
  analyzeOrdering,
  type CanonicallyOrderable,
} from './canonicalOrder';

describe('canonicalOrder', () => {
  describe('hasCanonicalFields', () => {
    it('returns true when all canonical fields present', () => {
      const item = { episodeId: 'ep1', step: 1, sequence: 0 };
      expect(hasCanonicalFields(item)).toBe(true);
    });

    it('returns false when episodeId missing', () => {
      const item = { step: 1, sequence: 0 };
      expect(hasCanonicalFields(item)).toBe(false);
    });

    it('returns false when step missing', () => {
      const item = { episodeId: 'ep1', sequence: 0 };
      expect(hasCanonicalFields(item)).toBe(false);
    });

    it('returns false when sequence missing', () => {
      const item = { episodeId: 'ep1', step: 1 };
      expect(hasCanonicalFields(item)).toBe(false);
    });

    it('returns false when episodeId is empty string', () => {
      const item = { episodeId: '', step: 1, sequence: 0 };
      expect(hasCanonicalFields(item)).toBe(false);
    });
  });

  describe('isDegradedOrdering', () => {
    it('returns true when episodeId and step present but sequence missing', () => {
      const item = { episodeId: 'ep1', step: 1 };
      expect(isDegradedOrdering(item)).toBe(true);
    });

    it('returns false when all canonical fields present', () => {
      const item = { episodeId: 'ep1', step: 1, sequence: 0 };
      expect(isDegradedOrdering(item)).toBe(false);
    });

    it('returns false when episodeId missing', () => {
      const item = { step: 1 };
      expect(isDegradedOrdering(item)).toBe(false);
    });

    it('returns false when step missing', () => {
      const item = { episodeId: 'ep1' };
      expect(isDegradedOrdering(item)).toBe(false);
    });
  });

  describe('analyzeOrdering', () => {
    it('identifies canonical mode', () => {
      const item = { episodeId: 'ep1', step: 1, sequence: 0 };
      const analysis = analyzeOrdering(item);
      expect(analysis.mode).toBe('canonical');
      expect(analysis.hasEpisodeId).toBe(true);
      expect(analysis.hasStep).toBe(true);
      expect(analysis.hasSequence).toBe(true);
    });

    it('identifies degraded mode', () => {
      const item = { episodeId: 'ep1', step: 1 };
      const analysis = analyzeOrdering(item);
      expect(analysis.mode).toBe('degraded');
      expect(analysis.hasEpisodeId).toBe(true);
      expect(analysis.hasStep).toBe(true);
      expect(analysis.hasSequence).toBe(false);
    });

    it('identifies fallback mode when only timestamp present', () => {
      const item = { timestamp: 100 };
      const analysis = analyzeOrdering(item);
      expect(analysis.mode).toBe('fallback');
      expect(analysis.hasEpisodeId).toBe(false);
      expect(analysis.hasStep).toBe(false);
      expect(analysis.hasSequence).toBe(false);
    });
  });

  describe('compareCanonical', () => {
    it('orders by episodeId first', () => {
      const a = { episodeId: 'a', step: 10, sequence: 0 };
      const b = { episodeId: 'b', step: 1, sequence: 0 };
      expect(compareCanonical(a, b)).toBeLessThan(0);
    });

    it('orders by step within same episode', () => {
      const a = { episodeId: 'ep1', step: 1, sequence: 0 };
      const b = { episodeId: 'ep1', step: 2, sequence: 0 };
      expect(compareCanonical(a, b)).toBeLessThan(0);
    });

    it('orders by sequence within same step', () => {
      const a = { episodeId: 'ep1', step: 1, sequence: 0 };
      const b = { episodeId: 'ep1', step: 1, sequence: 1 };
      expect(compareCanonical(a, b)).toBeLessThan(0);
    });

    it('uses id as tiebreaker when all else equal', () => {
      const a = { id: 'a', episodeId: 'ep1', step: 1, sequence: 0 };
      const b = { id: 'b', episodeId: 'ep1', step: 1, sequence: 0 };
      expect(compareCanonical(a, b)).toBeLessThan(0);
    });

    it('uses eventId as tiebreaker when id not present', () => {
      const a = { eventId: 'a', episodeId: 'ep1', step: 1, sequence: 0 };
      const b = { eventId: 'b', episodeId: 'ep1', step: 1, sequence: 0 };
      expect(compareCanonical(a, b)).toBeLessThan(0);
    });

    it('falls back to timestamp when canonical fields missing', () => {
      const a = { timestamp: 100 };
      const b = { timestamp: 200 };
      expect(compareCanonical(a, b)).toBeLessThan(0);
    });

    it('falls back to wallTimeMs when timestamp missing', () => {
      const a = { wallTimeMs: 100 };
      const b = { wallTimeMs: 200 };
      expect(compareCanonical(a, b)).toBeLessThan(0);
    });

    it('canonical items sort before non-canonical', () => {
      const canonical = { episodeId: 'ep1', step: 100, sequence: 0 };
      const nonCanonical = { timestamp: 1 };
      expect(compareCanonical(canonical, nonCanonical)).toBeLessThan(0);
    });

    it('degraded items sort before fallback items', () => {
      const degraded = { episodeId: 'ep1', step: 100, wallTimeMs: 100 };
      const fallback = { timestamp: 1 };
      expect(compareCanonical(degraded, fallback)).toBeLessThan(0);
    });
  });

  describe('compareCanonical - degraded mode', () => {
    it('treats missing sequence as 0', () => {
      const degraded = { id: 'x', episodeId: 'ep1', step: 1, wallTimeMs: 100 };
      const canonical = { id: 'y', episodeId: 'ep1', step: 1, sequence: 0 };
      // Both have sequence=0, so compare by wallTimeMs (degraded uses tiebreak) then id
      const result = compareCanonical(degraded, canonical);
      // Since sequence is treated as 0 for both, they differ on id
      expect(result).toBeLessThan(0); // 'x' < 'y'
    });

    it('uses wallTimeMs as tiebreaker for degraded events', () => {
      const a = { id: 'z', episodeId: 'ep1', step: 1, wallTimeMs: 100 };
      const b = { id: 'a', episodeId: 'ep1', step: 1, wallTimeMs: 200 };
      // Both degraded, same step, different wallTimeMs
      expect(compareCanonical(a, b)).toBeLessThan(0);
    });

    it('handles mixed canonical and degraded with same episodeId+step', () => {
      const canonical = { id: 'y', episodeId: 'ep1', step: 1, sequence: 1 };
      const degraded = { id: 'x', episodeId: 'ep1', step: 1, wallTimeMs: 100 };
      // canonical has sequence=1, degraded has sequence=0 (implicit)
      // degraded should come first (sequence 0 < 1)
      expect(compareCanonical(degraded, canonical)).toBeLessThan(0);
    });
  });

  describe('compareCanonical - cross-episode ordering', () => {
    it('sorts events from different episodes correctly', () => {
      const ep1_step1 = { id: 'a', episodeId: 'ep1', step: 1, sequence: 0 };
      const ep1_step2 = { id: 'b', episodeId: 'ep1', step: 2, sequence: 0 };
      const ep2_step1 = { id: 'c', episodeId: 'ep2', step: 1, sequence: 0 };
      const ep2_step2 = { id: 'd', episodeId: 'ep2', step: 2, sequence: 0 };

      const events = [ep2_step2, ep1_step2, ep2_step1, ep1_step1];
      const sorted = sortedCanonical(events);

      // Should be: ep1_step1, ep1_step2, ep2_step1, ep2_step2
      expect(sorted[0]?.id).toBe('a');
      expect(sorted[1]?.id).toBe('b');
      expect(sorted[2]?.id).toBe('c');
      expect(sorted[3]?.id).toBe('d');
    });

    it('respects episode ordering even with interleaved timestamps', () => {
      const events: CanonicallyOrderable[] = [
        { id: 'c', episodeId: 'ep2', step: 1, sequence: 0, timestamp: 100 },
        { id: 'a', episodeId: 'ep1', step: 1, sequence: 0, timestamp: 300 },
        { id: 'd', episodeId: 'ep2', step: 2, sequence: 0, timestamp: 200 },
        { id: 'b', episodeId: 'ep1', step: 2, sequence: 0, timestamp: 400 },
      ];

      const sorted = sortedCanonical(events);

      // Should be: ep1_step1 (a), ep1_step2 (b), ep2_step1 (c), ep2_step2 (d)
      // Canonical ordering ignores timestamp
      expect(sorted.map((e) => e.id)).toEqual(['a', 'b', 'c', 'd']);
    });
  });

  describe('sortedCanonical - clock skew scenario', () => {
    it('canonical ordering wins over out-of-order wallTimeMs', () => {
      // This is the key test: events with later wall-clock time
      // should still be ordered correctly by canonical fields
      const events: CanonicallyOrderable[] = [
        {
          id: 'event3',
          episodeId: 'ep1',
          step: 3,
          sequence: 0,
          timestamp: 100, // Earliest wall-clock time
        },
        {
          id: 'event1',
          episodeId: 'ep1',
          step: 1,
          sequence: 0,
          timestamp: 300, // Latest wall-clock time
        },
        {
          id: 'event2',
          episodeId: 'ep1',
          step: 2,
          sequence: 0,
          timestamp: 200, // Middle wall-clock time
        },
      ];

      const sorted = sortedCanonical(events);

      // Should be ordered by step (1, 2, 3) not by timestamp (100, 200, 300)
      expect(sorted[0]?.id).toBe('event1');
      expect(sorted[1]?.id).toBe('event2');
      expect(sorted[2]?.id).toBe('event3');
    });

    it('handles mixed canonical and non-canonical events', () => {
      const events: CanonicallyOrderable[] = [
        { id: 'legacy', timestamp: 50 }, // No canonical fields
        { id: 'event2', episodeId: 'ep1', step: 2, sequence: 0, timestamp: 100 },
        { id: 'event1', episodeId: 'ep1', step: 1, sequence: 0, timestamp: 200 },
      ];

      const sorted = sortedCanonical(events);

      // Canonical events come first (sorted by step), then non-canonical
      expect(sorted[0]?.id).toBe('event1');
      expect(sorted[1]?.id).toBe('event2');
      expect(sorted[2]?.id).toBe('legacy');
    });

    it('handles async events with same step but different sequence', () => {
      const events: CanonicallyOrderable[] = [
        { id: 'async2', episodeId: 'ep1', step: 1, sequence: 1, timestamp: 100 },
        { id: 'sync', episodeId: 'ep1', step: 1, sequence: 0, timestamp: 101 },
        { id: 'async3', episodeId: 'ep1', step: 1, sequence: 2, timestamp: 99 },
      ];

      const sorted = sortedCanonical(events);

      // Should be ordered by sequence, not timestamp
      expect(sorted[0]?.id).toBe('sync');
      expect(sorted[1]?.id).toBe('async2');
      expect(sorted[2]?.id).toBe('async3');
    });
  });

  describe('sortedCanonical - determinism tests', () => {
    it('tie-breaks by id when episodeId+step+sequence identical', () => {
      const a = { id: 'aaa', episodeId: 'ep1', step: 1, sequence: 0 };
      const b = { id: 'bbb', episodeId: 'ep1', step: 1, sequence: 0 };
      expect(compareCanonical(a, b)).toBeLessThan(0);
    });

    it('produces stable sort across multiple runs', () => {
      const events: CanonicallyOrderable[] = [
        { id: 'c', episodeId: 'ep1', step: 1, sequence: 0 },
        { id: 'a', episodeId: 'ep1', step: 1, sequence: 0 },
        { id: 'b', episodeId: 'ep1', step: 1, sequence: 0 },
      ];

      // Sort multiple times and verify same result
      const sorted1 = sortedCanonical(events);
      const sorted2 = sortedCanonical(events);
      const sorted3 = sortedCanonical([...events].reverse());

      expect(sorted1.map((e) => e.id)).toEqual(['a', 'b', 'c']);
      expect(sorted2.map((e) => e.id)).toEqual(['a', 'b', 'c']);
      expect(sorted3.map((e) => e.id)).toEqual(['a', 'b', 'c']);
    });
  });

  describe('sortedCanonical - does not mutate input', () => {
    it('returns new array without modifying original', () => {
      const original = [
        { id: 'b', episodeId: 'ep1', step: 2, sequence: 0 },
        { id: 'a', episodeId: 'ep1', step: 1, sequence: 0 },
      ];
      const originalCopy = [...original];

      const sorted = sortedCanonical(original);

      expect(original).toEqual(originalCopy);
      expect(sorted).not.toBe(original);
      expect(sorted[0]?.id).toBe('a');
    });
  });
});
