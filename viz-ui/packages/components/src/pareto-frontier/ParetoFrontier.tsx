import { useMemo, useCallback } from 'react';
import Plot from 'react-plotly.js';
import type { PlotParams } from 'react-plotly.js';

// Extract types from PlotParams
type Data = PlotParams['data'][number];
type Layout = PlotParams['layout'];
type PlotMouseEvent = Parameters<NonNullable<PlotParams['onClick']>>[0];

import type { ParetoFrontierProps, FrontierSource } from './types';
import type { ParetoPoint, ParetoPointWithUncertainty } from '../types';

import { getX, getY, requirePointAxes } from './analysis';
import { prepareFrontier } from './axes';

/**
 * Check if a point has uncertainty data (is ParetoPointWithUncertainty)
 */
function hasUncertainty(p: ParetoPoint): p is ParetoPointWithUncertainty {
  return 'trialCount' in p && (p as ParetoPointWithUncertainty).trialCount > 1;
}

/**
 * Pareto Frontier Component
 *
 * Visualizes the tradeoff between resource budget and performance.
 * Points on the frontier represent configurations where you cannot
 * improve one metric without worsening the other.
 *
 * Uses Plotly.js for interactive scatter plots.
 *
 * @example
 * ```tsx
 * <ParetoFrontier
 *   events={debuggerEvents}
 *   onPointClick={(point) => console.log('Selected:', point)}
 * />
 * ```
 */
