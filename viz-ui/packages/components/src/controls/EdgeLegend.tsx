import { EdgeType } from '../types';

/**
 * Props for EdgeLegend component
 */
export interface EdgeLegendProps {
  /** Edge types to show in legend */
  visibleTypes?: EdgeType[];
  /** Counts for each edge type */
  counts?: Record<EdgeType, number>;
  /** Whether to show in horizontal or vertical layout */
  layout?: 'horizontal' | 'vertical';
  /** Custom class name */
  className?: string;
  /** Custom styles */
  style?: React.CSSProperties;
}

/**
 * Edge type metadata for legend display.
 * Icons chosen for grayscale accessibility (survive colorblind/print scenarios).
 */
const EDGE_TYPE_META: Record<EdgeType, { label: string; icon: string; description: string; strokeStyle: string }> = {
  [EdgeType.MEASURED]: {
    label: 'Measured',
    icon: '\u2713', // checkmark
    description: 'Direct probe exists with statistical test',
    strokeStyle: 'solid',
  },
  [EdgeType.INFERRED]: {
    label: 'Implied (unverified)',
    icon: '\u26D3', // chain link - implies derived relationship
    description: 'Shown due to closure assumptions; no direct probe yet.',
    strokeStyle: 'dashed',
  },
  [EdgeType.PROXY]: {
    label: 'Proxy',
    icon: '\u2726', // star/wand - heuristic magic
    description: 'Heuristic signal only (recency, usage, etc.)',
    strokeStyle: 'dotted',
  },
};

/**
 * EdgeLegend Component
 *
 * Displays a legend explaining edge type visual encoding:
 * - Solid line = measured (direct probe)
 * - Dashed line = inferred (transitive closure)
 * - Dotted line = proxy (heuristic)
 */
export function EdgeLegend({
  visibleTypes = [EdgeType.MEASURED, EdgeType.INFERRED, EdgeType.PROXY],
  counts,
  layout = 'horizontal',
  className = '',
  style,
}: EdgeLegendProps) {
  const isVertical = layout === 'vertical';

  return (
    <div
      className={`edge-legend ${className}`}
      style={{
        display: 'flex',
        flexDirection: isVertical ? 'column' : 'row',
        gap: isVertical ? 6 : 16,
        padding: '8px 12px',
        background: 'var(--color-bg-tertiary, #0f172a)',
        borderRadius: 6,
        fontFamily: 'system-ui, sans-serif',
        fontSize: 11,
        color: 'var(--color-text, #eaeaea)',
        ...style,
      }}
    >
      {visibleTypes.map((type) => {
        const meta = EDGE_TYPE_META[type];
        const count = counts?.[type];

        return (
          <div
            key={type}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
            title={meta.description}
          >
            {/* Line sample */}
            <svg width={24} height={8} style={{ flexShrink: 0 }}>
              <line
                x1={0}
                y1={4}
                x2={24}
                y2={4}
                stroke={getEdgeColor(type)}
                strokeWidth={2}
                strokeDasharray={getStrokeDasharray(type)}
              />
            </svg>

            {/* Icon (for grayscale accessibility) */}
            <span
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: getEdgeColor(type),
                marginRight: 2,
              }}
              aria-hidden="true"
            >
              {meta.icon}
            </span>

            {/* Label */}
            <span style={{ color: 'var(--color-text-muted, #a0a0a0)' }}>
              {meta.label}
              {count !== undefined && (
                <span style={{ marginLeft: 4, color: 'var(--color-text, #eaeaea)' }}>
                  ({count})
                </span>
              )}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/**
 * Get edge color based on type
 */
function getEdgeColor(type: EdgeType): string {
  switch (type) {
    case EdgeType.MEASURED:
      return 'var(--color-success, #10b981)';
    case EdgeType.INFERRED:
      return 'var(--color-warning, #f59e0b)';
    case EdgeType.PROXY:
      return 'var(--color-info, #3b82f6)';
    default:
      return 'var(--color-text-muted, #6b7280)';
  }
}

/**
 * Get stroke dash array based on type
 */
function getStrokeDasharray(type: EdgeType): string | undefined {
  switch (type) {
    case EdgeType.MEASURED:
      return undefined; // solid
    case EdgeType.INFERRED:
      return '6,3'; // dashed
    case EdgeType.PROXY:
      return '2,2'; // dotted
    default:
      return undefined;
  }
}

export default EdgeLegend;
