import { useEffect, useRef, useState } from 'react';
import type { ComputeLedgerData } from '../types';

/**
 * Props for ComputeLedger component
 */
export interface ComputeLedgerProps {
  /** The ledger data to display */
  ledger: ComputeLedgerData | null;
  /** Whether to show compact mode (for HUD) */
  compact?: boolean;
  /** Callback when user clicks "Verify edge" action */
  onVerifyPending?: () => void;
  /** Custom class name */
  className?: string;
  /** Custom styles */
  style?: React.CSSProperties;
}

/**
 * Flash animation keyframes (inline style approach)
 */
const FLASH_DURATION = 1000; // ms

/**
 * Format large numbers with K/M suffix
 */
function formatNumber(n: number): string {
  if (n >= 1000000) {
    return `${(n / 1000000).toFixed(1)}M`;
  }
  if (n >= 1000) {
    return `${(n / 1000).toFixed(1)}K`;
  }
  return n.toFixed(0);
}

/**
 * Format time in seconds to human readable
 */
function formatTime(seconds: number): string {
  if (seconds >= 3600) {
    return `${(seconds / 3600).toFixed(1)}h`;
  }
  if (seconds >= 60) {
    return `${(seconds / 60).toFixed(1)}m`;
  }
  return `${seconds.toFixed(1)}s`;
}

/**
 * Format percentage
 */
function formatPercent(ratio: number): string {
  return `${(ratio * 100).toFixed(1)}%`;
}

/**
 * Format relative time
 */
function formatRelativeTime(timestamp: number): string {
  const now = Date.now();
  const diff = now - timestamp;
  const seconds = Math.floor(diff / 1000);

  if (seconds < 5) return 'just now';
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return `${Math.floor(seconds / 3600)}h ago`;
}

/**
 * Progress bar component
 */
function ProgressBar({
  value,
  max,
  color,
  height = 6,
}: {
  value: number;
  max: number;
  color: string;
  height?: number;
}) {
  const percentage = max > 0 ? Math.min(100, (value / max) * 100) : 0;

  return (
    <div
      style={{
        width: '100%',
        height,
        background: 'var(--color-bg-tertiary, #0f172a)',
        borderRadius: height / 2,
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          width: `${percentage}%`,
          height: '100%',
          background: color,
          borderRadius: height / 2,
          transition: 'width 300ms ease',
        }}
      />
    </div>
  );
}

/**
 * ComputeLedger Component
 *
 * An always-visible HUD panel showing:
 * - Base episodes (acting)
 * - Probe episodes (evaluation)
 * - Probe overhead ratio
 * - Wall-time split
 * - Reward per total episode / per wall-time
 */
