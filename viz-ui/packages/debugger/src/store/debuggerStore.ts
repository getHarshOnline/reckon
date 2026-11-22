import { timelineCoordinate } from '@rtepl/reckon-components';
import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';
import type {
  DebuggerEvent,
  MemoryRecord,
  TimeRange,
  TransitivityReport,
  ComputeLedgerData,
  EdgeStatus,
  CausalEdge,
} from '@rtepl/reckon-components';
import { compareCanonical, EdgeDisplayMode, TruthMode } from '@rtepl/reckon-components';

/**
 * WebSocket connection status
 */
export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

/**
 * Episode metadata
 */
export interface Episode {
  id: string;
  startTime: number;
  endTime?: number;
  eventCount: number;
  status: 'active' | 'completed';
}

/**
 * Run summary from server
 */
export interface RunSummary {
  run_id: string;
  config_id: string;
  notebook_name: string;
  task_name: string;
  created_at: number;
  policy_name: string;
  num_episodes: number;
  budget_slots: number;
  success_rate: number | null;
  summary: Record<string, unknown>;
}

/**
 * Available run for selection
 */
export interface AvailableRun {
  run_id: string;
  task_name: string;
  policy_name: string;
  created_at: number;
}

/**
 * Store configuration
 */
export interface StoreConfig {
  /** Maximum events to keep in memory (default: 50000) */
  maxEvents: number;
  /** Maximum records to keep in memory (default: 50000) */
  maxRecords: number;
}

const DEFAULT_CONFIG: StoreConfig = {
  maxEvents: 50000,
  maxRecords: 50000,
};

/**
 * Debugger store state
 */
export interface DebuggerState {
  // ============================================================================
  // Configuration
  // ============================================================================

  /** Store configuration (max events/records limits) */
  config: StoreConfig;

  // ============================================================================
  // Data
  // ============================================================================

  /** All events indexed by ID for O(1) lookup */
  eventsMap: Map<string, DebuggerEvent>;

  /** Events as array (derived from map) */
  events: DebuggerEvent[];

  /** Events omitted from this browser window by its configured limit. */
  omittedEvents: number;

  /** Episodes indexed by ID */
  episodes: Map<string, Episode>;

  /** All records indexed by ID */
  recordsMap: Map<string, MemoryRecord>;

  // ============================================================================
  // Selection
  // ============================================================================

  /** Currently selected episode ID */
  selectedEpisodeId: string | null;

  /** Currently selected event ID */
  selectedEventId: string | null;

  /** Currently selected record ID */
  selectedRecordId: string | null;

  /** Visible time range [start, end] in milliseconds */
  timeRange: TimeRange;

  // ============================================================================
  // Connection
  // ============================================================================

  /** WebSocket connection status */
  connectionStatus: ConnectionStatus;

  /** WebSocket URL */
  wsUrl: string;

  /** Last connection error */
  lastError: string | null;

  // ============================================================================
  // Run State (new v1 architecture)
  // ============================================================================

  /** Currently selected run ID */
  selectedRunId: string | null;

  /** Current run summary */
  currentRunSummary: RunSummary | null;

  /** Available runs from server */
  availableRuns: AvailableRun[];

  // ============================================================================
  // UI State
  // ============================================================================

  /** Current view mode */
  viewMode: 'timeline' | 'causal' | 'pareto';

  /** Sidebar visibility */
  sidebarOpen: boolean;

  // ============================================================================
  // Causal Graph State
  // ============================================================================

  /** Current edge display choice for the relationship graph */
  edgeDisplayMode: EdgeDisplayMode;

  /** Current truth mode (research vs product) */
  truthMode: TruthMode;

  /** Currently selected edge ID */
  selectedEdgeId: string | null;

  /** Edge drawer open state */
  edgeDrawerOpen: boolean;

  /** Transitivity report */
  transitivityReport: TransitivityReport | null;

  /** Compute ledger */
  computeLedger: ComputeLedgerData | null;

  /** Edge statuses map */
  edgeStatuses: Map<string, EdgeStatus>;

  /** Caller-supplied inferred edges; the store does not compute closure */
  inferredEdges: CausalEdge[];

  /** Whether verification is in progress */
  isVerifying: boolean;

