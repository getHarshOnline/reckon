import { useCallback } from 'react';
import { Timeline, type DebuggerEvent } from '@rtepl/reckon-components';
import { useDebuggerStore, selectVisibleEvents } from '@/store';
import { selectIsLoading } from '@/store/selectors';

/**
 * Timeline feature panel.
 *
 * Wraps the Timeline component with store integration.
 */
export function TimelinePanel() {
  // Select state from store
  const events = useDebuggerStore(selectVisibleEvents);
  const omittedEvents = useDebuggerStore((s) => s.omittedEvents);
  const allEvents = useDebuggerStore((s) => s.events);
  const timeRange = useDebuggerStore((s) => s.timeRange);
  const selectedEventId = useDebuggerStore((s) => s.selectedEventId);
  const isLoading = useDebuggerStore(selectIsLoading);

  // Get actions
  const selectEvent = useDebuggerStore((s) => s.selectEvent);
  const setTimeRange = useDebuggerStore((s) => s.setTimeRange);

  const selectedIndex = allEvents.findIndex(event => event.eventId === selectedEventId);

  // Event handlers
  const handleEventClick = useCallback(
    (event: DebuggerEvent) => {
      selectEvent(event.eventId);
    },
    [selectEvent]
  );

  const handleTimeRangeChange = useCallback(
    (range: [number, number]) => {
      setTimeRange(range);
    },
    [setTimeRange]
  );

  // Loading skeleton
  if (isLoading) {
    return (
      <div className="flex flex-col h-full bg-[var(--color-bg-secondary)] rounded-lg overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-accent)]">
          <span className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            Memory Timeline
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
          Memory Timeline
        </span>
        <span className="text-xs text-[var(--color-text-dim)]">
          {events.length} events
        </span>
      </div>
      {omittedEvents > 0 && <p role="status" className="px-4 py-2 text-sm">Showing the most recent {allEvents.length} events; {omittedEvents} earlier events remain in server storage. Export or page through the stored run for the complete history.</p>}
      <div className="flex items-center gap-3 px-4 py-2 text-sm" aria-label="Event navigation">
        <button disabled={selectedIndex <= 0} onClick={() => selectEvent(allEvents[selectedIndex - 1]!.eventId)}>Previous event</button>
        <span>{selectedIndex < 0 ? 'No event selected' : `Event ${selectedIndex + 1} of ${allEvents.length}`}</span>
        <button disabled={selectedIndex + 1 >= allEvents.length} onClick={() => selectEvent(allEvents[selectedIndex + 1]!.eventId)}>Next event</button>
      </div>
      <div className="flex-1 min-h-0">
        <Timeline
          events={events}
          timeRange={timeRange}
          selectedEventId={selectedEventId}
          onEventClick={handleEventClick}
          onTimeRangeChange={handleTimeRangeChange}
        />
      </div>
    </div>
  );
}

export default TimelinePanel;