export function ParetoFrontier({
  events,
  points: precomputedPoints,
  axes,
  onPointClick,
  onPointHover,
  selectedPointLabel,
  xMetric,
  yMetric,
  xLabel,
  yLabel,
  title,
  showFrontierLine = true,
  showDominatedPoints = true,
  className,
  style,
  // "You Are Here" marker support
  runSummary,
  youAreHereMarkers,
  onOperatingPointSelect,
  selectedOperatingPointIndex,
  showOperatingPointSlider = false,
}: ParetoFrontierProps) {
  const { analysis, axes: resolvedAxes } = useMemo(() => {
    const source: FrontierSource = precomputedPoints !== undefined
      ? { points: precomputedPoints, axes: axes! }
      : { xMetric: xMetric ?? 'byteBudgetFraction', yMetric: yMetric ?? 'writeShare' };
    return prepareFrontier(events, source);
  }, [events, precomputedPoints, axes, xMetric, yMetric]);
  const effectiveXLabel = xLabel ?? resolvedAxes.x.label;
  const effectiveYLabel = yLabel ?? resolvedAxes.y.label;
  const effectiveTitle = title ?? `${effectiveYLabel} vs ${effectiveXLabel}`;
  const xIsPercent = resolvedAxes.x.format === 'percent';
  const yIsPercent = resolvedAxes.y.format === 'percent';

  // Build Plotly traces
  const traces = useMemo((): Data[] => {
    const result: Data[] = [];

    // Helper to format values using the new x/y naming
    const formatX = (p: ParetoPoint) => xIsPercent ? getX(p) * 100 : getX(p);
    const formatY = (p: ParetoPoint) => yIsPercent ? getY(p) * 100 : getY(p);
    const xUnit = xIsPercent ? '%' : '';
    const yUnit = yIsPercent ? '%' : '';

    // Check if any points have uncertainty data
    const pointsWithUncertainty = analysis.frontierPoints.filter(hasUncertainty);
    const showErrorBars = pointsWithUncertainty.length > 0;

    // Frontier points
    if (analysis.frontierPoints.length > 0) {
      const frontierTrace: Data = {
        type: 'scatter',
        mode: 'markers',
        name: 'Pareto Optimal',
        x: analysis.frontierPoints.map(formatX),
        y: analysis.frontierPoints.map(formatY),
        text: analysis.frontierPoints.map((p) => p.label ?? ''),
        hovertemplate:
          '<b>%{text}</b><br>' +
          `${effectiveXLabel}: %{x:.1f}${xUnit}<br>` +
          `${effectiveYLabel}: %{y:.1f}${yUnit}<extra></extra>`,
        marker: {
          size: 12,
          color: '#10b981',
          symbol: 'diamond',
          line: {
            color: '#ffffff',
            width: selectedPointLabel
              ? analysis.frontierPoints.map((p) =>
                  p.label === selectedPointLabel ? 3 : 1
                )
              : 1,
          },
        },
      };

      // Add error bars if points have uncertainty data (trialCount > 1)
      if (showErrorBars) {
        (frontierTrace as Record<string, unknown>).error_x = {
          type: 'data',
          array: analysis.frontierPoints.map((p) =>
            hasUncertainty(p) ? (xIsPercent ? p.xStd * 100 : p.xStd) : 0
          ),
          visible: true,
          color: '#10b981',
          thickness: 1.5,
          width: 4,
        };
        (frontierTrace as Record<string, unknown>).error_y = {
          type: 'data',
          array: analysis.frontierPoints.map((p) =>
            hasUncertainty(p) ? (yIsPercent ? p.yStd * 100 : p.yStd) : 0
          ),
          visible: true,
          color: '#10b981',
          thickness: 1.5,
          width: 4,
        };
      }

      result.push(frontierTrace);
    }

    // Dominated points
    if (showDominatedPoints && analysis.dominatedPoints.length > 0) {
      const dominatedTrace: Data = {
        type: 'scatter',
        mode: 'markers',
        name: 'Dominated',
        x: analysis.dominatedPoints.map(formatX),
        y: analysis.dominatedPoints.map(formatY),
        text: analysis.dominatedPoints.map((p) => p.label ?? ''),
        hovertemplate:
          '<b>%{text}</b><br>' +
          `${effectiveXLabel}: %{x:.1f}${xUnit}<br>` +
          `${effectiveYLabel}: %{y:.1f}${yUnit}<extra></extra>`,
        marker: {
          size: 8,
          color: '#6b7280',
          symbol: 'circle',
          opacity: 0.6,
        },
      };

      // Add error bars for dominated points with uncertainty
      const dominatedWithUncertainty = analysis.dominatedPoints.filter(hasUncertainty);
      if (dominatedWithUncertainty.length > 0) {
        (dominatedTrace as Record<string, unknown>).error_x = {
          type: 'data',
          array: analysis.dominatedPoints.map((p) =>
            hasUncertainty(p) ? (xIsPercent ? p.xStd * 100 : p.xStd) : 0
          ),
          visible: true,
          color: '#6b7280',
          thickness: 1,
          width: 3,
        };
        (dominatedTrace as Record<string, unknown>).error_y = {
          type: 'data',
          array: analysis.dominatedPoints.map((p) =>
            hasUncertainty(p) ? (yIsPercent ? p.yStd * 100 : p.yStd) : 0
          ),
          visible: true,
          color: '#6b7280',
          thickness: 1,
          width: 3,
        };
      }

      result.push(dominatedTrace);
    }

    // Frontier line
    if (showFrontierLine && analysis.frontierPoints.length > 1) {
      // Sort frontier by x for proper line drawing
      const sortedFrontier = [...analysis.frontierPoints].sort(
        (a, b) => getX(a) - getX(b)
      );

      result.push({
        type: 'scatter',
        mode: 'lines',
        name: 'Frontier',
        x: sortedFrontier.map(formatX),
        y: sortedFrontier.map(formatY),
        line: {
          color: '#10b981',
          width: 2,
          dash: 'dot',
        },
        hoverinfo: 'skip',
      });
    }

    // "You Are Here" Marker A: Current run (auto-populated from RunSummary.configId)
    // Find the point matching the current run's configId
    const markerAPoint = runSummary
      ? analysis.points.find(p => p.label === runSummary.configId) ?? runSummary.paretoPoint
      : youAreHereMarkers?.measured;

    if (markerAPoint) {
      requirePointAxes(markerAPoint, resolvedAxes.x.metric, resolvedAxes.y.metric);
      result.push({
        type: 'scatter',
        mode: 'text+markers',  // Use 'text+markers' instead of 'markers+text'
        name: 'You Are Here (A)',
        x: [formatX(markerAPoint)],
        y: [formatY(markerAPoint)],
        text: ['A'],
        textposition: 'top center',
        textfont: { color: '#f59e0b', size: 14 },
        hovertemplate:
          `<b>Current Run</b><br>` +
          `${effectiveXLabel}: %{x:.1f}${xUnit}<br>` +
          `${effectiveYLabel}: %{y:.1f}${yUnit}<extra></extra>`,
        marker: {
          size: 18,
          color: '#f59e0b',
          symbol: 'star',
          line: { color: '#ffffff', width: 2 },
        },
      });
    }

    // "You Are Here" Marker B: User selection (slider or click)
    const markerBPoint = selectedOperatingPointIndex !== undefined && analysis.frontierPoints.length > 0
      ? analysis.frontierPoints[Math.min(selectedOperatingPointIndex, analysis.frontierPoints.length - 1)]
      : youAreHereMarkers?.selected;

    if (markerBPoint && markerBPoint !== markerAPoint) {
      requirePointAxes(markerBPoint, resolvedAxes.x.metric, resolvedAxes.y.metric);
      result.push({
        type: 'scatter',
        mode: 'text+markers',  // Use 'text+markers' instead of 'markers+text'
        name: 'Selected (B)',
        x: [formatX(markerBPoint)],
        y: [formatY(markerBPoint)],
        text: ['B'],
        textposition: 'top center',
        textfont: { color: '#3b82f6', size: 14 },
        hovertemplate:
          `<b>Selected Point</b><br>` +
          `${effectiveXLabel}: %{x:.1f}${xUnit}<br>` +
          `${effectiveYLabel}: %{y:.1f}${yUnit}<extra></extra>`,
        marker: {
          size: 16,
          color: '#3b82f6',
          symbol: 'circle',
          line: { color: '#ffffff', width: 2 },
        },
      });
    }

    return result;
  }, [analysis, showDominatedPoints, showFrontierLine, selectedPointLabel, xIsPercent, yIsPercent, effectiveXLabel, effectiveYLabel, runSummary, youAreHereMarkers, selectedOperatingPointIndex, resolvedAxes]);

  // Layout configuration
  const layout = useMemo((): Partial<Layout> => {
    // Compute axis ranges based on data using new x/y naming
    const allPoints = [...analysis.frontierPoints, ...analysis.dominatedPoints];
    const xMax = allPoints.length > 0
      ? Math.max(...allPoints.map(p => xIsPercent ? getX(p) * 100 : getX(p)))
      : 100;
    const yMax = allPoints.length > 0
      ? Math.max(...allPoints.map(p => yIsPercent ? getY(p) * 100 : getY(p)))
      : 100;

    return {
      autosize: true,
      margin: { l: 60, r: 20, t: 40, b: 60 },
      paper_bgcolor: 'transparent',
      plot_bgcolor: 'rgba(0,0,0,0.2)',
      font: {
        family: 'system-ui, sans-serif',
        color: '#a0a0a0',
      },
      title: {
        text: effectiveTitle,
        font: { size: 14, color: '#e0e0e0' },
      },
      xaxis: {
        title: { text: effectiveXLabel },
        range: [Math.min(0, ...allPoints.map(p => xIsPercent ? getX(p) * 100 : getX(p))), Math.max(1, xMax * 1.1)],
        gridcolor: 'rgba(255,255,255,0.1)',
        zerolinecolor: 'rgba(255,255,255,0.2)',
      },
      yaxis: {
        title: { text: effectiveYLabel },
        range: [Math.min(0, ...allPoints.map(p => yIsPercent ? getY(p) * 100 : getY(p))), Math.max(1, yMax * 1.1)],
        gridcolor: 'rgba(255,255,255,0.1)',
        zerolinecolor: 'rgba(255,255,255,0.2)',
      },
      legend: {
        orientation: 'h',
        y: -0.15,
        x: 0.5,
        xanchor: 'center',
      },
      hovermode: 'closest',
    };
  }, [analysis, xIsPercent, yIsPercent, effectiveTitle, effectiveXLabel, effectiveYLabel]);

  // Handle click
  const handleClick = useCallback(
    (data: Readonly<PlotMouseEvent>) => {
      if (!data.points || data.points.length === 0) return;

      const point = data.points[0];
      if (!point) return;

      const index = point.pointIndex;
      const curveNumber = point.curveNumber;

      // Determine which array the point came from
      let clickedPoint: ParetoPoint | undefined;
      if (curveNumber === 0 && analysis.frontierPoints[index]) {
        clickedPoint = analysis.frontierPoints[index];
        // If clicking on a frontier point, also trigger operating point selection
        if (onOperatingPointSelect) {
          onOperatingPointSelect(clickedPoint);
        }
      } else if (curveNumber === 1 && analysis.dominatedPoints[index]) {
        clickedPoint = analysis.dominatedPoints[index];
      }

      if (clickedPoint && onPointClick) {
        onPointClick(clickedPoint);
      }
    },
    [analysis, onPointClick, onOperatingPointSelect]
  );

  // Handle hover
  const handleHover = useCallback(
    (data: Readonly<PlotMouseEvent>) => {
      if (!onPointHover || !data.points || data.points.length === 0) {
        onPointHover?.(null);
        return;
      }

      const point = data.points[0];
      if (!point) return;

      const index = point.pointIndex;
      const curveNumber = point.curveNumber;

      let hoveredPoint: ParetoPoint | undefined;
      if (curveNumber === 0 && analysis.frontierPoints[index]) {
        hoveredPoint = analysis.frontierPoints[index];
      } else if (curveNumber === 1 && analysis.dominatedPoints[index]) {
        hoveredPoint = analysis.dominatedPoints[index];
      }

      onPointHover(hoveredPoint ?? null);
    },
    [analysis, onPointHover]
  );

  const handleUnhover = useCallback(() => {
    onPointHover?.(null);
  }, [onPointHover]);

  // Handle slider change for operating point selection
  const handleSliderChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const index = parseInt(event.target.value, 10);
      if (
        onOperatingPointSelect &&
        analysis.frontierPoints.length > 0 &&
        index >= 0 &&
        index < analysis.frontierPoints.length
      ) {
        const selectedPoint = analysis.frontierPoints[index];
        if (selectedPoint) {
          onOperatingPointSelect(selectedPoint);
        }
      }
    },
    [analysis.frontierPoints, onOperatingPointSelect]
  );

  if (analysis.points.length === 0) {
    return (
      <div
        className={className}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '100%',
          height: '100%',
          color: 'var(--pareto-text-muted, #a0a0a0)',
          fontFamily: 'system-ui, sans-serif',
          fontSize: 14,
          ...style,
        }}
      >
        No measurements are available for these axes. Supply measured points or choose metrics present in the run.
      </div>
    );
  }


  return (
    <div
      className={className}
      style={{
        width: '100%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        ...style,
      }}
    >
      <Plot
        data={traces}
        layout={layout}
        config={{
          responsive: true,
          displayModeBar: true,
          modeBarButtonsToRemove: ['lasso2d', 'select2d'],
          displaylogo: false,
        }}
        style={{ width: '100%', flex: 1 }}
        onClick={handleClick}
        onHover={handleHover}
        onUnhover={handleUnhover}
      />

      {/* Operating Point Slider */}
      {showOperatingPointSlider && analysis.frontierPoints.length > 1 && (
        <div
          style={{
            padding: '8px 16px',
            backgroundColor: 'rgba(0,0,0,0.3)',
            borderRadius: '4px',
            marginTop: '8px',
          }}
        >
          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              color: '#a0a0a0',
              fontSize: '13px',
              fontFamily: 'system-ui, sans-serif',
            }}
          >
            <span style={{ minWidth: '140px' }}>Operating Point:</span>
            <input
              type="range"
              min={0}
              max={analysis.frontierPoints.length - 1}
              value={selectedOperatingPointIndex ?? 0}
              onChange={handleSliderChange}
              style={{
                flex: 1,
                accentColor: '#3b82f6',
              }}
            />
            <span style={{ minWidth: '40px', textAlign: 'right' }}>
              {selectedOperatingPointIndex !== undefined
                ? `${selectedOperatingPointIndex + 1}/${analysis.frontierPoints.length}`
                : `1/${analysis.frontierPoints.length}`}
            </span>
          </label>
        </div>
      )}
    </div>
  );
}

export default ParetoFrontier;
