/** Viewer projections of the Rust laboratory model, plus event and UI contracts. */
import type {
  MemoryRecord as NativeRecord, RecordCost as NativeCost, RecordOrigin as NativeOrigin,
  UtilityEstimate as NativeUtility, CausalScore as NativeScore,
} from './generated/record';
export type { MemoryRecord as LaboratoryRecord } from './generated/record';

// ============================================================================
// Enums
// ============================================================================

/** Type of payload stored in a record */
export enum PayloadType {
  UNSPECIFIED = 0,
  OBSERVATION = 1,
  ACTION = 2,
  REWARD = 3,
  CUE = 4,
  TRACE = 5,
  REPRESENTATION = 6,
  CUSTOM = 7,
}

/** Type of memory operation */
export enum MemoryOpType {
  UNSPECIFIED = 0,
  WRITE = 1,
  READ = 2,
  PRUNE = 3,
  UPDATE_SCORE = 4,
  COMPRESS = 5,
  BUDGET_CHECK = 6,
}

/** Type of debugger event */
export enum DebuggerEventType {
  UNSPECIFIED = 0,
  EPISODE_START = 1,
  EPISODE_END = 2,
  STEP = 3,
  POLICY_CHANGE = 4,
  BUDGET_EXCEEDED = 5,
  CAUSAL_UPDATE = 6,
  CHECKPOINT = 7,
}

/** Type of causal edge */
export enum EdgeType {
  /** Pair has supplied direct-probe evidence */
  MEASURED = 'measured',
  /** Caller-supplied inference without direct probe evidence for the pair */
  INFERRED = 'inferred',
  /** Heuristic signal only (recency, usage, etc.) - not causally verified */
  PROXY = 'proxy',
}

/** Which supplied graph edges to display, with optional probe-queue details. */
export enum EdgeDisplayMode {
  /** Show only measured edges (default) */
  MEASURED_ONLY = 'measured_only',
  /** Also allow supplied inferences and enabled provenance proxies */
  INCLUDE_UNMEASURED = 'include_unmeasured',
  /** Show measured edges and any caller-supplied probe queue */
  PROBE_STATUS = 'probe_status',
}

/** Truth mode for information display */
export enum TruthMode {
  /** Research mode: show all uncertainty, costs, q-values */
  RESEARCH = 'research',
  /** Product mode: show only pairs with supplied direct-probe evidence */
  PRODUCT = 'product',
}

/** Proxy signal type */
export enum ProxySignalType {
  RECENCY = 'recency',
  USAGE = 'usage',
  REWARD_CORRELATION = 'reward_correlation',
  TEMPORAL_PROXIMITY = 'temporal_proximity',
}

/** Multiple testing correction method */
export enum MultipleTestingMethod {
  NONE = 'none',
  BONFERRONI = 'bonferroni',
  BH_FDR = 'bh_fdr',
  HOLM = 'holm',
}

/** Confidence level for an edge */
export enum ConfidenceLevel {
  WEAK = 'weak',
  MEDIUM = 'medium',
  STRONG = 'strong',
}

// ============================================================================
// Core Types
// ============================================================================

/** Resource cost of storing a record */
export interface RecordCost extends Omit<NativeCost, 'bytes' | 'tokens'> {
  bytes: number;
  tokens: number | null;
}

/** Origin and creation context of a record */
export type RecordOrigin = NativeOrigin<string[]>;

/** Utility estimates for retention decisions */
export interface UtilityEstimate extends Omit<NativeUtility, 'lastUsed'> {
  lastUsed: number;
}

/** Causal influence estimates */
export interface CausalScore {
  ablationDelta?: NativeScore['ablationDelta'];
  counterfactualDelta?: NativeScore['counterfactualDelta'];
  influenceProxy?: NativeScore['influenceProxy'];
  lastEvaluated: number;
}

