import { useState, useMemo, useCallback, useRef, useEffect } from 'react';
import type { TransitivityViolation, TransitivityReport } from '../types';

/**
 * Filter options for violations panel
 */
export interface ViolationFilters {
  /** Show only measured-measured-measured triples */
  measuredOnly: boolean;
  /** Show only failures due to insufficient n */
  insufficientNOnly: boolean;
  /** Show only likely false positives (borderline q-values) */
  borderlineOnly: boolean;
  /** Show only untested violations */
  untestedOnly: boolean;
}

/**
 * Props for ViolationsPanel component
 */
export interface ViolationsPanelProps {
  /** Transitivity report to display */
  report: TransitivityReport | null;
  /** Callback when a violation is selected */
  onViolationSelect?: (violation: TransitivityViolation) => void;
  /** Callback to verify an edge */
  onVerifyEdge?: (source: string, target: string) => void;
  /** Callback to increase sample size */
  onIncreaseN?: (source: string, target: string, suggestedN: number) => void;
  /** Currently selected violation ID */
  selectedViolationId?: string | null;
  /** Custom class name */
  className?: string;
  /** Custom styles */
  style?: React.CSSProperties;
}

/**
 * Format a number with appropriate precision
 */
function formatNumber(n: number, precision = 3): string {
  if (n < 0.001 && n !== 0) {
    return n.toExponential(2);
  }
  return n.toFixed(precision);
}

/**
 * Get category badge styling
 */
function getCategoryStyle(category: TransitivityViolation['category']): { bg: string; label: string } {
  switch (category) {
    case 'measured_failure':
      return { bg: 'var(--color-error, #ef4444)', label: 'Measured Failure' };
    case 'untested':
      return { bg: 'var(--color-warning, #f59e0b)', label: 'Untested' };
    case 'borderline':
      return { bg: 'var(--color-info, #3b82f6)', label: 'Borderline' };
    case 'power_issue':
      return { bg: 'var(--color-text-muted, #6b7280)', label: 'Power Issue' };
    default:
      return { bg: 'var(--color-text-muted, #6b7280)', label: 'Unknown' };
  }
}

/**
 * Get violation classification label styling.
 * Helps users understand the likely cause and appropriate action.
 */
function getViolationClassificationLabel(
  violation: TransitivityViolation
): { icon: string; label: string; tooltip: string; color: string } | null {
  // Use explicit violationCategory if set
  if (violation.violationCategory) {
    switch (violation.violationCategory) {
      case 'type_i_suspect':
        return {
          icon: '\u26A0\uFE0F', // warning sign
          label: 'Near threshold',
          tooltip: 'q-value between 0.04-0.06 - false positive likely',
          color: 'var(--color-warning, #f59e0b)',
        };
      case 'low_power_suspect':
        return {
          icon: '\uD83D\uDCCA', // bar chart
          label: 'Underpowered',
          tooltip: 'A->C unverified or low n - false negative likely',
          color: 'var(--color-info, #3b82f6)',
        };
      case 'budget_limited':
        return {
          icon: '\uD83D\uDCB0', // money bag
          label: 'Budget-limited',
          tooltip: 'Verification skipped due to constraints',
          color: 'var(--color-text-muted, #a0a0a0)',
        };
      default:
        return null;
    }
  }

  // Auto-classify based on violation properties
  // Type I suspect: q-value near threshold (0.04-0.06)
  const qValues = [violation.edgeAB.qValue, violation.edgeBC.qValue, violation.edgeAC.qValue].filter(
    (q): q is number => q !== undefined
  );
  if (qValues.some((q) => q >= 0.04 && q <= 0.06)) {
    return {
      icon: '\u26A0\uFE0F',
      label: 'Near threshold',
      tooltip: 'q-value between 0.04-0.06 - false positive likely',
      color: 'var(--color-warning, #f59e0b)',
    };
  }

  // Low power suspect: untested or low n
  if (!violation.edgeAC.tested || (violation.edgeAC.n !== undefined && violation.edgeAC.n < 50)) {
    return {
      icon: '\uD83D\uDCCA',
      label: 'Underpowered',
      tooltip: 'A->C unverified or low n - false negative likely',
      color: 'var(--color-info, #3b82f6)',
    };
  }

  return null;
}

