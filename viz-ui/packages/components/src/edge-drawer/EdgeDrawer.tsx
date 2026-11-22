import { useMemo, useState } from 'react';
import type {
  EdgeStatus,
  ProbeEvidence,
  EdgeType,
  ConfidenceLevel,
  MultipleTestingMethod,
  ProxySignalType,
} from '../types';

/**
 * Props for EdgeDrawer component
 */
export interface EdgeDrawerProps {
  /** The edge to display details for */
  edge: EdgeStatus | null;
  /** Whether the drawer is open */
  isOpen: boolean;
  /** Callback to close the drawer */
  onClose: () => void;
  /** Callback to rerun probe with specific n */
  onRerunProbe?: (edge: EdgeStatus, sampleSize: number) => void;
  /** Callback to verify an inferred edge */
  onVerifyEdge?: (edge: EdgeStatus) => void;
  /** Estimated cost per episode in seconds */
  costPerEpisodeSeconds?: number;
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
 * Format timestamp as relative time
 */
function formatRelativeTime(timestamp: number): string {
  const now = Date.now();
  const diff = now - timestamp;
  const seconds = Math.floor(diff / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (days > 0) return `${days}d ago`;
  if (hours > 0) return `${hours}h ago`;
  if (minutes > 0) return `${minutes}m ago`;
  return `${seconds}s ago`;
}

/**
 * Get confidence badge styling
 */
function getConfidenceBadgeStyle(level: ConfidenceLevel): { bg: string; text: string } {
  switch (level) {
    case 'strong':
      return { bg: 'var(--color-success, #10b981)', text: '#ffffff' };
    case 'medium':
      return { bg: 'var(--color-warning, #f59e0b)', text: '#000000' };
    case 'weak':
      return { bg: 'var(--color-error, #ef4444)', text: '#ffffff' };
    default:
      return { bg: 'var(--color-text-muted, #6b7280)', text: '#ffffff' };
  }
}

/**
 * Get edge type styling
 */
function getEdgeTypeStyle(type: EdgeType): { bg: string; text: string; label: string; icon: string } {
  switch (type) {
    case 'measured':
      return { bg: 'var(--color-success, #10b981)', text: '#ffffff', label: 'Measured', icon: '\u2713' };
    case 'inferred':
      return { bg: 'var(--color-warning, #f59e0b)', text: '#000000', label: 'Implied (unverified)', icon: '\u26D3' };
    case 'proxy':
      return { bg: 'var(--color-info, #3b82f6)', text: '#ffffff', label: 'Proxy', icon: '\u2726' };
    default:
      return { bg: 'var(--color-text-muted, #6b7280)', text: '#ffffff', label: 'Unknown', icon: '?' };
  }
}

/**
 * Format multiple testing method
 */
function formatCorrectionMethod(method: MultipleTestingMethod): string {
  switch (method) {
    case 'bonferroni':
      return 'Bonferroni';
    case 'bh_fdr':
      return 'BH-FDR';
    case 'holm':
      return 'Holm';
    case 'none':
      return 'None';
    default:
      return method;
  }
}

/**
 * Format proxy signal type
 */
function formatProxySignal(type: ProxySignalType): string {
  switch (type) {
    case 'recency':
      return 'Recency';
    case 'usage':
      return 'Usage Frequency';
    case 'reward_correlation':
      return 'Reward Correlation';
    case 'temporal_proximity':
      return 'Temporal Proximity';
    default:
      return type;
  }
}

/**
 * Sparkline component for probe history
 */
function Sparkline({ data, width = 120, height = 30 }: { data: number[]; width?: number; height?: number }) {
  if (data.length < 2) return null;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  const points = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * width;
      const y = height - ((v - min) / range) * height;
      return `${x},${y}`;
    })
    .join(' ');

  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      <polyline
        points={points}
        fill="none"
        stroke="var(--color-primary, #e94560)"
        strokeWidth={1.5}
      />
    </svg>
  );
}

/**
 * EdgeDrawer Component
 *
 * A side drawer that shows detailed information about a causal edge:
 * - Status (measured/inferred/proxy)
 * - Evidence (probe summary for measured edges)
 * - Stability (confidence trend sparkline)
 * - Reproduction options
 * - Cost information
 */