/** A causal memory record stored by the CMM */
export interface MemoryRecord extends Omit<NativeRecord, 'timestamp' | 'createdAtStep' |
  'createdAtSequence' | 'payloadType' | 'payload' | 'cost' | 'provenance' |
  'utility' | 'causalScore' | 'metadata'> {
  timestamp: number;
  /**
   * Step at which this record was created (snapshot, not mutable).
   * Used for derived timeline ordering only — NOT authoritative record identity.
   * For event ordering, use DebuggerEvent.step instead.
   */
  createdAtStep?: number;
  /**
   * Sequence number at creation time (snapshot, not mutable).
   * Used for derived timeline ordering only — NOT authoritative record identity.
   * For event ordering, use DebuggerEvent.sequence instead.
   */
  createdAtSequence?: number;
  payloadType: PayloadType;
  payload?: Uint8Array;
  cost: RecordCost;
  provenance?: RecordOrigin;
  utility: UtilityEstimate;
  causalScore: CausalScore;
  metadata?: Uint8Array;
}

/** Current resource usage snapshot */
export interface ResourceUsage {
  slotCount: number;
  byteCount: number;
  tokenCount: number;
  opsInWindow: number;
}

/** Memory-specific budget for the CMM */
export interface MemoryBudget {
  maxSlots: number;
  maxBytes?: number;
  maxTokens?: number;
  maxWriteOpsPerWindow?: number;
  maxReadOpsPerWindow?: number;
  windowSize: number;
}

/** A memory operation event logged by the CMM */
export interface MemoryEvent {
  eventId: string;
  opType: MemoryOpType;
  timestamp: number;
  episodeId: string;
  recordId?: string;
  queryJson?: string;
  resultIds: string[];
  pruneReason: string;
  scoreType: string;
  oldScore?: number;
  newScore?: number;
  usageAfter?: Partial<ResourceUsage>;
  durationUs: number;
}

/** High-level debugger event */
export interface DebuggerEvent {
  /** Native kernel events carry logical steps; they do not record wall time. */
  timeBasis?: 'wall' | 'step';
  /** Complete source operation when projected from the native kernel. */
  kernelEvent?: Record<string, unknown>;
  eventId: string;
  eventType: DebuggerEventType;
  wallTimeMs: number;
  episodeId: string;
  step: number;
  /**
   * Monotonically increasing sequence number within (episodeId, step).
   * Part of canonical ordering key: (episodeId, step, sequence).
   * Optional for backward compatibility with legacy events; when missing,
   * the comparator operates in "degraded mode" using wallTimeMs as tiebreaker.
   */
  sequence?: number;
  initialBudget?: MemoryBudget;
  finalUsage?: ResourceUsage;
  totalWrites?: number;
  totalPrunes?: number;
  memoryEvents: MemoryEvent[];
  exceededDimension: string;
  snapshot: MemoryRecord[];
  metadata?: Uint8Array;
}

// ============================================================================
// Timeline-specific types
// ============================================================================

/** Time range represented as [start, end] timestamps in milliseconds */
export type TimeRange = [number, number];

/** Viewport configuration for virtualized rendering */
export interface TimelineViewport {
  /** Visible time range */
  timeRange: TimeRange;
  /** Pixel width of the viewport */
  width: number;
  /** Pixel height of the viewport */
  height: number;
  /** Pixels per millisecond (zoom level) */
  scale: number;
}

/** Lane (row) configuration for grouping events */
export interface TimelineLane {
  id: string;
  label: string;
  color?: string;
  height?: number;
}

/** Rendered event position and dimensions */
export interface TimelineEventLayout {
  eventId: string;
  x: number;
  y: number;
  width: number;
  height: number;
  lane: string;
}

// ============================================================================
// Causal Graph types
// ============================================================================

/** Node in the causal graph */
export interface CausalNode {
  id: string;
  label: string;
  type: PayloadType;
  utility: number;
  timestamp: number;
  episodeId: string;
  /** Logical step within episode (canonical ordering) */
  step?: number;
  /** Sequence number within step (tiebreaker for async events) */
  sequence?: number;
}