/** Virtualization constants */
const ITEM_HEIGHT = 120; // Approximate height of each violation card
const OVERSCAN = 5; // Number of items to render outside visible area

/**
 * ViolationsPanel Component
 *
 * A first-class panel for displaying transitivity violations.
 * Shows each violating triple (A->B, B->C, A->C fails) with:
 * - Whether each edge was tested
 * - Statistical details for tested edges
 * - Filters for different violation types
 */
export function ViolationsPanel({
  report,
  onViolationSelect,
  onVerifyEdge,
  onIncreaseN,
  selectedViolationId,
  className = '',
  style,
}: ViolationsPanelProps) {
  // Filter state
  const [filters, setFilters] = useState<ViolationFilters>({
    measuredOnly: false,
    insufficientNOnly: false,
    borderlineOnly: false,
    untestedOnly: false,
  });

  // Expand/collapse state for violations
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  // Toggle filter
  const toggleFilter = useCallback((key: keyof ViolationFilters) => {
    setFilters((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  // Toggle expansion
  const toggleExpanded = useCallback((id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  // Filter violations
  const filteredViolations = useMemo(() => {
    if (!report?.violations) return [];

    return report.violations.filter((v) => {
      // Measured only: all three edges must be tested
      if (filters.measuredOnly) {
        if (!v.edgeAB.tested || !v.edgeBC.tested || !v.edgeAC.tested) {
          return false;
        }
      }

      // Insufficient N only
      if (filters.insufficientNOnly) {
        if (v.category !== 'power_issue') {
          return false;
        }
      }

      // Borderline only
      if (filters.borderlineOnly) {
        if (v.category !== 'borderline') {
          return false;
        }
      }

      // Untested only
      if (filters.untestedOnly) {
        if (v.category !== 'untested') {
          return false;
        }
      }

      return true;
    });
  }, [report?.violations, filters]);

  // Summary stats
  const stats = useMemo(() => {
    if (!report) return null;
    return {
      total: report.totalViolations,
      byCategory: report.violationsByCategory,
      edgesChecked: report.edgesChecked,
      triplesChecked: report.triplesChecked,
    };
  }, [report]);

  if (!report) {
    return (
      <div
        className={className}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          color: 'var(--color-text-muted, #a0a0a0)',
          fontFamily: 'system-ui, sans-serif',
          fontSize: 14,
          ...style,
        }}
      >
        No transitivity report available.
      </div>
    );
  }

  return (
    <div
      className={`violations-panel ${className}`}
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        background: 'var(--color-bg-secondary, #16213e)',
        borderRadius: 8,
        overflow: 'hidden',
        fontFamily: 'system-ui, sans-serif',
        color: 'var(--color-text, #eaeaea)',
        ...style,
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: '12px 16px',
          borderBottom: '1px solid var(--color-accent, #0f3460)',
        }}
      >
        <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          Transitivity Violations
        </h3>
        {stats && (
          <div style={{ fontSize: 12, color: 'var(--color-text-muted, #a0a0a0)', marginTop: 4 }}>
            {stats.total} violations from {stats.triplesChecked} triples checked
          </div>
        )}
      </div>

      {/* Filters */}
      <div
        style={{
          padding: '8px 16px',
          borderBottom: '1px solid var(--color-accent, #0f3460)',
          display: 'flex',
          flexWrap: 'wrap',
          gap: 8,
        }}
      >
        <FilterChip
          label="Measured Only"
          active={filters.measuredOnly}
          onClick={() => toggleFilter('measuredOnly')}
        />
        <FilterChip
          label="Insufficient N"
          active={filters.insufficientNOnly}
          onClick={() => toggleFilter('insufficientNOnly')}
        />
        <FilterChip
          label="Borderline"
          active={filters.borderlineOnly}
          onClick={() => toggleFilter('borderlineOnly')}
        />
        <FilterChip
          label="Untested"
          active={filters.untestedOnly}
          onClick={() => toggleFilter('untestedOnly')}
        />
      </div>

      {/* Violations list - virtualized when > 50 items */}
      {filteredViolations.length > 50 ? (
        <VirtualizedViolationsList
          violations={filteredViolations}
          expandedIds={expandedIds}
          selectedViolationId={selectedViolationId}
          onToggleExpand={toggleExpanded}
          onViolationSelect={onViolationSelect}
          onVerifyEdge={onVerifyEdge}
          onIncreaseN={onIncreaseN}
        />
      ) : (
        <div style={{ flex: 1, overflow: 'auto', padding: '8px 0' }}>
          {filteredViolations.length === 0 ? (
            <div style={{ padding: 16, textAlign: 'center', color: 'var(--color-text-muted, #a0a0a0)' }}>
              No violations match the current filters.
            </div>
          ) : (
            filteredViolations.map((violation) => (
              <ViolationCard
                key={violation.id}
                violation={violation}
                isExpanded={expandedIds.has(violation.id)}
                isSelected={violation.id === selectedViolationId}
                onToggleExpand={() => toggleExpanded(violation.id)}
                onSelect={() => onViolationSelect?.(violation) ?? undefined}
                {...(onVerifyEdge && { onVerifyEdge })}
                {...(onIncreaseN && { onIncreaseN })}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Virtualized violations list for > 50 items.
 * Uses simple windowing without external dependencies.
 */
function VirtualizedViolationsList({
  violations,
  expandedIds,
  selectedViolationId,
  onToggleExpand,
  onViolationSelect,
  onVerifyEdge,
  onIncreaseN,
}: {
  violations: TransitivityViolation[];
  expandedIds: Set<string>;
  selectedViolationId?: string | null | undefined;
  onToggleExpand: (id: string) => void;
  onViolationSelect?: ((violation: TransitivityViolation) => void) | undefined;
  onVerifyEdge?: ((source: string, target: string) => void) | undefined;
  onIncreaseN?: ((source: string, target: string, suggestedN: number) => void) | undefined;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [containerHeight, setContainerHeight] = useState(400);

  // Calculate visible items
  const startIndex = Math.max(0, Math.floor(scrollTop / ITEM_HEIGHT) - OVERSCAN);
  const endIndex = Math.min(
    violations.length,
    Math.ceil((scrollTop + containerHeight) / ITEM_HEIGHT) + OVERSCAN
  );
  const visibleViolations = violations.slice(startIndex, endIndex);

  // Handle scroll
  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(e.currentTarget.scrollTop);
  }, []);

  // Measure container
  useEffect(() => {
    if (containerRef.current) {
      setContainerHeight(containerRef.current.clientHeight);
      const observer = new ResizeObserver((entries) => {
        for (const entry of entries) {
          setContainerHeight(entry.contentRect.height);
        }
      });
      observer.observe(containerRef.current);
      return () => observer.disconnect();
    }
  }, []);

  const totalHeight = violations.length * ITEM_HEIGHT;

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      style={{
        flex: 1,
        overflow: 'auto',
        padding: '8px 0',
      }}
    >
      {/* Warning banner */}
      <div
        style={{
          padding: '8px 12px',
          margin: '0 12px 8px',
          background: 'var(--color-info, #3b82f6)22',
          border: '1px solid var(--color-info, #3b82f6)',
          borderRadius: 4,
          fontSize: 11,
          color: 'var(--color-info, #3b82f6)',
        }}
      >
        Showing {violations.length} violations (virtualized for performance)
      </div>
      {/* Spacer for virtualization */}
      <div style={{ height: totalHeight, position: 'relative' }}>
        <div
          style={{
            position: 'absolute',
            top: startIndex * ITEM_HEIGHT,
            left: 0,
            right: 0,
          }}
        >
          {visibleViolations.map((violation) => (
            <ViolationCard
              key={violation.id}
              violation={violation}
              isExpanded={expandedIds.has(violation.id)}
              isSelected={violation.id === selectedViolationId}
              onToggleExpand={() => onToggleExpand(violation.id)}
              onSelect={() => onViolationSelect?.(violation) ?? undefined}
              {...(onVerifyEdge && { onVerifyEdge })}
              {...(onIncreaseN && { onIncreaseN })}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

/**
 * Filter chip component
 */
function FilterChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '4px 10px',
        borderRadius: 12,
        border: 'none',
        fontSize: 11,
        fontWeight: 500,
        cursor: 'pointer',
        background: active ? 'var(--color-primary, #e94560)' : 'var(--color-accent, #0f3460)',
        color: active ? '#ffffff' : 'var(--color-text, #eaeaea)',
        transition: 'all 150ms ease',
      }}
    >
      {label}
    </button>
  );
}

/**
 * Violation card component
 */
function ViolationCard({
  violation,
  isExpanded,
  isSelected,
  onToggleExpand,
  onSelect,
  onVerifyEdge,
  onIncreaseN,
}: {
  violation: TransitivityViolation;
  isExpanded: boolean;
  isSelected: boolean;
  onToggleExpand: () => void;
  onSelect: () => void;
  onVerifyEdge?: (source: string, target: string) => void;
  onIncreaseN?: (source: string, target: string, suggestedN: number) => void;
}) {
  const categoryStyle = getCategoryStyle(violation.category);
  const classificationLabel = getViolationClassificationLabel(violation);

  return (
    <div
      style={{
        margin: '0 12px 8px',
        background: isSelected
          ? 'var(--color-accent, #0f3460)'
          : 'var(--color-bg-tertiary, #0f172a)',
        borderRadius: 6,
        border: isSelected
          ? '1px solid var(--color-primary, #e94560)'
          : '1px solid transparent',
        overflow: 'hidden',
      }}
    >
      {/* Card header */}
      <div
        onClick={onSelect}
        style={{
          padding: 12,
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ flex: 1 }}>
          {/* Classification label */}
          {classificationLabel && (
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                padding: '2px 6px',
                marginBottom: 6,
                borderRadius: 3,
                background: `${classificationLabel.color}22`,
                border: `1px solid ${classificationLabel.color}`,
                fontSize: 10,
                fontWeight: 500,
                color: classificationLabel.color,
              }}
              title={classificationLabel.tooltip}
            >
              <span aria-hidden="true">{classificationLabel.icon}</span>
              {classificationLabel.label}
            </div>
          )}
          {/* Triple visualization */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 8, fontFamily: 'monospace', fontSize: 13 }}>
            <span>{violation.nodeA}</span>
            <EdgeIndicator tested={violation.edgeAB.tested} holds={violation.edgeAB.holds} />
            <span>{violation.nodeB}</span>
            <EdgeIndicator tested={violation.edgeBC.tested} holds={violation.edgeBC.holds} />
            <span>{violation.nodeC}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontFamily: 'monospace', fontSize: 13, color: 'var(--color-error, #ef4444)' }}>
            <span>{violation.nodeA}</span>
            <EdgeIndicator tested={violation.edgeAC.tested} holds={violation.edgeAC.holds} fail />
            <span>{violation.nodeC}</span>
          </div>
        </div>

        {/* Category badge */}
        <span
          style={{
            padding: '4px 8px',
            borderRadius: 4,
            fontSize: 10,
            fontWeight: 600,
            background: categoryStyle.bg,
            color: '#ffffff',
            textTransform: 'uppercase',
          }}
        >
          {categoryStyle.label}
        </span>
      </div>

      {/* Expand/collapse button */}
      <button
        onClick={onToggleExpand}
        style={{
          width: '100%',
          padding: '6px 12px',
          background: 'transparent',
          border: 'none',
          borderTop: '1px solid var(--color-accent, #0f3460)',
          color: 'var(--color-text-muted, #a0a0a0)',
          fontSize: 11,
          cursor: 'pointer',
          textAlign: 'left',
        }}
      >
        {isExpanded ? '- Hide details' : '+ Show details'}
      </button>

      {/* Expanded details */}
      {isExpanded && (
        <div style={{ padding: '0 12px 12px', borderTop: '1px solid var(--color-accent, #0f3460)' }}>
          {/* Edge details */}
          <EdgeDetail
            label={`${violation.nodeA} -> ${violation.nodeB}`}
            status={violation.edgeAB}
            {...(onVerifyEdge && { onVerify: () => onVerifyEdge(violation.nodeA, violation.nodeB) })}
            {...(onIncreaseN && { onIncreaseN: (n: number) => onIncreaseN(violation.nodeA, violation.nodeB, n) })}
          />
          <EdgeDetail
            label={`${violation.nodeB} -> ${violation.nodeC}`}
            status={violation.edgeBC}
            {...(onVerifyEdge && { onVerify: () => onVerifyEdge(violation.nodeB, violation.nodeC) })}
            {...(onIncreaseN && { onIncreaseN: (n: number) => onIncreaseN(violation.nodeB, violation.nodeC, n) })}
          />
          <EdgeDetail
            label={`${violation.nodeA} -> ${violation.nodeC} (FAIL)`}
            status={violation.edgeAC}
            isFailing
            {...(onVerifyEdge && { onVerify: () => onVerifyEdge(violation.nodeA, violation.nodeC) })}
            {...(onIncreaseN && { onIncreaseN: (n: number) => onIncreaseN(violation.nodeA, violation.nodeC, n) })}
          />

          {/* Suggested action */}
          <div
            style={{
              marginTop: 12,
              padding: 10,
              background: 'var(--color-accent, #0f3460)',
              borderRadius: 4,
              fontSize: 12,
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: 4 }}>Suggested Action</div>
            <div>{violation.suggestedAction}</div>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Edge indicator arrow
 */
function EdgeIndicator({
  tested,
  holds,
  fail,
}: {
  tested: boolean;
  holds: boolean;
  fail?: boolean;
}) {
  const color = fail
    ? 'var(--color-error, #ef4444)'
    : holds
    ? 'var(--color-success, #10b981)'
    : 'var(--color-warning, #f59e0b)';

  return (
    <span style={{ color, display: 'inline-flex', alignItems: 'center', margin: '0 2px' }}>
      {tested ? (holds ? (fail ? 'X' : '->') : '!->') : '?->'}
    </span>
  );
}

/**
 * Edge detail row
 */
function EdgeDetail({
  label,
  status,
  isFailing,
  onVerify,
  onIncreaseN,
}: {
  label: string;
  status: TransitivityViolation['edgeAB'];
  isFailing?: boolean;
  onVerify?: () => void;
  onIncreaseN?: (n: number) => void;
}) {
  return (
    <div
      style={{
        padding: '8px 0',
        borderBottom: '1px solid var(--color-accent, #0f3460)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
        <span style={{ fontSize: 12, fontWeight: 500, color: isFailing ? 'var(--color-error, #ef4444)' : undefined }}>
          {label}
        </span>
        {!status.tested && onVerify && (
          <button
            onClick={onVerify}
            style={{
              padding: '2px 8px',
              borderRadius: 3,
              border: 'none',
              background: 'var(--color-primary, #e94560)',
              color: '#ffffff',
              fontSize: 10,
              cursor: 'pointer',
            }}
          >
            Verify (~{status.estimatedCostEpisodes ?? '?'} ep)
          </button>
        )}
      </div>

      {status.tested ? (
        <div style={{ fontSize: 11, color: 'var(--color-text-muted, #a0a0a0)', display: 'flex', gap: 12 }}>
          <span>p={formatNumber(status.pValue ?? 0)}</span>
          <span>q={formatNumber(status.qValue ?? 0)}</span>
          <span>d={formatNumber(status.effectSize ?? 0)}</span>
          <span>n={status.n ?? '?'}</span>
        </div>
      ) : (
        <div style={{ fontSize: 11, color: 'var(--color-warning, #f59e0b)' }}>
          Unverified (cost: ~{status.estimatedCostEpisodes ?? '?'} episodes)
        </div>
      )}

      {status.tested && onIncreaseN && (
        <button
          onClick={() => onIncreaseN((status.n ?? 50) * 2)}
          style={{
            marginTop: 4,
            padding: '2px 8px',
            borderRadius: 3,
            border: '1px solid var(--color-accent, #0f3460)',
            background: 'transparent',
            color: 'var(--color-text, #eaeaea)',
            fontSize: 10,
            cursor: 'pointer',
          }}
        >
          Increase n to {(status.n ?? 50) * 2}
        </button>
      )}
    </div>
  );
}

export default ViolationsPanel;
