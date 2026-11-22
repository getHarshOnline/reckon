import { timelineCoordinate } from '../utils/eventTime';
import { useMemo, useCallback, useRef } from 'react';
import type { TimeRange, TimelineViewport, DebuggerEvent, TimelineLane } from '../types';
import { DebuggerEventType, PAYLOAD_TYPE_COLORS, PayloadType } from '../types';
import type { RenderableEvent, TimelineRendererState } from './types';

interface UseTimelineRendererOptions {
  events: DebuggerEvent[];
  timeRange: TimeRange;
  width: number;
  height: number;
  lanes?: TimelineLane[];
  eventHeight?: number;
  laneGap?: number;
  minScale?: number;
  maxScale?: number;
  onTimeRangeChange?: (range: TimeRange) => void;
}

const DEFAULT_EVENT_HEIGHT = 24;
const DEFAULT_LANE_GAP = 8;
const DEFAULT_MIN_SCALE = 0.01; // 100px = 1ms (very zoomed in)
const DEFAULT_MAX_SCALE = 1000; // 1px = 1000ms (very zoomed out)

/**
 * Format event type as a display label
 */
function formatEventType(type: DebuggerEventType): string {
  const labels: Record<DebuggerEventType, string> = {
    [DebuggerEventType.UNSPECIFIED]: 'Unknown',
    [DebuggerEventType.EPISODE_START]: 'Start',
    [DebuggerEventType.EPISODE_END]: 'End',
    [DebuggerEventType.STEP]: 'Step',
    [DebuggerEventType.POLICY_CHANGE]: 'Policy',
    [DebuggerEventType.BUDGET_EXCEEDED]: 'Budget!',
    [DebuggerEventType.CAUSAL_UPDATE]: 'Causal',
    [DebuggerEventType.CHECKPOINT]: 'Checkpoint',
  };
  return labels[type] ?? `Type ${type}`;
}

/**
 * Get color for an event based on its type and content
 */
function getEventColor(event: DebuggerEvent): string {
  // Budget exceeded events are red
  if (event.eventType === DebuggerEventType.BUDGET_EXCEEDED) {
    return '#ef4444';
  }

  // Episode start/end are distinct
  if (event.eventType === DebuggerEventType.EPISODE_START) {
    return '#10b981';
  }
  if (event.eventType === DebuggerEventType.EPISODE_END) {
    return '#f59e0b';
  }

  // Step events - color by primary payload type in snapshot
  if (event.snapshot && event.snapshot.length > 0) {
    const record = event.snapshot[0];
    if (record) {
      return PAYLOAD_TYPE_COLORS[record.payloadType] ?? PAYLOAD_TYPE_COLORS[PayloadType.UNSPECIFIED];
    }
  }

  // Default blue for other events
  return '#3b82f6';
}

/**
 * Hook for managing timeline rendering state and calculations.
 * Handles virtualization, coordinate transforms, and hit testing.
 */
