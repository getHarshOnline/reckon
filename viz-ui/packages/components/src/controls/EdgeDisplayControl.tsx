import { useState } from 'react';
import { EdgeDisplayMode } from '../types';

/**
 * Verification queue state for display
 */
export interface VerificationQueueInfo {
  pendingProbes: number;
  estimatedCostEpisodes: number;
  estimatedCostSeconds: number;
}

/**
 * Props for EdgeDisplayControl component
 */
export interface EdgeDisplayControlProps {
  /** Current edge display choice */
  mode: EdgeDisplayMode;
  /** Callback when mode changes */
  onModeChange: (mode: EdgeDisplayMode) => void;
  /** Number of inferred edges available */
  inferredEdgeCount?: number;
  /** Number of unverified edges that can be verified */
  unverifiedEdgeCount?: number;
  /** Callback when user wants to verify all implied edges */
  onVerifyAll?: () => void;
  /** Estimated cost to verify all */
  verifyAllCostEpisodes?: number;
  /** Estimated wall time for verification */
  verifyAllCostSeconds?: number;
  /** Whether verification is currently in progress */
  isVerifying?: boolean;
  /** Caller-supplied queue details shown in PROBE_STATUS mode */
  verificationQueue?: VerificationQueueInfo;
  /** Custom class name */
  className?: string;
  /** Custom styles */
  style?: React.CSSProperties;
}

/**
 * EdgeDisplayControl Component
 *
 * Choose how supplied edges appear and show optional probe costs and queue.
 * The parent applies the filter and handles requested probes; this control
 * neither computes closure nor executes or validates a measurement.
 */
