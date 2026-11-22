import { useCallback } from 'react';
import { ParetoFrontier, type ParetoPoint } from '@rtepl/reckon-components';
import { useDebuggerStore } from '@/store';
import { selectIsLoading } from '@/store/selectors';

/**
 * Pareto Frontier feature panel.
 *
 * Wraps the ParetoFrontier component with store integration.
 */
export function ParetoFrontierPanel() {
  // Select state from store
  const events = useDebuggerStore((s) => s.events);
  const selectedEpisodeId = useDebuggerStore((s) => s.selectedEpisodeId);
  const isLoading = useDebuggerStore(selectIsLoading);

  // Get actions
  const selectEpisode = useDebuggerStore((s) => s.selectEpisode);

  // Event handlers
  const handlePointClick = useCallback(
    (point: ParetoPoint) => {
      if (point.episodeId) {
        selectEpisode(point.episodeId);
      }
    },
    [selectEpisode]
  );

  // Count configurations with data
  const configCount = events.filter(
    (e) => e.finalUsage && e.initialBudget
  ).length;

  // Loading skeleton
  if (isLoading) {
    return (
      <div className="flex flex-col h-full bg-[var(--color-bg-secondary)] rounded-lg overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-accent)]">
          <span className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            Budget and operation counts
          </span>
          <span className="text-xs text-[var(--color-text-dim)]">
            Loading...
          </span>
        </div>
        <div className="flex-1 min-h-0 flex items-center justify-center">
          <div className="animate-pulse flex flex-col items-center gap-4">
            <div className="w-48 h-4 bg-[var(--color-accent)] rounded" />
            <div className="w-32 h-4 bg-[var(--color-accent)] rounded opacity-60" />
            <div className="w-24 h-4 bg-[var(--color-accent)] rounded opacity-40" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-[var(--color-bg-secondary)] rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-accent)]">
        <span className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Budget and operation counts
        </span>
        <span className="text-xs text-[var(--color-text-dim)]">
          {configCount} configurations
        </span>
      </div>
      <div className="flex-1 min-h-0">
        <ParetoFrontier
          events={events}
          selectedPointLabel={selectedEpisodeId}
          onPointClick={handlePointClick}
          showFrontierLine
          showDominatedPoints
        />
      </div>
    </div>
  );
}

export default ParetoFrontierPanel;