export function useTimelineRenderer({
  events,
  timeRange,
  width,
  height,
  lanes,
  eventHeight = DEFAULT_EVENT_HEIGHT,
  laneGap = DEFAULT_LANE_GAP,
  minScale = DEFAULT_MIN_SCALE,
  maxScale = DEFAULT_MAX_SCALE,
  onTimeRangeChange,
}: UseTimelineRendererOptions): TimelineRendererState {
  const [startTime, endTime] = timeRange;
  const duration = endTime - startTime;
  // Guard against division by zero: use 1 as fallback for scale calculation
  const scale = width > 0 ? duration / width : 1; // ms per pixel

  // Build lane index for fast lookup
  const laneIndex = useMemo(() => {
    const index = new Map<string, number>();
    if (lanes) {
      lanes.forEach((lane, i) => index.set(lane.id, i));
    }
    return index;
  }, [lanes]);

  // Compute viewport
  const viewport: TimelineViewport = useMemo(() => ({
    timeRange,
    width,
    height,
    scale,
  }), [timeRange, width, height, scale]);

  // Convert events to renderable format and cull invisible ones
  const renderableEvents = useMemo((): RenderableEvent[] => {
    return events
      .map((event): RenderableEvent => {
        const lane = event.episodeId || 'default';
        return {
          id: event.eventId,
          event,
          startMs: timelineCoordinate(event),
          endMs: timelineCoordinate(event) + 1, // Point events
          lane,
          color: getEventColor(event),
          label: formatEventType(event.eventType),
        };
      })
      .filter((re) => {
        // Cull events outside visible range (with some margin)
        const margin = duration * 0.1;
        return re.endMs >= startTime - margin && re.startMs <= endTime + margin;
      })
      .sort((a, b) => a.startMs - b.startMs);
  }, [events, startTime, endTime, duration]);

  // Spatial index for hit testing (simple grid-based for 100K+ events)
  const spatialIndexRef = useRef<Map<string, RenderableEvent[]>>(new Map());

  // Build spatial index
  useMemo(() => {
    const index = new Map<string, RenderableEvent[]>();
    const cellSize = 10; // pixels

    for (const re of renderableEvents) {
      // Guard against zero duration: default to x=0 when duration is 0
      const x = duration > 0 ? Math.floor(((re.startMs - startTime) / duration) * width / cellSize) : 0;
      const laneIdx = laneIndex.get(re.lane) ?? 0;
      const y = Math.floor((laneIdx * (eventHeight + laneGap)) / cellSize);
      const key = `${x},${y}`;

      const cell = index.get(key);
      if (cell) {
        cell.push(re);
      } else {
        index.set(key, [re]);
      }
    }

    spatialIndexRef.current = index;
  }, [renderableEvents, startTime, duration, width, laneIndex, eventHeight, laneGap]);

  // Coordinate transforms
  const timeToX = useCallback((timeMs: number): number => {
    // Guard against zero duration: return 0 when duration is 0
    return duration > 0 ? ((timeMs - startTime) / duration) * width : 0;
  }, [startTime, duration, width]);

  const xToTime = useCallback((x: number): number => {
    // Guard against zero width: return startTime when width is 0
    return width > 0 ? startTime + (x / width) * duration : startTime;
  }, [startTime, width, duration]);

  // Hit testing
  const hitTest = useCallback((x: number, y: number): RenderableEvent | null => {
    const cellSize = 10;
    const cellX = Math.floor(x / cellSize);
    const cellY = Math.floor(y / cellSize);

    // Check cell and neighbors
    for (let dx = -1; dx <= 1; dx++) {
      for (let dy = -1; dy <= 1; dy++) {
        const key = `${cellX + dx},${cellY + dy}`;
        const cell = spatialIndexRef.current.get(key);
        if (cell) {
          for (const re of cell) {
            const eventX = timeToX(re.startMs);
            const laneIdx = laneIndex.get(re.lane) ?? 0;
            const eventY = laneIdx * (eventHeight + laneGap);

            // Check if point is within event bounds
            if (
              x >= eventX - 6 &&
              x <= eventX + 6 &&
              y >= eventY &&
              y <= eventY + eventHeight
            ) {
              return re;
            }
          }
        }
      }
    }

    return null;
  }, [timeToX, laneIndex, eventHeight, laneGap]);

  // Zoom handler
  const zoom = useCallback((delta: number, centerX: number): void => {
    if (!onTimeRangeChange || width <= 0) return;

    const centerTime = xToTime(centerX);
    const zoomFactor = delta > 0 ? 1.1 : 0.9;
    const newScale = Math.max(minScale, Math.min(maxScale, scale * zoomFactor));
    const newDuration = newScale * width;

    // Maintain center point
    const ratio = centerX / width;
    const newStart = centerTime - newDuration * ratio;
    const newEnd = newStart + newDuration;

    onTimeRangeChange([newStart, newEnd]);
  }, [xToTime, scale, width, minScale, maxScale, onTimeRangeChange]);

  // Pan handler
  const pan = useCallback((deltaX: number): void => {
    if (!onTimeRangeChange || width <= 0) return;

    const deltaTime = (deltaX / width) * duration;
    onTimeRangeChange([startTime - deltaTime, endTime - deltaTime]);
  }, [width, duration, startTime, endTime, onTimeRangeChange]);

  return {
    viewport,
    visibleEvents: renderableEvents,
    hitTest,
    timeToX,
    xToTime,
    zoom,
    pan,
  };
}
