import type { DebuggerEvent, TimeRange, TimelineLane, TimelineViewport } from '../types';

/**
 * Timeline component props
 */
export interface TimelineProps {
  /** Array of debugger events to display */
  events: DebuggerEvent[];

  /** Visible time range [start, end] in milliseconds */
  timeRange: TimeRange;

  /** Callback when an event is clicked */
  onEventClick?: (event: DebuggerEvent) => void;

  /** Callback when the time range changes (zoom/pan) */
  onTimeRangeChange?: (range: TimeRange) => void;

  /** Callback when an event is hovered */
  onEventHover?: (event: DebuggerEvent | null) => void;

  /** Currently selected event ID */
  selectedEventId?: string | null;

  /** Lane configuration for grouping */
  lanes?: TimelineLane[];

  /** Show memory events within debugger events */
  showMemoryEvents?: boolean;

  /** Minimum zoom level (ms per pixel) */
  minScale?: number;

  /** Maximum zoom level (ms per pixel) */
  maxScale?: number;

  /** Event height in pixels */
  eventHeight?: number;

  /** Gap between lanes in pixels */
  laneGap?: number;

  /** Custom class name */
  className?: string;

  /** Custom inline styles */
  style?: React.CSSProperties;
}

/**
 * Internal event data for rendering
 */
export interface RenderableEvent {
  id: string;
  event: DebuggerEvent;
  startMs: number;
  endMs: number;
  lane: string;
  color: string;
  label: string;
}

/**
 * useTimelineRenderer hook return type
 */
export interface TimelineRendererState {
  /** Current viewport state */
  viewport: TimelineViewport;

  /** Visible events after culling */
  visibleEvents: RenderableEvent[];

  /** Event at given coordinates, if any */
  hitTest: (x: number, y: number) => RenderableEvent | null;

  /** Convert timestamp to x coordinate */
  timeToX: (timeMs: number) => number;

  /** Convert x coordinate to timestamp */
  xToTime: (x: number) => number;

  /** Handle zoom */
  zoom: (delta: number, centerX: number) => void;

  /** Handle pan */
  pan: (deltaX: number) => void;
}
