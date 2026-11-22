import { TruthMode } from '../types';

/**
 * Props for TruthModeSwitch component
 */
export interface TruthModeSwitchProps {
  /** Current truth mode */
  mode: TruthMode;
  /** Callback when mode changes */
  onModeChange: (mode: TruthMode) => void;
  /** Number of inferred edges that will be hidden in product mode */
  inferredEdgeCount?: number;
  /** Number of proxy edges that will be hidden in product mode */
  proxyEdgeCount?: number;
  /** Custom class name */
  className?: string;
  /** Custom styles */
  style?: React.CSSProperties;
}

/**
 * TruthModeSwitch Component
 *
 * Toggle between:
 * - RESEARCH: Can show supplied uncertainty, costs and unverified links
 * - PRODUCT: Limits the graph to pairs with supplied direct probe evidence
 */
export function TruthModeSwitch({
  mode,
  onModeChange,
  inferredEdgeCount = 0,
  proxyEdgeCount = 0,
  className = '',
  style,
}: TruthModeSwitchProps) {
  const isResearch = mode === TruthMode.RESEARCH;

  return (
    <div
      className={`truth-mode-switch ${className}`}
      style={{
        fontFamily: 'system-ui, sans-serif',
        ...style,
      }}
    >
      {/* Switch container */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
        }}
      >
        {/* Label */}
        <span
          style={{
            fontSize: 12,
            color: 'var(--color-text-muted, #a0a0a0)',
            userSelect: 'none',
          }}
        >
          Mode
        </span>

        {/* Toggle switch */}
        <button
          onClick={() => onModeChange(isResearch ? TruthMode.PRODUCT : TruthMode.RESEARCH)}
          style={{
            position: 'relative',
            width: 120,
            height: 32,
            background: 'var(--color-bg-tertiary, #0f172a)',
            border: 'none',
            borderRadius: 16,
            cursor: 'pointer',
            overflow: 'hidden',
            padding: 0,
          }}
        >
          {/* Sliding background */}
          <div
            style={{
              position: 'absolute',
              top: 2,
              left: isResearch ? 2 : 'calc(50% + 2px)',
              width: 'calc(50% - 4px)',
              height: 28,
              background: isResearch
                ? 'var(--color-primary, #e94560)'
                : 'var(--color-success, #10b981)',
              borderRadius: 14,
              transition: 'left 200ms ease',
            }}
          />

          {/* Labels */}
          <div
            style={{
              position: 'relative',
              display: 'flex',
              height: '100%',
            }}
          >
            <span
              style={{
                flex: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 11,
                fontWeight: 600,
                color: isResearch ? '#ffffff' : 'var(--color-text-muted, #a0a0a0)',
                transition: 'color 200ms ease',
              }}
            >
              Research
            </span>
            <span
              style={{
                flex: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 11,
                fontWeight: 600,
                color: isResearch ? 'var(--color-text-muted, #a0a0a0)' : '#ffffff',
                transition: 'color 200ms ease',
              }}
            >
              Product
            </span>
          </div>
        </button>
      </div>

      {/* Mode description */}
      <div
        style={{
          marginTop: 8,
          padding: 10,
          background: isResearch
            ? 'var(--color-primary, #e94560)11'
            : 'var(--color-success, #10b981)11',
          border: `1px solid ${isResearch ? 'var(--color-primary, #e94560)' : 'var(--color-success, #10b981)'}`,
          borderRadius: 6,
          fontSize: 11,
        }}
      >
        {isResearch ? (
          <>
            <div style={{ fontWeight: 600, color: 'var(--color-primary, #e94560)', marginBottom: 4 }}>
              Research Mode
            </div>
            <ul style={{ margin: 0, paddingLeft: 16, color: 'var(--color-text, #eaeaea)' }}>
              <li>Shows supplied probe statistics and costs</li>
              <li>Implied view can include inferred and proxy links</li>
            </ul>
          </>
        ) : (
          <>
            <div style={{ fontWeight: 600, color: 'var(--color-success, #10b981)', marginBottom: 4 }}>
              Product Mode
            </div>
            <ul style={{ margin: 0, paddingLeft: 16, color: 'var(--color-text, #eaeaea)' }}>
              <li>Graph shows pairs with supplied direct probe evidence</li>
              <li>Inferred and proxy links are hidden</li>
            </ul>
            {(inferredEdgeCount > 0 || proxyEdgeCount > 0) && (
              <div style={{ marginTop: 8, color: 'var(--color-text-muted, #a0a0a0)' }}>
                Hidden: {inferredEdgeCount} implied (unverified), {proxyEdgeCount} proxy edges
              </div>
            )}
            {/* Visible affordance to switch to Research mode */}
            <button
              onClick={() => onModeChange(TruthMode.RESEARCH)}
              style={{
                marginTop: 10,
                width: '100%',
                padding: '8px 12px',
                borderRadius: 4,
                border: '1px dashed var(--color-primary, #e94560)',
                background: 'transparent',
                color: 'var(--color-primary, #e94560)',
                fontSize: 11,
                fontWeight: 500,
                cursor: 'pointer',
                transition: 'all 150ms ease',
              }}
            >
              Switch to Research Mode (shows all uncertainty)
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export default TruthModeSwitch;
