import { useEffect, useCallback } from 'react';
import { useDebuggerStore } from '@/store';
import { useRuns } from '@/hooks';

/**
 * Run selector component.
 *
 * Displays a dropdown to select from available runs.
 * When a run is selected, it clears existing events and
 * connects to the WebSocket with the selected run_id.
 */
export function RunSelector({ connect, subscribeToRun }: { connect: () => void; subscribeToRun: (runId: string) => void }) {
  const { runs, isLoading, error, refresh } = useRuns();

  const selectedRunId = useDebuggerStore((s) => s.selectedRunId);
  const connectionStatus = useDebuggerStore((s) => s.connectionStatus);
  const selectRun = useDebuggerStore((s) => s.selectRun);
  const clearEvents = useDebuggerStore((s) => s.clearEvents);
  const currentRunSummary = useDebuggerStore((s) => s.currentRunSummary);

  // Handle run selection
  const handleRunSelect = useCallback(
    (runId: string) => {
      if (runId === selectedRunId) return;

      // Clear existing events when switching runs
      clearEvents();

      // Select the new run
      selectRun(runId);

      // Always use subscribeToRun if connected - it will send the subscribe message
      // and the server will respond with a snapshot
      if (connectionStatus === 'connected') {
        subscribeToRun(runId);
      } else if (connectionStatus === 'disconnected') {
        connect();
      }
    },
    [selectedRunId, connectionStatus, clearEvents, selectRun, subscribeToRun, connect]
  );

  // Auto-select first run if none selected
  useEffect(() => {
    if (!selectedRunId && runs.length > 0) {
      const firstRun = runs[0];
      if (firstRun) {
        handleRunSelect(firstRun.run_id);
      }
    }
  }, [runs, selectedRunId, handleRunSelect]);

  // Format date for display
  const formatDate = (timestamp: number) => {
    if (!timestamp) return '';
    return new Date(timestamp).toLocaleDateString();
  };

  return (
    <div className="flex items-center gap-2">
      {/* Run selector dropdown */}
      <select
        value={selectedRunId || ''}
        onChange={(e) => handleRunSelect(e.target.value)}
        disabled={isLoading}
        className="px-2 py-1.5 bg-[var(--color-bg)] border border-[var(--color-accent)] rounded text-sm min-w-[200px]"
      >
        {!selectedRunId && <option value="">Select a run...</option>}
        {runs.map((run) => (
          <option key={run.run_id} value={run.run_id}>
            {run.task_name || 'unknown'} / {run.policy_name || 'unknown'} ({formatDate(run.created_at)})
          </option>
        ))}
      </select>

      {/* Refresh button */}
      <button
        onClick={refresh}
        disabled={isLoading}
        className="px-2 py-1.5 hover:bg-[var(--color-accent)] rounded transition-colors"
        title="Refresh runs"
      >
        <svg
          className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
          />
        </svg>
      </button>

      {/* Run info */}
      {currentRunSummary && (
        <span className="text-xs text-[var(--color-text-muted)]">
          {currentRunSummary.num_episodes} episodes
          {currentRunSummary.success_rate != null ? (
            <> | {(currentRunSummary.success_rate * 100).toFixed(0)}% success</>
          ) : (
            <> | Success unavailable</>
          )}
        </span>
      )}

      {/* Error indicator */}
      {error && (
        <span className="text-xs text-red-500" title={error}>
          Failed to load runs
        </span>
      )}
    </div>
  );
}

export default RunSelector;