  /** Verification queue: pending probes to run */
  verificationQueue: {
    pendingProbes: number;
    estimatedCostEpisodes: number;
    estimatedCostSeconds: number;
  };

  /** Show verification confirmation dialog */
  showVerificationConfirmation: boolean;

  /** Focus mode state: show ego graph around selected node */
  focusMode: {
    enabled: boolean;
    hops: number;
    centerId: string | null;
  };

  // ============================================================================
  // Actions
  // ============================================================================

  /** Add events to the store (batched for performance) */
  addEvents: (events: DebuggerEvent[]) => void;

  /** Clear all events */
  clearEvents: () => void;

  /** Select an event by ID */
  selectEvent: (eventId: string | null) => void;

  /** Select an episode by ID */
  selectEpisode: (episodeId: string | null) => void;

  /** Select a record by ID */
  selectRecord: (recordId: string | null) => void;

  /** Set the visible time range */
  setTimeRange: (range: TimeRange) => void;

  /** Set connection status */
  setConnectionStatus: (status: ConnectionStatus, error?: string) => void;

  /** Set WebSocket URL */
  setWsUrl: (url: string) => void;

  /** Set view mode */
  setViewMode: (mode: DebuggerState['viewMode']) => void;

  /** Toggle sidebar */
  toggleSidebar: () => void;

  /** Reset store to initial state */
  reset: () => void;

  /** Update store configuration */
  setConfig: (config: Partial<StoreConfig>) => void;

  // ============================================================================
  // Run Actions (new v1 architecture)
  // ============================================================================

  /** Select a run by ID */
  selectRun: (runId: string | null) => void;

  /** Set current run summary (from WebSocket snapshot) */
  setCurrentRunSummary: (summary: RunSummary | null) => void;

  /** Set available runs */
  setAvailableRuns: (runs: AvailableRun[]) => void;

  // ============================================================================
  // Causal Graph Actions
  // ============================================================================

  /** Set the edge display choice */
  setEdgeDisplayMode: (mode: EdgeDisplayMode) => void;

  /** Set truth mode */
  setTruthMode: (mode: TruthMode) => void;

  /** Select an edge by ID */
  selectEdge: (edgeId: string | null) => void;

  /** Toggle edge drawer */
  toggleEdgeDrawer: () => void;

  /** Open edge drawer */
  openEdgeDrawer: () => void;

  /** Close edge drawer */
  closeEdgeDrawer: () => void;

  /** Set transitivity report */
  setTransitivityReport: (report: TransitivityReport | null) => void;

  /** Set compute ledger */
  setComputeLedgerData: (ledger: ComputeLedgerData | null) => void;

  /** Set edge statuses */
  setEdgeStatuses: (statuses: Map<string, EdgeStatus>) => void;

  /** Set inferred edges */
  setInferredEdges: (edges: CausalEdge[]) => void;

  /** Set verification state */
  setIsVerifying: (isVerifying: boolean) => void;

  /** Set verification queue */
  setVerificationQueue: (queue: DebuggerState['verificationQueue']) => void;

  /** Show/hide verification confirmation dialog */
  setShowVerificationConfirmation: (show: boolean) => void;

  /** Set focus mode */
  setFocusMode: (focusMode: Partial<DebuggerState['focusMode']>) => void;

  /** Toggle focus mode on/off */
  toggleFocusMode: () => void;
}

/**
 * Initial state factory
 */
function createInitialState(): Omit<DebuggerState, keyof DebuggerActions> {
  return {
    config: { ...DEFAULT_CONFIG },
    eventsMap: new Map(),
    events: [],
    omittedEvents: 0,
    episodes: new Map(),
    recordsMap: new Map(),
    selectedEpisodeId: null,
    selectedEventId: null,
    selectedRecordId: null,
    timeRange: [Date.now() - 60000, Date.now()],
    connectionStatus: 'disconnected',
    wsUrl: 'ws://localhost:8000/v1/stream',
    lastError: null,
    // Run state
    selectedRunId: null,
    currentRunSummary: null,
    availableRuns: [],
    viewMode: 'timeline',
    sidebarOpen: true,
    // The default graph view requires supplied pair evidence.
    edgeDisplayMode: EdgeDisplayMode.MEASURED_ONLY,      // Measured-only by default
    truthMode: TruthMode.PRODUCT,
    selectedEdgeId: null,
    edgeDrawerOpen: false,
    transitivityReport: null,
    computeLedger: null,
    edgeStatuses: new Map(),
    inferredEdges: [],
    isVerifying: false,
    verificationQueue: {
      pendingProbes: 0,
      estimatedCostEpisodes: 0,
      estimatedCostSeconds: 0,
    },
    showVerificationConfirmation: false,
    focusMode: {
      enabled: false,
      hops: 1,
      centerId: null,
    },
  };
}

