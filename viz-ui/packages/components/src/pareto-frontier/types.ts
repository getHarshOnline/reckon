import type {
  DebuggerEvent,
  ParetoPoint,
  RunSummary,
  YouAreHereMarkers,
} from "../types";

/** Quantities available directly from debugger operation events. */
export type XMetric =
  "byteBudgetFraction" | "byteCount" | "tokenCount" | "slotCount";
export type YMetric = "writeShare" | "netWritesPerWrite" | "writeCount";

/** A supplied measurement's identity and optional display treatment. */
export interface FrontierAxis {
  metric: string;
  label?: string;
  format?: "number" | "percent";
}
export interface FrontierAxes {
  x: FrontierAxis;
  y: FrontierAxis;
}

/** Supplied points must name both axes; event inputs use operation quantities. */
export type FrontierSource =
  | {
      points: ParetoPoint[];
      axes: FrontierAxes;
      xMetric?: never;
      yMetric?: never;
    }
  | { points?: undefined; axes?: never; xMetric?: XMetric; yMetric?: YMetric };

/**
 * ParetoFrontier component props
 */
export type ParetoFrontierProps = FrontierSource & {
  /** Array of debugger events for analysis */
  events: DebuggerEvent[];

  /** Callback when a point is clicked */
  onPointClick?: (point: ParetoPoint) => void;

  /** Callback when a point is hovered */
  onPointHover?: (point: ParetoPoint | null) => void;

  /** Currently selected point label */
  selectedPointLabel?: string | null;

  /** Custom X-axis label (overrides default for metric) */
  xLabel?: string;

  /** Custom Y-axis label (overrides default for metric) */
  yLabel?: string;

  /** Custom chart title */
  title?: string;

  /** Show the Pareto frontier line */
  showFrontierLine?: boolean;

  /** Show dominated points */
  showDominatedPoints?: boolean;

  /** Custom class name */
  className?: string;

  /** Custom inline styles */
  style?: React.CSSProperties;

  // ========================================================================
  // "You Are Here" marker support
  // ========================================================================

  /** Current run summary for auto-populating marker A */
  runSummary?: RunSummary;

  /**
   * "You Are Here" markers showing current run and selected point.
   * - measured (A): Auto-populated from runSummary.configId match
   * - selected (B): User selection via slider or click
   */
  youAreHereMarkers?: YouAreHereMarkers;

  /**
   * Callback when user selects a different operating point (marker B).
   * Fired by slider interaction or direct click on a frontier point.
   */
  onOperatingPointSelect?: (point: ParetoPoint) => void;

  /**
   * Index of currently selected operating point on the frontier (0-indexed).
   * Controls the position of marker B / slider.
   */
  selectedOperatingPointIndex?: number;

  /**
   * Show the operating point slider control.
   * When enabled, users can slide between frontier points.
   */
  showOperatingPointSlider?: boolean;
};

/**
 * Computed Pareto analysis results
 */
export interface ParetoAnalysis {
  points: ParetoPoint[];
  frontierPoints: ParetoPoint[];
  dominatedPoints: ParetoPoint[];
}
