import {
  useRef,
  useEffect,
  useCallback,
  useState,
  useMemo,
  type MouseEvent,
} from 'react';
import { useTimelineRenderer } from './useTimelineRenderer';
import type { TimelineProps } from './types';
import type { TimeRange, TimelineLane } from '../types';

const DEFAULT_LANES: TimelineLane[] = [
  { id: 'default', label: 'Events', color: '#3b82f6' },
];

/**
 * Custom Canvas Timeline Component
 *
 * High-performance timeline visualization using HTML5 Canvas.
 * Designed for 100K+ events with virtualized rendering.
 *
 * Features:
 * - Virtualized rendering (only draws visible events)
 * - Smooth zoom/pan with requestAnimationFrame
 * - Spatial indexing for fast hit testing
 * - Lane-based event grouping
 *
 * @example
 * ```tsx
 * <Timeline
 *   events={debuggerEvents}
 *   timeRange={[Date.now() - 60000, Date.now()]}
 *   onEventClick={(event) => console.log('Clicked:', event)}
 *   onTimeRangeChange={(range) => setTimeRange(range)}
 * />
 * ```
 */
export function Timeline({
  events,
  timeRange,
  onEventClick,
  onTimeRangeChange,
  onEventHover,
  selectedEventId,
  lanes = DEFAULT_LANES,
  showMemoryEvents: _showMemoryEvents = false,
  minScale,
  maxScale,
  eventHeight = 24,
  laneGap = 8,
  className,
  style,
}: TimelineProps) {
  // TODO: Use _showMemoryEvents to filter memory-level events
  void _showMemoryEvents;
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 400 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, time: 0 });
  const animationFrameRef = useRef<number | null>(null);

  const {
    visibleEvents,
    hitTest,
    timeToX,
    zoom,
    pan,
  } = useTimelineRenderer({
    events,
    timeRange,
    width: dimensions.width,
    height: dimensions.height,
    lanes,
    eventHeight,
    laneGap,
    ...(minScale !== undefined && { minScale }),
    ...(maxScale !== undefined && { maxScale }),
    ...(onTimeRangeChange !== undefined && { onTimeRangeChange }),
  });

  // Build lane index (memoized to avoid recreation on every render)
  const laneIndex = useMemo(
    () => new Map(lanes.map((lane, i) => [lane.id, i])),
    [lanes]
  );

  const usesSteps = useMemo(
    () => events.length > 0 && events.every(event => event.timeBasis === 'step'),
    [events]
  );

  // Observe container size
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        const { width, height } = entry.contentRect;
        setDimensions({ width, height });
      }
    });

    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  // Render canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) {
      console.error('Canvas 2D context unavailable. Check browser compatibility.');
      return;
    }

    // Handle device pixel ratio for crisp rendering
    const dpr = window.devicePixelRatio || 1;
    canvas.width = dimensions.width * dpr;
    canvas.height = dimensions.height * dpr;
    ctx.scale(dpr, dpr);

    // Schedule render
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
    }

    animationFrameRef.current = requestAnimationFrame(() => {
      render(ctx, dimensions.width, dimensions.height);
    });

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [visibleEvents, dimensions, selectedEventId, timeRange, lanes, eventHeight, laneGap, usesSteps]);

  // Render function
  const render = useCallback((
    ctx: CanvasRenderingContext2D,
    width: number,
    height: number
  ) => {
    // Clear canvas
    ctx.fillStyle = getComputedStyle(ctx.canvas).getPropertyValue('--timeline-bg').trim() || '#1a1a2e';
    ctx.fillRect(0, 0, width, height);

    // Draw lane backgrounds
    lanes.forEach((_lane, i) => {
      const y = i * (eventHeight + laneGap);
      ctx.fillStyle = i % 2 === 0 ? 'rgba(255,255,255,0.02)' : 'transparent';
      ctx.fillRect(0, y, width, eventHeight);
    });

    // Draw time grid
    drawTimeGrid(ctx, width, height, timeRange, usesSteps);

    // Draw events
    for (const re of visibleEvents) {
      const x = timeToX(re.startMs);
      const laneIdx = laneIndex.get(re.lane) ?? 0;
      const y = laneIdx * (eventHeight + laneGap);

      // Event marker
      const isSelected = re.id === selectedEventId;
      const radius = isSelected ? 8 : 6;

      // Glow effect for selected
      if (isSelected) {
        ctx.shadowColor = re.color;
        ctx.shadowBlur = 10;
      }

      ctx.beginPath();
      ctx.arc(x, y + eventHeight / 2, radius, 0, Math.PI * 2);
      ctx.fillStyle = re.color;
      ctx.fill();

      if (isSelected) {
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.shadowBlur = 0;
      }

      // Label (only if zoomed in enough)
      const scale = (timeRange[1] - timeRange[0]) / width;
      if (scale < 10) { // Show labels when zoomed in
        ctx.fillStyle = '#ffffff';
        ctx.font = '11px system-ui, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(re.label, x, y + eventHeight + 12);
      }
    }

    // Draw lane labels
    ctx.fillStyle = 'rgba(255,255,255,0.6)';
    ctx.font = '12px system-ui, sans-serif';
    ctx.textAlign = 'left';
    lanes.forEach((lane, i) => {
      const y = i * (eventHeight + laneGap) + eventHeight / 2 + 4;
      ctx.fillText(lane.label, 8, y);
    });
  }, [visibleEvents, lanes, eventHeight, laneGap, timeRange, selectedEventId, timeToX, laneIndex, usesSteps]);

  // Draw time axis grid
  const drawTimeGrid = useCallback((
    ctx: CanvasRenderingContext2D,
    width: number,
    height: number,
    range: TimeRange,
    logicalSteps: boolean
  ) => {
    const [start, end] = range;
    const duration = end - start;

    // Determine appropriate grid interval
    const intervals = [
      1, 5, 10, 50, 100, 500, // milliseconds
      1000, 5000, 10000, 30000, 60000, // seconds
      300000, 600000, 1800000, 3600000, // minutes/hours
    ];

    // Find interval that gives ~10 grid lines
    let interval = intervals[0]!;
    for (const i of intervals) {
      if (duration / i < 20) {
        interval = i;
        break;
      }
    }

    // Draw grid lines
    ctx.strokeStyle = 'rgba(255,255,255,0.1)';
    ctx.lineWidth = 1;

    const firstLine = Math.ceil(start / interval) * interval;
    for (let t = firstLine; t <= end; t += interval) {
      const x = ((t - start) / duration) * width;
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }

    // Draw time labels at bottom
    ctx.fillStyle = 'rgba(255,255,255,0.4)';
    ctx.font = '10px system-ui, monospace';
    ctx.textAlign = 'center';

    for (let t = firstLine; t <= end; t += interval) {
      const x = ((t - start) / duration) * width;
      const label = logicalSteps
        ? `step ${Number(t.toFixed(2))}` : formatTimeLabel(t, interval);
      ctx.fillText(label, x, height - 4);
    }
  }, []);

  // Mouse event handlers
  const handleMouseDown = useCallback((e: MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;

    setIsDragging(true);
    setDragStart({
      x: e.clientX - rect.left,
      time: Date.now(),
    });
  }, []);

  const handleMouseMove = useCallback((e: MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;

    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    if (isDragging) {
      const deltaX = x - dragStart.x;
      pan(deltaX);
      setDragStart({ x, time: Date.now() });
    } else {
      // Hover detection
      const event = hitTest(x, y);
      onEventHover?.(event?.event ?? null);
    }
  }, [isDragging, dragStart, pan, hitTest, onEventHover]);

  const handleMouseUp = useCallback((e: MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;

    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    // Check if this was a click (short duration, minimal movement)
    const duration = Date.now() - dragStart.time;
    const distance = Math.abs(x - dragStart.x);

    if (duration < 200 && distance < 5) {
      const event = hitTest(x, y);
      if (event) {
        onEventClick?.(event.event);
      }
    }

    setIsDragging(false);
  }, [dragStart, hitTest, onEventClick]);

  const handleMouseLeave = useCallback(() => {
    setIsDragging(false);
    onEventHover?.(null);
  }, [onEventHover]);

  // Wheel zoom handler - uses native event listener for passive: false
  const handleWheel = useCallback((e: WheelEvent) => {
    e.preventDefault();
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;

    const x = e.clientX - rect.left;
    zoom(e.deltaY, x);
  }, [zoom]);

  // Attach wheel event listener with passive: false to allow preventDefault
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    canvas.addEventListener('wheel', handleWheel, { passive: false });
    return () => {
      canvas.removeEventListener('wheel', handleWheel);
    };
  }, [handleWheel]);

  // Empty state when no events
  if (events.length === 0) {
    return (
      <div
        className={className}
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          width: '100%',
          height: '100%',
          color: 'var(--timeline-text-muted, #a0a0a0)',
          fontFamily: 'system-ui, sans-serif',
          gap: 12,
          ...style,
        }}
      >
        <svg
          width="48"
          height="48"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{ opacity: 0.5 }}
        >
          <circle cx="12" cy="12" r="10" />
          <polyline points="12 6 12 12 16 14" />
        </svg>
        <p style={{ margin: 0, fontSize: 14 }}>
          No events yet. Connect to start receiving data.
        </p>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={className}
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        overflow: 'hidden',
        cursor: isDragging ? 'grabbing' : 'grab',
        ...style,
      }}
    >
      <canvas
        ref={canvasRef}
        style={{
          width: dimensions.width,
          height: dimensions.height,
          display: 'block',
        }}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseLeave}
      />
      {/* Event count overlay */}
      <div
        style={{
          position: 'absolute',
          top: 8,
          right: 8,
          padding: '4px 8px',
          borderRadius: 4,
          background: 'rgba(0,0,0,0.6)',
          color: 'rgba(255,255,255,0.8)',
          fontSize: 11,
          fontFamily: 'system-ui, sans-serif',
          pointerEvents: 'none',
        }}
      >
        {visibleEvents.length} / {events.length} events
      </div>
    </div>
  );
}

/**
 * Format time label based on interval
 */
function formatTimeLabel(timestamp: number, interval: number): string {
  const date = new Date(timestamp);

  if (interval < 1000) {
    // Milliseconds
    return `${date.getSeconds()}.${String(date.getMilliseconds()).padStart(3, '0')}`;
  } else if (interval < 60000) {
    // Seconds
    return `${date.getMinutes()}:${String(date.getSeconds()).padStart(2, '0')}`;
  } else if (interval < 3600000) {
    // Minutes
    return `${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')}`;
  } else {
    // Hours
    return `${date.getHours()}:00`;
  }
}

export default Timeline;