/** Edge in the causal graph */
export interface CausalEdge {
  id: string;
  source: string;
  target: string;
  weight?: number;
  edgeType: EdgeType;
}

// ============================================================================
// Edge Semantics & Probe Types
// ============================================================================

/** Detailed probe evidence for a measured edge */
export interface ProbeEvidence {
  /** P-value from the statistical test */
  pValue: number;
  /** Q-value (adjusted p-value after multiple testing correction) */
  qValue: number;
  /** Effect size (Cohen's d, correlation, etc.) */
  effectSize: number;
  /** Sample size (number of trials) */
  n: number;
  /** Multiple testing correction method used */
  correctionMethod: MultipleTestingMethod;
  /** Random seed for reproducibility */
  seed?: number;
  /** Test type (e.g., 'mann_whitney', 't_test', 'permutation') */
  testType: string;
  /** Timestamp when probe was run */
  timestamp: number;
  /** Episodes spent on this probe */
  episodesUsed: number;
  /** Wall time in seconds */
  wallTimeSeconds: number;
  /** Confidence interval lower bound */
  ciLower?: number;
  /** Confidence interval upper bound */
  ciUpper?: number;
}

/** Proxy signal information */
export interface ProxyInfo {
  /** Type of proxy signal */
  signalType: ProxySignalType;
  /** Strength of the proxy signal (0-1) */
  strength: number;
  /** When this proxy was computed */
  computedAt: number;
  /** Additional context */
  description?: string;
}

/** Full edge status with all semantics */
export interface EdgeStatus {
  /** Edge type classification */
  edgeType: EdgeType;
  /** Source node ID */
  source: string;
  /** Target node ID */
  target: string;
  /** For measured edges: probe evidence */
  probeEvidence?: ProbeEvidence;
  /** For proxy edges: proxy info */
  proxyInfo?: ProxyInfo;
  /** For inferred edges: the path that implies this edge */
  inferredPath?: string[];
  /** Estimated cost to verify this edge (episodes) */
  verificationCostEpisodes?: number;
  /** Estimated cost to verify this edge (seconds) */
  verificationCostSeconds?: number;
  /** Confidence level badge */
  confidenceLevel?: ConfidenceLevel;
  /** Historical probe data for sparkline */
  probeHistory?: ProbeEvidence[];
  /** Whether this edge has insufficient statistical power */
  insufficientPower?: boolean;
  /** Power analysis result */
  statisticalPower?: number;
}

// ============================================================================
// Transitivity Violations
// ============================================================================

/** Status of a single edge in a violation triple */
export interface ViolationEdgeStatus {
  /** Source of the edge */
  source: string;
  /** Target of the edge */
  target: string;
  /** Whether the edge was tested */
  tested: boolean;
  /** Edge holds (relation confirmed) */
  holds: boolean;
  /** P-value if tested */
  pValue?: number;
  /** Q-value if tested */
  qValue?: number;
  /** Effect size if tested */
  effectSize?: number;
  /** Sample size if tested */
  n?: number;
  /** Estimated cost to verify if not tested */
  estimatedCostEpisodes?: number;
}

/**
 * Classification category for violations.
 * Helps users understand the likely cause and appropriate action.
 */
export type ViolationCategory =
  | 'type_i_suspect'    // False positive likely - edges near threshold (q-value 0.04-0.06)
  | 'low_power_suspect' // False negative likely - A->C unverified or low n
  | 'budget_limited'    // Verification skipped due to constraints
  | 'unknown';          // Unable to classify

/** A transitivity violation triple: A->B, B->C holds but A->C fails */
export interface TransitivityViolation {
  /** Unique ID for this violation */
  id: string;
  /** First node in the triple */
  nodeA: string;
  /** Middle node in the triple */
  nodeB: string;
  /** Third node in the triple */
  nodeC: string;
  /** Edge A->B status */
  edgeAB: ViolationEdgeStatus;
  /** Edge B->C status */
  edgeBC: ViolationEdgeStatus;
  /** Edge A->C status (the failing/missing edge) */
  edgeAC: ViolationEdgeStatus;
  /** Severity score (higher = more concerning) */
  severity: number;
  /** Category of violation */
  category: 'measured_failure' | 'untested' | 'borderline' | 'power_issue';
  /** Classification label for display */
  violationCategory?: ViolationCategory;
  /** Timestamp when violation was detected */
  detectedAt: number;
  /** Suggested action to resolve */
  suggestedAction: string;
}