export function ComputeLedger({
  ledger,
  compact = false,
  onVerifyPending,
  className = '',
  style,
}: ComputeLedgerProps) {
  // Track previous values for flash animation
  const prevProbeEpisodes = useRef<number | null>(null);
  const prevWallTime = useRef<number | null>(null);
  const [flashProbeEpisodes, setFlashProbeEpisodes] = useState(false);
  const [flashWallTime, setFlashWallTime] = useState(false);

  // Detect changes and trigger flash
  useEffect(() => {
    if (ledger) {
      if (prevProbeEpisodes.current !== null && prevProbeEpisodes.current !== ledger.probeEpisodes) {
        setFlashProbeEpisodes(true);
        const timer = setTimeout(() => setFlashProbeEpisodes(false), FLASH_DURATION);
        return () => clearTimeout(timer);
      }
      prevProbeEpisodes.current = ledger.probeEpisodes;
    }
  }, [ledger?.probeEpisodes]);

  useEffect(() => {
    if (ledger) {
      const currentWallTime = ledger.wallTimeSplit.probe;
      if (prevWallTime.current !== null && prevWallTime.current !== currentWallTime) {
        setFlashWallTime(true);
        const timer = setTimeout(() => setFlashWallTime(false), FLASH_DURATION);
        return () => clearTimeout(timer);
      }
      prevWallTime.current = currentWallTime;
    }
  }, [ledger?.wallTimeSplit.probe]);

  if (!ledger) {
    return (
      <div
        className={className}
        style={{
          padding: compact ? 8 : 16,
          background: 'var(--color-bg-secondary, #16213e)',
          borderRadius: 8,
          fontFamily: 'system-ui, sans-serif',
          color: 'var(--color-text-muted, #a0a0a0)',
          fontSize: 12,
          ...style,
        }}
      >
        No compute data available
      </div>
    );
  }

  const totalEpisodes = ledger.baseEpisodes + ledger.probeEpisodes;
  const totalWallTime = ledger.wallTimeSplit.base + ledger.wallTimeSplit.probe;

  // Flash style helper
  const getFlashStyle = (isFlashing: boolean) => ({
    transition: 'background-color 300ms ease',
    backgroundColor: isFlashing ? 'var(--color-success, #10b981)44' : 'transparent',
    borderRadius: 4,
    padding: isFlashing ? '2px 4px' : 0,
  });

  if (compact) {
    // Compact HUD mode
    return (
      <div
        className={`compute-ledger compute-ledger--compact ${className}`}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '6px 12px',
          background: 'var(--color-bg-secondary, #16213e)',
          borderRadius: 6,
          fontFamily: 'system-ui, sans-serif',
          fontSize: 11,
          color: 'var(--color-text, #eaeaea)',
          ...style,
        }}
      >
        <span title="Base + Probe Episodes" style={getFlashStyle(flashProbeEpisodes)}>
          <span style={{ color: 'var(--color-text-muted, #a0a0a0)' }}>Ep:</span>{' '}
          {formatNumber(ledger.baseEpisodes)}+
          <span style={{ fontWeight: flashProbeEpisodes ? 700 : 400 }}>
            {formatNumber(ledger.probeEpisodes)}
          </span>
        </span>
        <span title="Probe Overhead Ratio" style={{ color: ledger.probeOverheadRatio > 0.3 ? 'var(--color-warning, #f59e0b)' : undefined }}>
          <span style={{ color: 'var(--color-text-muted, #a0a0a0)' }}>OH:</span>{' '}
          {formatPercent(ledger.probeOverheadRatio)}
        </span>
        <span title="Reward per Episode">
          <span style={{ color: 'var(--color-text-muted, #a0a0a0)' }}>R/ep:</span>{' '}
          {ledger.rewardPerTotalEpisode.toFixed(2)}
        </span>
        {ledger.pendingVerificationCost.episodes > 0 && onVerifyPending && (
          <button
            onClick={onVerifyPending}
            style={{
              padding: '2px 6px',
              borderRadius: 3,
              border: 'none',
              background: 'var(--color-primary, #e94560)',
              color: '#ffffff',
              fontSize: 10,
              cursor: 'pointer',
            }}
            title={`Pending: ~${ledger.pendingVerificationCost.episodes} episodes`}
          >
            Verify ({ledger.pendingVerificationCost.episodes})
          </button>
        )}
      </div>
    );
  }

  // Full mode
  return (
    <div
      className={`compute-ledger ${className}`}
      style={{
        padding: 16,
        background: 'var(--color-bg-secondary, #16213e)',
        borderRadius: 8,
        fontFamily: 'system-ui, sans-serif',
        color: 'var(--color-text, #eaeaea)',
        ...style,
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          Compute Ledger
        </h3>
        <span style={{ fontSize: 10, color: 'var(--color-text-muted, #a0a0a0)' }}>
          {formatRelativeTime(ledger.lastUpdated)}
        </span>
      </div>

      {/* Episode breakdown */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <span style={{ fontSize: 12, color: 'var(--color-text-muted, #a0a0a0)' }}>Episodes</span>
          <span style={{ fontSize: 12 }}>{formatNumber(totalEpisodes)} total</span>
        </div>
        <div style={{ display: 'flex', gap: 2, marginBottom: 8 }}>
          <div
            style={{
              flex: ledger.baseEpisodes,
              height: 20,
              background: 'var(--color-success, #10b981)',
              borderRadius: '4px 0 0 4px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 10,
              fontWeight: 600,
              color: '#ffffff',
            }}
          >
            Base: {formatNumber(ledger.baseEpisodes)}
          </div>
          <div
            style={{
              flex: ledger.probeEpisodes,
              height: 20,
              background: 'var(--color-warning, #f59e0b)',
              borderRadius: '0 4px 4px 0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 10,
              fontWeight: 600,
              color: '#000000',
            }}
          >
            Probe: {formatNumber(ledger.probeEpisodes)}
          </div>
        </div>
      </div>

      {/* Overhead ratio */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
          <span style={{ fontSize: 12, color: 'var(--color-text-muted, #a0a0a0)' }}>Probe Overhead</span>
          <span
            style={{
              fontSize: 14,
              fontWeight: 600,
              color: ledger.probeOverheadRatio > 0.3
                ? 'var(--color-warning, #f59e0b)'
                : ledger.probeOverheadRatio > 0.5
                ? 'var(--color-error, #ef4444)'
                : 'var(--color-success, #10b981)',
            }}
          >
            {formatPercent(ledger.probeOverheadRatio)}
          </span>
        </div>
        <ProgressBar
          value={ledger.probeEpisodes}
          max={totalEpisodes}
          color={
            ledger.probeOverheadRatio > 0.3
              ? 'var(--color-warning, #f59e0b)'
              : 'var(--color-success, #10b981)'
          }
        />
      </div>

      {/* Wall time split */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
          <span style={{ fontSize: 12, color: 'var(--color-text-muted, #a0a0a0)' }}>Wall Time</span>
          <span style={{ fontSize: 12 }}>{formatTime(totalWallTime)} total</span>
        </div>
        <div style={{ display: 'flex', gap: 8, fontSize: 11 }}>
          <span>Base: {formatTime(ledger.wallTimeSplit.base)}</span>
          <span style={{ color: 'var(--color-text-muted, #a0a0a0)' }}>|</span>
          <span style={getFlashStyle(flashWallTime)}>
            Probe: <span style={{ fontWeight: flashWallTime ? 700 : 400 }}>{formatTime(ledger.wallTimeSplit.probe)}</span>
          </span>
        </div>
      </div>

      {/* Reward metrics */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 12, color: 'var(--color-text-muted, #a0a0a0)', marginBottom: 8 }}>
          Reward Efficiency
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div style={{ padding: 10, background: 'var(--color-bg-tertiary, #0f172a)', borderRadius: 6 }}>
            <div style={{ fontSize: 10, color: 'var(--color-text-muted, #a0a0a0)', marginBottom: 4 }}>
              Per Episode
            </div>
            <div style={{ fontSize: 16, fontWeight: 600 }}>
              {ledger.rewardPerTotalEpisode.toFixed(3)}
            </div>
          </div>
          <div style={{ padding: 10, background: 'var(--color-bg-tertiary, #0f172a)', borderRadius: 6 }}>
            <div style={{ fontSize: 10, color: 'var(--color-text-muted, #a0a0a0)', marginBottom: 4 }}>
              Per Second
            </div>
            <div style={{ fontSize: 16, fontWeight: 600 }}>
              {ledger.rewardPerWallTimeSecond.toFixed(3)}
            </div>
          </div>
        </div>
      </div>

      {/* Total reward */}
      <div
        style={{
          padding: 12,
          background: 'var(--color-bg-tertiary, #0f172a)',
          borderRadius: 6,
          marginBottom: 16,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <span style={{ fontSize: 12, color: 'var(--color-text-muted, #a0a0a0)' }}>Total Reward</span>
        <span style={{ fontSize: 18, fontWeight: 700, color: 'var(--color-success, #10b981)' }}>
          {ledger.totalReward.toFixed(1)}
        </span>
      </div>

      {/* Pending verifications */}
      {ledger.pendingVerificationCost.episodes > 0 && (
        <div
          style={{
            padding: 12,
            background: 'var(--color-warning, #f59e0b)22',
            border: '1px solid var(--color-warning, #f59e0b)',
            borderRadius: 6,
          }}
        >
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-warning, #f59e0b)', marginBottom: 4 }}>
            Pending Verifications
          </div>
          <div style={{ fontSize: 12, marginBottom: 8 }}>
            ~{ledger.pendingVerificationCost.episodes} episodes / ~{formatTime(ledger.pendingVerificationCost.seconds)}
          </div>
          {onVerifyPending && (
            <button
              onClick={onVerifyPending}
              style={{
                width: '100%',
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
              Verify All Pending Edges
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default ComputeLedger;
