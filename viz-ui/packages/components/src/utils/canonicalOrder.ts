/**
 * Canonical ordering utilities for Reckon events.
 *
 * Events are ordered by the canonical key: (episode_id, step, sequence).
 * Wall-clock timestamps (timestamp, wallTimeMs) are display-only fallbacks.
 *
 * ## Ordering Rules
 *
 * 1. **Canonical ordering**: When episodeId, step, and sequence are all present,
 *    events are ordered by (episodeId, step, sequence) ascending.
 *
 * 2. **Degraded ordering**: When episodeId and step exist but sequence is missing,
 *    the comparator operates in "degraded mode":
 *    - sequence is treated as 0
 *    - wallTimeMs is used as a secondary tiebreaker
 *    - Events are labeled as "degraded ordering"
 *
 * 3. **Mixed ordering**: Canonical/degraded items sort before non-canonical items.
 *
 * 4. **Fallback ordering**: When canonical fields are missing, falls back to
 *    timestamp or wallTimeMs.
 *
 * 5. **Tiebreaker**: id (or eventId) is used as a stable tiebreaker when all else
 *    is equal.
 *
 * See docs/12-Reproducibility.md for specification.
 */

/**
 * Item with optional canonical ordering fields.
 */
export interface CanonicallyOrderable {
  episodeId?: string;
  step?: number;
  sequence?: number;
  /** Fallback for ordering when canonical fields are missing */
  timestamp?: number;
  /** Alternative fallback (e.g., wallTimeMs for DebuggerEvent) */
  wallTimeMs?: number;
  /** Stable tiebreaker when all else is equal */
  id?: string;
  /** Alternative tiebreaker (e.g., eventId for DebuggerEvent) */
  eventId?: string;
}

/**
 * Ordering mode for an item.
 */
export type OrderingMode = 'canonical' | 'degraded' | 'fallback';

/**
 * Result of analyzing ordering fields.
 */
export interface OrderingAnalysis {
  mode: OrderingMode;
  hasEpisodeId: boolean;
  hasStep: boolean;
  hasSequence: boolean;
}

/**
 * Check if an item has all canonical ordering fields.
 * Returns true only when episodeId, step, AND sequence are all present.
 */
export function hasCanonicalFields(item: CanonicallyOrderable): boolean {
  return (
    item.episodeId !== undefined &&
    item.episodeId !== '' &&
    item.step !== undefined &&
    item.sequence !== undefined
  );
}

/**
 * Check if an item is in degraded ordering mode.
 *
 * Degraded mode: episodeId and step are present, but sequence is missing.
 * In this mode, sequence is treated as 0 and wallTimeMs is used as tiebreaker.
 */
export function isDegradedOrdering(item: CanonicallyOrderable): boolean {
  return (
    item.episodeId !== undefined &&
    item.episodeId !== '' &&
    item.step !== undefined &&
    item.sequence === undefined
  );
}

/**
 * Analyze the ordering mode of an item.
 */
export function analyzeOrdering(item: CanonicallyOrderable): OrderingAnalysis {
  const hasEpisodeId = item.episodeId !== undefined && item.episodeId !== '';
  const hasStep = item.step !== undefined;
  const hasSequence = item.sequence !== undefined;

  let mode: OrderingMode;
  if (hasEpisodeId && hasStep && hasSequence) {
    mode = 'canonical';
  } else if (hasEpisodeId && hasStep && !hasSequence) {
    mode = 'degraded';
  } else {
    mode = 'fallback';
  }

  return { mode, hasEpisodeId, hasStep, hasSequence };
}

/**
 * Get the tiebreaker ID from an item.
 * Prefers 'id' but falls back to 'eventId' for DebuggerEvent compatibility.
 */
function getTiebreakerId(item: CanonicallyOrderable): string {
  return String(item.id ?? item.eventId ?? '');
}

/** Numeric kernel IDs keep their order even beyond JavaScript's exact integers. */
function compareEventIds(a: string, b: string): number {
  if (/^\d+$/.test(a) && /^\d+$/.test(b)) {
    const left = BigInt(a), right = BigInt(b);
    return left < right ? -1 : left > right ? 1 : 0;
  }
  return a.localeCompare(b);
}

/**
 * Compare two items by canonical ordering.
 *
 * Canonical order: (episodeId, step, sequence) ascending
 * Degraded mode: sequence=0, tiebreak by wallTimeMs then id
 * Fallback: timestamp or wallTimeMs when canonical fields missing
 * Tiebreaker: id or eventId (stable sort)
 *
 * @returns negative if a < b, positive if a > b, 0 if equal
 */
export function compareCanonical<T extends CanonicallyOrderable>(
  a: T,
  b: T
): number {
  const aAnalysis = analyzeOrdering(a);
  const bAnalysis = analyzeOrdering(b);

  // Both have canonical or degraded ordering: use canonical key
  const aHasCanonicalOrDegraded =
    aAnalysis.mode === 'canonical' || aAnalysis.mode === 'degraded';
  const bHasCanonicalOrDegraded =
    bAnalysis.mode === 'canonical' || bAnalysis.mode === 'degraded';

  if (aHasCanonicalOrDegraded && bHasCanonicalOrDegraded) {
    // Compare episodeId (string comparison)
    const epA = a.episodeId ?? '';
    const epB = b.episodeId ?? '';
    if (epA !== epB) {
      return epA.localeCompare(epB);
    }

    // Compare step
    const stepA = a.step ?? 0;
    const stepB = b.step ?? 0;
    if (stepA !== stepB) {
      return stepA - stepB;
    }

    // Compare sequence (0 for degraded mode)
    const seqA = a.sequence ?? 0;
    const seqB = b.sequence ?? 0;
    if (seqA !== seqB) {
      return seqA - seqB;
    }

    // Wall time is comparable only when both events lack a canonical sequence.
    if (aAnalysis.mode === 'degraded' && bAnalysis.mode === 'degraded') {
      const timeA = a.wallTimeMs ?? a.timestamp ?? 0;
      const timeB = b.wallTimeMs ?? b.timestamp ?? 0;
      if (timeA !== timeB) {
        return timeA - timeB;
      }
    }

    // Final tiebreaker: id for stable sort
    const idA = getTiebreakerId(a);
    const idB = getTiebreakerId(b);
    return compareEventIds(idA, idB);
  }

  // Mixed: canonical/degraded items come first, then fallback
  if (aHasCanonicalOrDegraded && !bHasCanonicalOrDegraded) {
    return -1; // a (canonical/degraded) comes before b (fallback)
  }
  if (!aHasCanonicalOrDegraded && bHasCanonicalOrDegraded) {
    return 1; // b (canonical/degraded) comes before a (fallback)
  }

  // Neither has canonical fields: fall back to timestamp
  const timeA = a.timestamp ?? a.wallTimeMs ?? 0;
  const timeB = b.timestamp ?? b.wallTimeMs ?? 0;
  if (timeA !== timeB) {
    return timeA - timeB;
  }

  // Final tiebreaker: id for stable sort
  const idA = getTiebreakerId(a);
  const idB = getTiebreakerId(b);
  return compareEventIds(idA, idB);
}

/**
 * Sort an array by canonical ordering (in place).
 */
export function sortCanonical<T extends CanonicallyOrderable>(items: T[]): T[] {
  return items.sort(compareCanonical);
}

/**
 * Create a sorted copy by canonical ordering.
 */
export function sortedCanonical<T extends CanonicallyOrderable>(
  items: readonly T[]
): T[] {
  return [...items].sort(compareCanonical);
}