/** Transitivity report from validation */
export interface TransitivityReport {
  /** Total violations detected */
  totalViolations: number;
  /** Violations by category */
  violationsByCategory: Record<string, number>;
  /** All violations */
  violations: TransitivityViolation[];
  /** Timestamp of report generation */
  generatedAt: number;
  /** Number of edges checked */
  edgesChecked: number;
  /** Number of triples checked */
  triplesChecked: number;
}

// ============================================================================
// Probe Cost & Compute Ledger
// ============================================================================

/** Summary of probe costs */
export interface ProbeCostSummary {
  /** Total episodes used for probing */
  probeEpisodes: number;
  /** Total episodes used for acting */
  baseEpisodes: number;
  /** Probe overhead ratio: probeEpisodes / (baseEpisodes + probeEpisodes) */
  probeOverheadRatio: number;
  /** Total wall time for probes (seconds) */
  probeWallTimeSeconds: number;
  /** Total wall time for acting (seconds) */
  baseWallTimeSeconds: number;
  /** Reward per total episode */
  rewardPerTotalEpisode: number;
  /** Reward per wall time second */
  rewardPerWallTimeSecond: number;
  /** Breakdown by edge */
  edgeCosts: Map<string, {
    episodes: number;
    wallTimeSeconds: number;
    probeCount: number;
  }>;
}

/** Compute ledger data for HUD display */
export interface ComputeLedgerData {
  /** Base episodes (acting) */
  baseEpisodes: number;
  /** Probe episodes (evaluation) */
  probeEpisodes: number;
  /** Probe overhead ratio */
  probeOverheadRatio: number;
  /** Wall time split (base/probe in seconds) */
  wallTimeSplit: {
    base: number;
    probe: number;
  };
  /** Total reward accumulated */
  totalReward: number;
  /** Reward per total episode */
  rewardPerTotalEpisode: number;
  /** Reward per wall time second */
  rewardPerWallTimeSecond: number;
  /** Estimated cost for pending verifications */
  pendingVerificationCost: {
    episodes: number;
    seconds: number;
  };
  /** Last update timestamp */
  lastUpdated: number;
}

// ============================================================================
// Failure Debugging
// ============================================================================

/** Information about a failed episode for debugging */
export interface FailureDebugInfo {
  /** Episode ID */
  episodeId: string;
  /** Step where failure occurred */
  failureStep: number;
  /** Records that were retrieved */
  retrievedRecords: string[];
  /** Which retrieved records were proxy-only */
  proxyOnlyRecords: string[];
  /** Causal edges relevant to retrieval */
  relevantEdges: EdgeStatus[];
  /** Inferred/unverified edges touching these records */
  unverifiedEdges: EdgeStatus[];
  /** Transitivity violations touching these records */
  relevantViolations: TransitivityViolation[];
  /** Suggested actions to resolve */
  suggestedActions: DebugSuggestion[];
}

/** A suggested action for debugging */
export interface DebugSuggestion {
  /** Action type */
  type: 'verify_edge' | 'increase_n' | 'change_correction_method' | 'prune_proxy';
  /** Human-readable description */
  description: string;
  /** Estimated cost in episodes */
  estimatedCostEpisodes: number;
  /** Priority (higher = more important) */
  priority: number;
  /** Edge ID if relevant */
  edgeId?: string;
  /** Parameters for the action */
  params?: Record<string, unknown>;
}

// ============================================================================
// Pareto Frontier types
// ============================================================================

