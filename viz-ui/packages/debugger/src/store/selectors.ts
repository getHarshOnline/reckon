import { timelineCoordinate } from '@rtepl/reckon-components';
import type { DebuggerState, Episode } from './debuggerStore';
import type { DebuggerEvent, MemoryRecord } from '@rtepl/reckon-components';

/**
 * Selectors for the debugger store.
 *
 * Using selectors with zustand provides:
 * - Memoization via shallow equality checks
 * - Clean separation of derived state
 * - Performance optimization (components only re-render on actual changes)
 */

/**
 * Simple memoization helper for selectors.
 * Caches result based on input equality check.
 */
function createMemoizedSelector<S, R>(
  selector: (state: S) => R,
  getKey: (state: S) => unknown[]
): (state: S) => R {
  let lastKey: unknown[] | null = null;
  let lastResult: R;

  return (state: S): R => {
    const key = getKey(state);
    const keysEqual = lastKey !== null &&
      key.length === lastKey.length &&
      key.every((v, i) => v === lastKey![i]);

    if (!keysEqual) {
      lastKey = key;
      lastResult = selector(state);
    }
    return lastResult;
  };
}

/**
 * Select currently selected event
 */
export function selectSelectedEvent(state: DebuggerState): DebuggerEvent | null {
  if (!state.selectedEventId) return null;
  return state.eventsMap.get(state.selectedEventId) ?? null;
}

/**
 * Select currently selected record
 */
export function selectSelectedRecord(state: DebuggerState): MemoryRecord | null {
  if (!state.selectedRecordId) return null;
  return state.recordsMap.get(state.selectedRecordId) ?? null;
}

/**
 * Select currently selected episode
 */
export function selectSelectedEpisode(state: DebuggerState): Episode | null {
  if (!state.selectedEpisodeId) return null;
  return state.episodes.get(state.selectedEpisodeId) ?? null;
}

/**
 * Select events for the current episode (memoized)
 */
export const selectEpisodeEvents = createMemoizedSelector(
  (state: DebuggerState): DebuggerEvent[] => {
    if (!state.selectedEpisodeId) return state.events;

    return state.events.filter(
      (e) => e.episodeId === state.selectedEpisodeId
    );
  },
  (state) => [state.events, state.selectedEpisodeId]
);

/**
 * Select events within current time range (memoized)
 */
export const selectVisibleEvents = createMemoizedSelector(
  (state: DebuggerState): DebuggerEvent[] => {
    const [start, end] = state.timeRange;
    const margin = (end - start) * 0.1;

    return state.events.filter(
      (e) => timelineCoordinate(e) >= start - margin && timelineCoordinate(e) <= end + margin
    );
  },
  (state) => [state.events, state.timeRange[0], state.timeRange[1]]
);

/**
 * Select all records from visible events (memoized)
 */
export const selectVisibleRecords = createMemoizedSelector(
  (state: DebuggerState): MemoryRecord[] => {
    const visibleEvents = selectVisibleEvents(state);

    // Use Map to deduplicate records, flatMap for cleaner iteration
    const recordMap = new Map<string, MemoryRecord>(
      visibleEvents
        .flatMap((event) => event.snapshot ?? [])
        .map((record) => [record.id, record])
    );

    return Array.from(recordMap.values());
  },
  (state) => [state.events, state.timeRange[0], state.timeRange[1]]
);

/**
 * Select episodes as array
 */
export function selectEpisodesArray(state: DebuggerState): Episode[] {
  return Array.from(state.episodes.values()).sort(
    (a, b) => a.startTime - b.startTime
  );
}

/**
 * Select event count stats
 */
export function selectEventStats(state: DebuggerState): {
  total: number;
  visible: number;
  selected: boolean;
} {
  const visible = selectVisibleEvents(state);
  return {
    total: state.events.length,
    visible: visible.length,
    selected: state.selectedEventId !== null,
  };
}

/**
 * Select connection info for display
 */
export function selectConnectionInfo(state: DebuggerState): {
  status: DebuggerState['connectionStatus'];
  url: string;
  error: string | null;
  isConnected: boolean;
} {
  return {
    status: state.connectionStatus,
    url: state.wsUrl,
    error: state.lastError,
    isConnected: state.connectionStatus === 'connected',
  };
}

/**
 * Select loading state based on connection status and event availability.
 * Returns true when connecting or when connected but no events received yet.
 */
export function selectIsLoading(state: DebuggerState): boolean {
  return (
    state.connectionStatus === 'connecting' ||
    (state.connectionStatus === 'connected' && state.events.length === 0)
  );
}

// ============================================================================
// Causal Graph Selectors
// ============================================================================

/**
 * Select violations matching current filters
 */
export function selectViolationCount(state: DebuggerState): number {
  return state.transitivityReport?.totalViolations ?? 0;
}

/**
 * Select violations by category
 */
export function selectViolationsByCategory(state: DebuggerState): Record<string, number> {
  return state.transitivityReport?.violationsByCategory ?? {};
}

/**
 * Select causal graph state for panel
 */
export function selectCausalGraphState(state: DebuggerState): {
  edgeDisplayMode: DebuggerState['edgeDisplayMode'];
  truthMode: DebuggerState['truthMode'];
  selectedEdgeId: string | null;
  edgeDrawerOpen: boolean;
  isVerifying: boolean;
  violationCount: number;
} {
  return {
    edgeDisplayMode: state.edgeDisplayMode,
    truthMode: state.truthMode,
    selectedEdgeId: state.selectedEdgeId,
    edgeDrawerOpen: state.edgeDrawerOpen,
    isVerifying: state.isVerifying,
    violationCount: state.transitivityReport?.totalViolations ?? 0,
  };
}