export function EdgeDisplayControl({
  mode,
  onModeChange,
  inferredEdgeCount = 0,
  unverifiedEdgeCount = 0,
  onVerifyAll,
  verifyAllCostEpisodes = 0,
  verifyAllCostSeconds = 0,
  isVerifying = false,
  verificationQueue,
  className = '',
  style,
}: EdgeDisplayControlProps) {
  // Confirmation state for verification
  const [showConfirmation, setShowConfirmation] = useState(false);
  const confirmationCostEpisodes = mode === EdgeDisplayMode.PROBE_STATUS
    ? verificationQueue?.estimatedCostEpisodes ?? 0 : verifyAllCostEpisodes;
  const confirmationCostSeconds = mode === EdgeDisplayMode.PROBE_STATUS
    ? verificationQueue?.estimatedCostSeconds ?? 0 : verifyAllCostSeconds;

  const modes: { value: EdgeDisplayMode; label: string; description: string }[] = [
    { value: EdgeDisplayMode.MEASURED_ONLY, label: 'Measured', description: 'Pairs with direct probe evidence' },
    { value: EdgeDisplayMode.INCLUDE_UNMEASURED, label: 'All supplied', description: 'Include supplied inferences and enabled proxies; Product view still limits these' },
    { value: EdgeDisplayMode.PROBE_STATUS, label: 'Probe status', description: 'Measured pairs and any supplied probe queue' },
  ];

  const handleVerifyClick = () => {
    setShowConfirmation(true);
  };

  const handleConfirmVerify = () => {
    setShowConfirmation(false);
    onVerifyAll?.();
  };

  const handleCancelVerify = () => {
    setShowConfirmation(false);
  };

  return (
    <div
      className={`edge-display-control ${className}`}
      style={{
        fontFamily: 'system-ui, sans-serif',
        ...style,
      }}
    >
      {/* Mode selector */}
      <div
        style={{
          display: 'flex',
          background: 'var(--color-bg-tertiary, #0f172a)',
          borderRadius: 6,
          padding: 2,
        }}
      >
        {modes.map((m) => (
          <button
            key={m.value}
            onClick={() => { setShowConfirmation(false); onModeChange(m.value); }}
            disabled={isVerifying}
            style={{
              flex: 1,
              padding: '6px 12px',
              border: 'none',
              borderRadius: 4,
              fontSize: 12,
              fontWeight: 500,
              cursor: isVerifying ? 'not-allowed' : 'pointer',
              background: mode === m.value ? 'var(--color-primary, #e94560)' : 'transparent',
              color: mode === m.value ? '#ffffff' : 'var(--color-text, #eaeaea)',
              opacity: isVerifying ? 0.5 : 1,
              transition: 'all 150ms ease',
            }}
            title={m.description}
          >
            {m.label}
          </button>
        ))}
      </div>

      {/* Explain unmeasured edges and any available probe action. */}
      {mode === EdgeDisplayMode.INCLUDE_UNMEASURED && (
        <div
          style={{
            marginTop: 8,
            padding: 10,
            background: 'var(--color-warning, #f59e0b)22',
            border: '1px solid var(--color-warning, #f59e0b)',
            borderRadius: 6,
            fontSize: 11,
            color: 'var(--color-text, #eaeaea)',
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: 4, color: 'var(--color-warning, #f59e0b)' }}>
            Implied edges are NOT directly tested
          </div>
          <div>
            Showing {inferredEdgeCount} implied (unverified) edge{inferredEdgeCount !== 1 ? 's' : ''}.
            A direct probe is required to assess an implied pair.
          </div>
          {onVerifyAll && unverifiedEdgeCount > 0 && !showConfirmation && (
            <button
              onClick={handleVerifyClick}
              disabled={isVerifying}
              style={{
                marginTop: 8,
                width: '100%',
                padding: '6px 10px',
                borderRadius: 4,
                border: 'none',
                background: isVerifying ? 'var(--color-accent, #0f3460)' : 'var(--color-primary, #e94560)',
                color: '#ffffff',
                fontSize: 11,
                fontWeight: 500,
                cursor: isVerifying ? 'not-allowed' : 'pointer',
              }}
            >
              {isVerifying
                ? 'Verifying...'
                : `Run ${unverifiedEdgeCount} probe${unverifiedEdgeCount !== 1 ? 's' : ''} (~${verifyAllCostEpisodes} episodes)`}
            </button>
          )}

        </div>
      )}

      {/* Measured edges can coexist with a caller-supplied pending probe queue. */}
      {mode === EdgeDisplayMode.PROBE_STATUS && (
        <div
          style={{
            marginTop: 8,
            padding: 10,
            background: 'var(--color-success, #10b981)22',
            border: '1px solid var(--color-success, #10b981)',
            borderRadius: 6,
            fontSize: 11,
            color: 'var(--color-text, #eaeaea)',
          }}
        >
          <div style={{ fontWeight: 600, color: 'var(--color-success, #10b981)' }}>
            Showing pairs with direct probe evidence
          </div>
          <div style={{ marginTop: 4 }}>
            All displayed edges have been directly tested with probes.
          </div>
          {/* Verification queue display */}
          {verificationQueue && verificationQueue.pendingProbes > 0 && (
            <div
              style={{
                marginTop: 10,
                padding: 8,
                background: 'var(--color-bg-tertiary, #0f172a)',
                borderRadius: 4,
              }}
            >
              <div style={{ fontWeight: 600, color: 'var(--color-warning, #f59e0b)', marginBottom: 4 }}>
                Verification Queue
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
                <span>Pending probes:</span>
                <span style={{ fontWeight: 500 }}>{verificationQueue.pendingProbes}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
                <span>Estimated cost:</span>
                <span style={{ fontWeight: 500 }}>~{verificationQueue.estimatedCostEpisodes} episodes</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Estimated time:</span>
                <span style={{ fontWeight: 500 }}>~{verificationQueue.estimatedCostSeconds.toFixed(0)}s</span>
              </div>
              {onVerifyAll && !showConfirmation && (
                <button
                  onClick={handleVerifyClick}
                  disabled={isVerifying}
                  style={{
                    marginTop: 8,
                    width: '100%',
                    padding: '6px 10px',
                    borderRadius: 4,
                    border: 'none',
                    background: isVerifying ? 'var(--color-accent, #0f3460)' : 'var(--color-primary, #e94560)',
                    color: '#ffffff',
                    fontSize: 11,
                    fontWeight: 500,
                    cursor: isVerifying ? 'not-allowed' : 'pointer',
                  }}
                >
                  {isVerifying
                    ? 'Running probes...'
                    : `Run ${verificationQueue.pendingProbes} probes (~${verificationQueue.estimatedCostEpisodes} ep)`}
                </button>
              )}
            </div>
          )}
        </div>
      )}
      {/* Verification confirmation dialog */}
      {showConfirmation && onVerifyAll && (
        <div
          style={{
            marginTop: 8,
            padding: 10,
            background: 'var(--color-bg-tertiary, #0f172a)',
            borderRadius: 4,
            border: '1px solid var(--color-primary, #e94560)',
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: 6, color: 'var(--color-primary, #e94560)' }}>
            Confirm Verification
          </div>
          <div style={{ marginBottom: 8 }}>
            This will cost:
            <ul style={{ margin: '4px 0', paddingLeft: 16 }}>
              <li>~{confirmationCostEpisodes} episodes</li>
              <li>~{confirmationCostSeconds.toFixed(0)}s estimated wall time</li>
            </ul>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={handleConfirmVerify}
              disabled={isVerifying}
              style={{
                flex: 1,
                padding: '6px 10px',
                borderRadius: 4,
                border: 'none',
                background: 'var(--color-primary, #e94560)',
                color: '#ffffff',
                fontSize: 11,
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              Run Probes
            </button>
            <button
              onClick={handleCancelVerify}
              style={{
                flex: 1,
                padding: '6px 10px',
                borderRadius: 4,
                border: '1px solid var(--color-accent, #0f3460)',
                background: 'transparent',
                color: 'var(--color-text, #eaeaea)',
                fontSize: 11,
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default EdgeDisplayControl;