/** A finite cost/outcome pair with the identity of both measured quantities. */
export interface ParetoPoint {
  /** X-axis value (cost metric - lower is better) */
  x: number;
  /** Y-axis value (quality metric - higher is better) */
  y: number;
  /** X-axis metric name (e.g., "probe_overhead_ratio") */
  xMetric: string;
  /** Y-axis metric name (e.g., "reward_per_total_episode") */
  yMetric: string;
  /** Whether this point is on the Pareto frontier */
  isPareto: boolean;
  /** Human-readable label */
  label?: string;
  /** Associated episode ID */
  episodeId?: string;
  /** Additional metadata (policy config, full results, etc.) */
  metadata?: Record<string, unknown>;

}

/** Pareto point with uncertainty estimates from multiple trials */
export interface ParetoPointWithUncertainty extends ParetoPoint {
  /** Standard deviation of x values across trials */
  xStd: number;
  /** Standard deviation of y values across trials */
  yStd: number;
  /** Number of trials used to compute statistics */
  trialCount: number;
}

/** RunSummary provides the "You Are Here" context */
export interface RunSummary {
  /** Unique run identifier */
  runId: string;
  /** config_id = hash(normalized config JSON) - determines marker A */
  configId: string;
  /** Full config dict for UI display + "apply this config" action */
  config: Record<string, unknown>;
  /** Pareto coordinates for this run */
  paretoPoint: ParetoPoint;
  /** Metrics decoded from the historical v1 summary shape */
  metrics: HistoricalRunMetricsV1;
  /** Schema version for core API */
  coreApiVersion: string;
  /** Schema version for events */
  eventsSchemaVersion: string;
}

/** Historical v1 fields; their names do not establish the producer's formulas. */
export interface HistoricalRunMetricsV1 {
  // Task-facing
  meanReturn?: number;
  successRate?: number;
  rewardPerTotalEpisode?: number;
  // Retained historical labels, not current task or record metrics.
  causalPrecision?: number;
  usefulMemoryRate?: number;
  // Cost-facing
  probeOverheadRatio?: number;
  baseEpisodes?: number;
  probeEpisodes?: number;
  probeWallTimeS?: number;
  // Extensible
  extra?: Record<string, number>;
}

/** "You Are Here" markers for Pareto frontier */
export interface YouAreHereMarkers {
  /** Marker A: current run - auto-selected by matching RunSummary.configId */
  measured: ParetoPoint;
  /** Marker B: user selection via slider */
  selected: ParetoPoint;
}

/** Frontier stability metrics across trial runs */
export interface FrontierStability {
  /** Jaccard similarity between frontier label sets (0-1) */
  jaccardIndex: number;
  /** Fraction of points that changed between runs (0-1) */
  churnRate: number;
  /** Labels of points on the reference frontier */
  referenceFrontier: string[];
}

// ============================================================================
// Color utilities
// ============================================================================

/** Default color palette for payload types */
export const PAYLOAD_TYPE_COLORS: Record<PayloadType, string> = {
  [PayloadType.UNSPECIFIED]: '#71717a',
  [PayloadType.OBSERVATION]: '#3b82f6',
  [PayloadType.ACTION]: '#f59e0b',
  [PayloadType.REWARD]: '#10b981',
  [PayloadType.CUE]: '#8b5cf6',
  [PayloadType.TRACE]: '#6366f1',
  [PayloadType.REPRESENTATION]: '#ec4899',
  [PayloadType.CUSTOM]: '#71717a',
};

/** Default color palette for memory operations */
export const MEMORY_OP_COLORS: Record<MemoryOpType, string> = {
  [MemoryOpType.UNSPECIFIED]: '#71717a',
  [MemoryOpType.WRITE]: '#10b981',
  [MemoryOpType.READ]: '#3b82f6',
  [MemoryOpType.PRUNE]: '#ef4444',
  [MemoryOpType.UPDATE_SCORE]: '#f59e0b',
  [MemoryOpType.COMPRESS]: '#8b5cf6',
  [MemoryOpType.BUDGET_CHECK]: '#6366f1',
};