export function EdgeDrawer({
  edge,
  isOpen,
  onClose,
  onRerunProbe,
  onVerifyEdge,
  costPerEpisodeSeconds = 0.5, // default estimate
  className = '',
  style,
}: EdgeDrawerProps) {
  // Extract probe history q-values for sparkline
  const qValueHistory = useMemo(() => {
    if (!edge?.probeHistory?.length) return [];
    return edge.probeHistory.map((p) => p.qValue);
  }, [edge?.probeHistory]);

  // Rerun action state
  const [rerunN, setRerunN] = useState(100);
  const [showRerunConfirmation, setShowRerunConfirmation] = useState(false);

  if (!isOpen || !edge) {
    return null;
  }

  const typeStyle = getEdgeTypeStyle(edge.edgeType);
  const confidenceStyle = edge.confidenceLevel
    ? getConfidenceBadgeStyle(edge.confidenceLevel)
    : null;

  return (
    <div
      className={`edge-drawer ${className}`}
      style={{
        position: 'fixed',
        top: 0,
        right: 0,
        width: 360,
        height: '100%',
        background: 'var(--color-bg-secondary, #16213e)',
        borderLeft: '1px solid var(--color-accent, #0f3460)',
        zIndex: 1000,
        display: 'flex',
        flexDirection: 'column',
        fontFamily: 'system-ui, sans-serif',
        color: 'var(--color-text, #eaeaea)',
        ...style,
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '16px',
          borderBottom: '1px solid var(--color-accent, #0f3460)',
        }}
      >
        <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>Edge Details</h2>
        <button
          onClick={onClose}
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--color-text-muted, #a0a0a0)',
            cursor: 'pointer',
            fontSize: 20,
            lineHeight: 1,
            padding: 4,
          }}
          aria-label="Close"
        >
          x
        </button>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: 'auto', padding: 16 }}>
        {/* Edge identification */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 13, color: 'var(--color-text-muted, #a0a0a0)', marginBottom: 4 }}>
            Edge
          </div>
          <div style={{ fontSize: 14, fontWeight: 500 }}>
            {edge.source} {'->'} {edge.target}
          </div>
        </div>

        {/* Status badge */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 13, color: 'var(--color-text-muted, #a0a0a0)', marginBottom: 8 }}>
            Status
          </div>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '4px 12px',
              borderRadius: 4,
              fontSize: 12,
              fontWeight: 600,
              background: typeStyle.bg,
              color: typeStyle.text,
            }}
          >
            <span aria-hidden="true">{typeStyle.icon}</span>
            {typeStyle.label}
          </span>
          {confidenceStyle && edge.confidenceLevel && (
            <span
              style={{
                display: 'inline-block',
                padding: '4px 12px',
                borderRadius: 4,
                fontSize: 12,
                fontWeight: 600,
                marginLeft: 8,
                background: confidenceStyle.bg,
                color: confidenceStyle.text,
              }}
            >
              {edge.confidenceLevel.toUpperCase()}
            </span>
          )}
        </div>

        {/* Measured edge: probe evidence */}
        {edge.edgeType === 'measured' && edge.probeEvidence && (
          <ProbeEvidenceSection evidence={edge.probeEvidence} />
        )}

        {/* Proxy edge: proxy info */}
        {edge.edgeType === 'proxy' && edge.proxyInfo && (
          <div style={{ marginBottom: 20 }}>
            <div style={{ fontSize: 13, color: 'var(--color-text-muted, #a0a0a0)', marginBottom: 8 }}>
              Proxy Signal
            </div>
            <div style={{ background: 'var(--color-bg-tertiary, #0f172a)', padding: 12, borderRadius: 6 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <span>Type</span>
                <span style={{ fontWeight: 500 }}>{formatProxySignal(edge.proxyInfo.signalType)}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <span>Strength</span>
                <span style={{ fontWeight: 500 }}>{(edge.proxyInfo.strength * 100).toFixed(0)}%</span>
              </div>
              {edge.proxyInfo.description && (
                <div style={{ fontSize: 12, color: 'var(--color-text-muted, #a0a0a0)', marginTop: 8 }}>
                  {edge.proxyInfo.description}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Implied (unverified) edge: path info */}
        {edge.edgeType === 'inferred' && (
          <div style={{ marginBottom: 20 }}>
            <div
              style={{
                padding: 12,
                background: 'var(--color-warning, #f59e0b)22',
                borderRadius: 6,
                border: '1px solid var(--color-warning, #f59e0b)',
                marginBottom: 12,
              }}
            >
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-warning, #f59e0b)' }}>
                IMPLIED (UNVERIFIED)
              </div>
              <div style={{ fontSize: 12, marginTop: 4, color: 'var(--color-text, #eaeaea)' }}>
                Shown due to closure assumptions; no direct probe yet.
              </div>
              <div style={{ fontSize: 11, marginTop: 4, color: 'var(--color-text-muted, #a0a0a0)' }}>
                Violations may occur. Confirmation requires a direct probe.
              </div>
            </div>
            {edge.inferredPath && edge.inferredPath.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 13, color: 'var(--color-text-muted, #a0a0a0)', marginBottom: 8 }}>
                  Implied by Path
                </div>
                <div style={{ fontSize: 13, fontFamily: 'monospace' }}>
                  {edge.inferredPath.join(' -> ')}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Stability sparkline */}
        {qValueHistory.length > 1 && (
          <div style={{ marginBottom: 20 }}>
            <div style={{ fontSize: 13, color: 'var(--color-text-muted, #a0a0a0)', marginBottom: 8 }}>
              Confidence Trend (q-value)
            </div>
            <div style={{ background: 'var(--color-bg-tertiary, #0f172a)', padding: 12, borderRadius: 6 }}>
              <Sparkline data={qValueHistory} width={300} height={40} />
            </div>
          </div>
        )}

        {/* Insufficient power warning */}
        {edge.insufficientPower && (
          <div
            style={{
              padding: 12,
              background: 'var(--color-error, #ef4444)22',
              borderRadius: 6,
              border: '1px solid var(--color-error, #ef4444)',
              marginBottom: 20,
            }}
          >
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-error, #ef4444)' }}>
              INSUFFICIENT POWER
            </div>
            <div style={{ fontSize: 12, marginTop: 4, color: 'var(--color-text, #eaeaea)' }}>
              Not enough episodes for reliable detection. Power: {edge.statisticalPower !== undefined ? `${(edge.statisticalPower * 100).toFixed(0)}%` : 'N/A'}
            </div>
            <div style={{ fontSize: 11, marginTop: 4, color: 'var(--color-text-muted, #a0a0a0)' }}>
              This does NOT mean no causal relation exists.
            </div>
          </div>
        )}

        {/* Cost information */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 13, color: 'var(--color-text-muted, #a0a0a0)', marginBottom: 8 }}>
            Cost
          </div>
          <div style={{ background: 'var(--color-bg-tertiary, #0f172a)', padding: 12, borderRadius: 6 }}>
            {edge.probeEvidence && (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                  <span>Episodes Used</span>
                  <span style={{ fontWeight: 500 }}>{edge.probeEvidence.episodesUsed}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>Wall Time</span>
                  <span style={{ fontWeight: 500 }}>{edge.probeEvidence.wallTimeSeconds.toFixed(1)}s</span>
                </div>
              </>
            )}
            {(edge.edgeType === 'inferred' || edge.edgeType === 'proxy') && edge.verificationCostEpisodes !== undefined && (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                  <span>Cost to Verify</span>
                  <span style={{ fontWeight: 500 }}>~{edge.verificationCostEpisodes} episodes</span>
                </div>
                {edge.verificationCostSeconds !== undefined && (
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>Est. Time</span>
                    <span style={{ fontWeight: 500 }}>~{edge.verificationCostSeconds.toFixed(0)}s</span>
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        {/* Actions */}
        <div style={{ marginTop: 20, display: 'flex', flexDirection: 'column', gap: 8 }}>
          {((edge.edgeType === 'measured' && !onRerunProbe) ||
            (edge.edgeType === 'inferred' && !onVerifyEdge)) && (
            <p role="status">Probe execution is unavailable in this debugger.</p>
          )}
          {edge.edgeType === 'measured' && onRerunProbe && (
            <>
              {!showRerunConfirmation ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <label style={{ fontSize: 12, color: 'var(--color-text-muted, #a0a0a0)' }}>
                      Rerun with n=
                    </label>
                    <select
                      value={rerunN}
                      onChange={(e) => setRerunN(Number(e.target.value))}
                      style={{
                        flex: 1,
                        padding: '6px 8px',
                        borderRadius: 4,
                        border: '1px solid var(--color-accent, #0f3460)',
                        background: 'var(--color-bg-tertiary, #0f172a)',
                        color: 'var(--color-text, #eaeaea)',
                        fontSize: 12,
                      }}
                    >
                      <option value={50}>50</option>
                      <option value={100}>100</option>
                      <option value={200}>200</option>
                      <option value={500}>500</option>
                      <option value={1000}>1000</option>
                    </select>
                  </div>
                  <button
                    onClick={() => setShowRerunConfirmation(true)}
                    style={{
                      padding: '10px 16px',
                      background: 'var(--color-accent, #0f3460)',
                      border: 'none',
                      borderRadius: 6,
                      color: 'var(--color-text, #eaeaea)',
                      cursor: 'pointer',
                      fontSize: 13,
                      fontWeight: 500,
                    }}
                  >
                    Rerun Probe
                  </button>
                </div>
              ) : (
                <div
                  style={{
                    padding: 12,
                    background: 'var(--color-bg-tertiary, #0f172a)',
                    borderRadius: 6,
                    border: '1px solid var(--color-primary, #e94560)',
                  }}
                >
                  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-primary, #e94560)', marginBottom: 8 }}>
                    Confirm Rerun
                  </div>
                  <div style={{ fontSize: 11, marginBottom: 8, color: 'var(--color-text, #eaeaea)' }}>
                    This will cost:
                    <ul style={{ margin: '4px 0', paddingLeft: 16 }}>
                      <li>~{rerunN} episodes</li>
                      <li>~{(rerunN * costPerEpisodeSeconds).toFixed(0)}s estimated time</li>
                    </ul>
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button
                      onClick={() => {
                        setShowRerunConfirmation(false);
                        onRerunProbe(edge, rerunN);
                      }}
                      style={{
                        flex: 1,
                        padding: '8px 12px',
                        borderRadius: 4,
                        border: 'none',
                        background: 'var(--color-primary, #e94560)',
                        color: '#ffffff',
                        fontSize: 12,
                        fontWeight: 500,
                        cursor: 'pointer',
                      }}
                    >
                      Run {rerunN} probes
                    </button>
                    <button
                      onClick={() => setShowRerunConfirmation(false)}
                      style={{
                        flex: 1,
                        padding: '8px 12px',
                        borderRadius: 4,
                        border: '1px solid var(--color-accent, #0f3460)',
                        background: 'transparent',
                        color: 'var(--color-text, #eaeaea)',
                        fontSize: 12,
                        fontWeight: 500,
                        cursor: 'pointer',
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
          {edge.edgeType === 'inferred' && onVerifyEdge && (
            <button
              onClick={() => onVerifyEdge(edge)}
              style={{
                padding: '10px 16px',
                background: 'var(--color-primary, #e94560)',
                border: 'none',
                borderRadius: 6,
                color: '#ffffff',
                cursor: 'pointer',
                fontSize: 13,
                fontWeight: 500,
              }}
            >
              Verify Edge (~{edge.verificationCostEpisodes ?? '?'} episodes, ~{((edge.verificationCostEpisodes ?? 0) * costPerEpisodeSeconds).toFixed(0)}s)
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Probe evidence section component
 */
function ProbeEvidenceSection({ evidence }: { evidence: ProbeEvidence }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ fontSize: 13, color: 'var(--color-text-muted, #a0a0a0)', marginBottom: 8 }}>
        Probe Evidence
      </div>
      <div style={{ background: 'var(--color-bg-tertiary, #0f172a)', padding: 12, borderRadius: 6 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          <div>
            <div style={{ fontSize: 11, color: 'var(--color-text-muted, #a0a0a0)' }}>p-value</div>
            <div style={{ fontSize: 14, fontWeight: 500 }}>{formatNumber(evidence.pValue)}</div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: 'var(--color-text-muted, #a0a0a0)' }}>q-value</div>
            <div style={{ fontSize: 14, fontWeight: 500 }}>{formatNumber(evidence.qValue)}</div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: 'var(--color-text-muted, #a0a0a0)' }}>Effect Size</div>
            <div style={{ fontSize: 14, fontWeight: 500 }}>{formatNumber(evidence.effectSize)}</div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: 'var(--color-text-muted, #a0a0a0)' }}>n</div>
            <div style={{ fontSize: 14, fontWeight: 500 }}>{evidence.n}</div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: 'var(--color-text-muted, #a0a0a0)' }}>Correction</div>
            <div style={{ fontSize: 14, fontWeight: 500 }}>{formatCorrectionMethod(evidence.correctionMethod)}</div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: 'var(--color-text-muted, #a0a0a0)' }}>Test</div>
            <div style={{ fontSize: 14, fontWeight: 500 }}>{evidence.testType}</div>
          </div>
        </div>
        {evidence.ciLower !== undefined && evidence.ciUpper !== undefined && (
          <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--color-accent, #0f3460)' }}>
            <div style={{ fontSize: 11, color: 'var(--color-text-muted, #a0a0a0)' }}>95% CI</div>
            <div style={{ fontSize: 14, fontWeight: 500 }}>
              [{formatNumber(evidence.ciLower)}, {formatNumber(evidence.ciUpper)}]
            </div>
          </div>
        )}
        {/* Test regime details */}
        <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--color-accent, #0f3460)' }}>
          <div style={{ fontSize: 11, color: 'var(--color-text-muted, #a0a0a0)', marginBottom: 4 }}>
            <strong>Test Regime</strong>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, fontSize: 11 }}>
            <div>
              <span style={{ color: 'var(--color-text-muted, #a0a0a0)' }}>n episodes:</span>{' '}
              <span>{evidence.episodesUsed}</span>
            </div>
            <div>
              <span style={{ color: 'var(--color-text-muted, #a0a0a0)' }}>Wall time:</span>{' '}
              <span>{evidence.wallTimeSeconds.toFixed(1)}s</span>
            </div>
            <div>
              <span style={{ color: 'var(--color-text-muted, #a0a0a0)' }}>Test type:</span>{' '}
              <span>{evidence.testType}</span>
            </div>
            <div>
              <span style={{ color: 'var(--color-text-muted, #a0a0a0)' }}>Correction:</span>{' '}
              <span>{formatCorrectionMethod(evidence.correctionMethod)}</span>
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <span style={{ color: 'var(--color-text-muted, #a0a0a0)' }}>Seeds:</span>{' '}
              <span>
                {evidence.seed !== undefined
                  ? `fixed: ${evidence.seed}`
                  : 'random'}
              </span>
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <span style={{ color: 'var(--color-text-muted, #a0a0a0)' }}>Last probe:</span>{' '}
              <span>{formatRelativeTime(evidence.timestamp)}</span>
            </div>
          </div>
        </div>

        {/* Probe cost spent so far */}
        <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--color-accent, #0f3460)' }}>
          <div style={{ fontSize: 11, color: 'var(--color-text-muted, #a0a0a0)', marginBottom: 4 }}>
            <strong>Probe Cost (this edge)</strong>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
            <span>Episodes spent:</span>
            <span style={{ fontWeight: 500, color: 'var(--color-warning, #f59e0b)' }}>
              {evidence.episodesUsed}
            </span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
            <span>Wall time spent:</span>
            <span style={{ fontWeight: 500, color: 'var(--color-warning, #f59e0b)' }}>
              {evidence.wallTimeSeconds.toFixed(1)}s
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default EdgeDrawer;
