/**
 * @rtepl/reckon-components
 *
 * Reusable visualization components for Reckon Memory Debugger.
 * These components are stateless and receive data via props.
 *
 * @packageDocumentation
 */

// Timeline - Custom Canvas high-performance timeline
export { Timeline, useTimelineRenderer } from './timeline';
export type { TimelineProps, RenderableEvent, TimelineRendererState } from './timeline';

// Causal Graph - React Flow wrapper for DAG visualization
export { CausalGraph, collectGraphRecords, projectCausalEdges } from './causal-graph';
export type { CausalGraphProps, GraphData } from './causal-graph';

// Pareto Frontier - Plotly wrapper for budget/performance tradeoffs
export { ParetoFrontier } from './pareto-frontier';
export type { ParetoFrontierProps, ParetoAnalysis, FrontierAxis, FrontierAxes } from './pareto-frontier';

// Edge Drawer - Side panel for edge details
export { EdgeDrawer } from './edge-drawer';
export type { EdgeDrawerProps } from './edge-drawer';

// Violations Panel - Transitivity violations display
export { ViolationsPanel } from './violations-panel';
export type { ViolationsPanelProps, ViolationFilters } from './violations-panel';

// Compute Ledger - Probe cost HUD
export { ComputeLedger } from './compute-ledger';
export type { ComputeLedgerProps } from './compute-ledger';

// Controls - Edge display, truth mode switch, edge legend
export { EdgeDisplayControl, TruthModeSwitch, EdgeLegend } from './controls';
export type { EdgeDisplayControlProps, TruthModeSwitchProps, EdgeLegendProps } from './controls';

// Shared utilities
export * from './shared';

// Canonical ordering utilities
export {
  compareCanonical,
  sortedCanonical,
  sortCanonical,
  hasCanonicalFields,
  isDegradedOrdering,
  analyzeOrdering,
} from './utils/canonicalOrder';
export type {
  CanonicallyOrderable,
  OrderingMode,
  OrderingAnalysis,
} from './utils/canonicalOrder';

// Types
export * from './types';

export { timelineCoordinate } from './utils/eventTime';
export { recordScoreSource, proxyOnlyRecordIds } from './utils/recordScores';