/**
 * Actions type (for cleaner separation)
 */
type DebuggerActions = Pick<
  DebuggerState,
  | 'addEvents'
  | 'clearEvents'
  | 'selectEvent'
  | 'selectEpisode'
  | 'selectRecord'
  | 'setTimeRange'
  | 'setConnectionStatus'
  | 'setWsUrl'
  | 'setViewMode'
  | 'toggleSidebar'
  | 'reset'
  | 'setConfig'
  | 'setEdgeDisplayMode'
  | 'setTruthMode'
  | 'selectEdge'
  | 'toggleEdgeDrawer'
  | 'openEdgeDrawer'
  | 'closeEdgeDrawer'
  | 'setTransitivityReport'
  | 'setComputeLedgerData'
  | 'setEdgeStatuses'
  | 'setInferredEdges'
  | 'setIsVerifying'
  | 'setVerificationQueue'
  | 'setShowVerificationConfirmation'
  | 'setFocusMode'
  | 'toggleFocusMode'
  | 'selectRun'
  | 'setCurrentRunSummary'
  | 'setAvailableRuns'
>;

/**
 * Debugger Zustand store with subscribeWithSelector middleware.
 *
 * Using Map for O(1) event/record lookup, critical for 100K+ events.
 * The `subscribeWithSelector` middleware enables efficient partial subscriptions.
 *
 * @example
 * ```tsx
 * // Subscribe to specific state slice
 * const events = useDebuggerStore((state) => state.events);
 *
 * // Use selector for derived state
 * const selectedEvent = useDebuggerStore(selectSelectedEvent);
 *
 * // Call actions
 * const { addEvents, selectEvent } = useDebuggerStore.getState();
 * ```
 */
