import { useEffect, useCallback, useState } from 'react';
import { useDebuggerStore } from '@/store';
import type { AvailableRun } from '@/store';

/**
 * API base URL for the viz server.
 * Uses window.location in browser, falls back to localhost for SSR.
 */
function getApiBaseUrl(): string {
  if (typeof window === 'undefined') {
    return 'http://localhost:8000';
  }
  const protocol = window.location.protocol;
  const host = window.location.hostname;
  const port = '8000'; // Viz server default port
  return `${protocol}//${host}:${port}`;
}

interface UseRunsReturn {
  /** Available runs from the server */
  runs: AvailableRun[];
  /** Loading state */
  isLoading: boolean;
  /** Error message if fetch failed */
  error: string | null;
  /** Refresh the runs list */
  refresh: () => Promise<void>;
  /** Select a run by ID */
  selectRun: (runId: string) => void;
}

/**
 * Hook for managing available runs.
 *
 * Fetches the list of runs from the server and provides
 * selection functionality.
 *
 * @example
 * ```tsx
 * const { runs, isLoading, selectRun } = useRuns();
 *
 * return (
 *   <select onChange={(e) => selectRun(e.target.value)}>
 *     {runs.map(run => (
 *       <option key={run.run_id} value={run.run_id}>
 *         {run.task_name} - {run.policy_name}
 *       </option>
 *     ))}
 *   </select>
 * );
 * ```
 */
export function useRuns(): UseRunsReturn {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runs = useDebuggerStore((s) => s.availableRuns);
  const setAvailableRuns = useDebuggerStore((s) => s.setAvailableRuns);
  const storeSelectRun = useDebuggerStore((s) => s.selectRun);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const baseUrl = getApiBaseUrl();
      const response = await fetch(`${baseUrl}/v1/runs?limit=50`);

      if (!response.ok) {
        throw new Error(`Failed to fetch runs: ${response.status}`);
      }

      const data = await response.json();

      // Convert to AvailableRun format
      const availableRuns: AvailableRun[] = data.runs.map((run: {
        run_id: string;
        task_name: string;
        policy_name: string;
        created_at: number;
      }) => ({
        run_id: run.run_id,
        task_name: run.task_name || 'unknown',
        policy_name: run.policy_name || 'unknown',
        created_at: run.created_at,
      }));

      setAvailableRuns(availableRuns);
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Unknown error';
      setError(message);
      console.error('Failed to fetch runs:', e);
    } finally {
      setIsLoading(false);
    }
  }, [setAvailableRuns]);

  // Fetch runs on mount
  useEffect(() => {
    refresh();
  }, [refresh]);

  const selectRun = useCallback((runId: string) => {
    storeSelectRun(runId);
  }, [storeSelectRun]);

  return {
    runs,
    isLoading,
    error,
    refresh,
    selectRun,
  };
}

export default useRuns;