export const useDebuggerStore = create<DebuggerState>()(
  subscribeWithSelector((set, get) => ({
    ...createInitialState(),

    addEvents: (newEvents) => {
      set((state) => {
        const { maxEvents, maxRecords } = state.config;
        let omittedEvents = state.omittedEvents;
        let eventsMap = new Map(state.eventsMap);
        const episodes = new Map(state.episodes);
        let recordsMap = new Map(state.recordsMap);

        for (const event of newEvents) {
          if (eventsMap.has(event.eventId)) continue;
          // Add event
          eventsMap.set(event.eventId, event);

          // Update episode
          const episodeId = event.episodeId || 'default';
          const existing = episodes.get(episodeId);

          if (existing) {
            episodes.set(episodeId, { ...existing,
              startTime: Math.min(existing.startTime, timelineCoordinate(event)),
              endTime: Math.max(existing.endTime ?? existing.startTime, timelineCoordinate(event)),
              eventCount: existing.eventCount + 1,
            });
          } else {
            episodes.set(episodeId, {
              id: episodeId,
              startTime: timelineCoordinate(event),
              eventCount: 1,
              status: 'active',
            });
          }

          // Add records from snapshot
          if (event.snapshot) {
            for (const record of event.snapshot) {
              recordsMap.set(record.id, record);
            }
          }
        }

        // Enforce max events limit (evict oldest first by canonical order)
        if (eventsMap.size > maxEvents) {
          const sortedEvents = Array.from(eventsMap.values()).sort(
            compareCanonical
          );
          const evictCount = eventsMap.size - maxEvents;
          omittedEvents += evictCount;
          eventsMap = new Map(
            sortedEvents.slice(evictCount).map((e) => [e.eventId, e])
          );
        }

        // Enforce max records limit (evict oldest by event reference)
        if (recordsMap.size > maxRecords) {
          const recordEntries = Array.from(recordsMap.entries());
          const evictCount = recordsMap.size - maxRecords;
          recordsMap = new Map(recordEntries.slice(evictCount));
        }

        // Convert map to sorted array by canonical order
        const events = Array.from(eventsMap.values()).sort(
          compareCanonical
        );

        // Auto-adjust time range if needed
        let timeRange = state.timeRange;
        if (events.length > 0) {
          const dataStart = events.reduce((value, event) => Math.min(value, timelineCoordinate(event)), Infinity);
          const dataEnd = events.reduce((value, event) => Math.max(value, timelineCoordinate(event)), -Infinity);

          // Expand range if data exceeds current view
          if (dataStart < timeRange[0] || dataEnd > timeRange[1]) {
            const margin = Math.max(1, (dataEnd - dataStart) * 0.1);
            timeRange = [dataStart - margin, dataEnd + margin];
          }
        }

        return { eventsMap, events, episodes, recordsMap, timeRange, omittedEvents };
      });
    },

    clearEvents: () => {
      set({
        eventsMap: new Map(),
        events: [],
        omittedEvents: 0,
        episodes: new Map(),
        recordsMap: new Map(),
        selectedEventId: null,
        selectedRecordId: null,
      });
    },

    selectEvent: (eventId) => {
      const { eventsMap, selectRecord } = get();

      set({ selectedEventId: eventId });

      // Auto-select first record in event's snapshot
      if (eventId) {
        const event = eventsMap.get(eventId);
        if (event?.snapshot?.length) {
          const firstRecord = event.snapshot[0];
          if (firstRecord) {
            selectRecord(firstRecord.id);
          }
        }
      }
    },

    selectEpisode: (episodeId) => {
      set({ selectedEpisodeId: episodeId });
    },

    selectRecord: (recordId) => {
      set({ selectedRecordId: recordId });
    },

    setTimeRange: (range) => {
      set({ timeRange: range });
    },

    setConnectionStatus: (status, error) => {
      set({
        connectionStatus: status,
        lastError: error ?? null,
      });
    },

    setWsUrl: (url) => {
      set({ wsUrl: url });
    },

    setViewMode: (mode) => {
      set({ viewMode: mode });
    },

    toggleSidebar: () => {
      set((state) => ({ sidebarOpen: !state.sidebarOpen }));
    },

    reset: () => {
      set(createInitialState());
    },

    setConfig: (newConfig) => {
      set((state) => ({
        config: { ...state.config, ...newConfig },
      }));
    },

    // ============================================================================
    // Causal Graph Actions
    // ============================================================================

    setEdgeDisplayMode: (mode) => {
      set({ edgeDisplayMode: mode });
    },

    setTruthMode: (mode) => {
      set({ truthMode: mode });
    },

    selectEdge: (edgeId) => {
      set({ selectedEdgeId: edgeId });
    },

    toggleEdgeDrawer: () => {
      set((state) => ({ edgeDrawerOpen: !state.edgeDrawerOpen }));
    },

    openEdgeDrawer: () => {
      set({ edgeDrawerOpen: true });
    },

    closeEdgeDrawer: () => {
      set({ edgeDrawerOpen: false });
    },

    setTransitivityReport: (report) => {
      set({ transitivityReport: report });
    },

    setComputeLedgerData: (ledger) => {
      set({ computeLedger: ledger });
    },

    setEdgeStatuses: (statuses) => {
      set({ edgeStatuses: statuses });
    },

    setInferredEdges: (edges) => {
      set({ inferredEdges: edges });
    },

    setIsVerifying: (isVerifying) => {
      set({ isVerifying });
    },

    setVerificationQueue: (queue) => {
      set({ verificationQueue: queue });
    },

    setShowVerificationConfirmation: (show) => {
      set({ showVerificationConfirmation: show });
    },

    setFocusMode: (focusMode) => {
      set((state) => ({
        focusMode: { ...state.focusMode, ...focusMode },
      }));
    },

    toggleFocusMode: () => {
      set((state) => ({
        focusMode: { ...state.focusMode, enabled: !state.focusMode.enabled },
      }));
    },

    // ============================================================================
    // Run Actions (new v1 architecture)
    // ============================================================================

    selectRun: (runId) => {
      set({ selectedRunId: runId });
    },

    setCurrentRunSummary: (summary) => {
      set({ currentRunSummary: summary });
    },

    setAvailableRuns: (runs) => {
      set({ availableRuns: runs });
    },
  }))
);

export default useDebuggerStore;
