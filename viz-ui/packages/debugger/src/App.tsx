import { useCallback } from 'react';
import { useDebuggerStore } from '@/store';
import { useWebSocket } from '@/hooks';
import { useShallow } from 'zustand/react/shallow';

import { TimelinePanel } from '@/features/timeline';
import { CausalGraphPanel } from '@/features/causal-graph';
import { ParetoFrontierPanel } from '@/features/pareto-frontier';
import { EventInspector } from '@/features/event-inspector';
import { ErrorBoundary } from '@/app/ErrorBoundary';
import { RunSelector, SchemaBanner } from '@/components';

/**
 * Main Reckon Debugger Application
 *
 * Provides three visualization modes:
 * - Timeline: chronological view of memory events (custom canvas)
 * - Relationship graph: directed record dependencies (React Flow)
 * - Pareto Frontier: budget vs performance tradeoffs (Plotly)
 */
function App() {
  // Store state - use useShallow for object selectors to prevent infinite loops
  const viewMode = useDebuggerStore((s) => s.viewMode);
  const sidebarOpen = useDebuggerStore((s) => s.sidebarOpen);

  // Connection info - use shallow comparison
  const connectionInfo = useDebuggerStore(
    useShallow((s) => ({
      status: s.connectionStatus,
      url: s.wsUrl,
      error: s.lastError,
      isConnected: s.connectionStatus === 'connected',
    }))
  );

  // Event stats - use shallow comparison
  const eventStats = useDebuggerStore(
    useShallow((s) => ({
      total: s.events.length,
    }))
  );

  // Store actions
  const setViewMode = useDebuggerStore((s) => s.setViewMode);
  const clearEvents = useDebuggerStore((s) => s.clearEvents);
  const toggleSidebar = useDebuggerStore((s) => s.toggleSidebar);

  // WebSocket
  const { connect, disconnect, subscribeToRun } = useWebSocket();

  const handleConnectionToggle = useCallback(() => {
    if (connectionInfo.isConnected) {
      disconnect();
    } else {
      connect();
    }
  }, [connectionInfo.isConnected, connect, disconnect]);

  return (
    <div className="h-screen flex flex-col bg-[var(--color-bg)] text-[var(--color-text)]">
      {/* Schema version warning banner */}
      <SchemaBanner />

      {/* Header */}
      <header className="flex items-center justify-between px-5 py-3 bg-[var(--color-bg-secondary)]">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-semibold">Reckon Debugger</h1>

          {/* Run selector */}
          <RunSelector connect={connect} subscribeToRun={subscribeToRun} />

          {/* View mode tabs */}
          <nav className="flex gap-1">
            <ViewTab
              active={viewMode === 'timeline'}
              onClick={() => setViewMode('timeline')}
            >
              Timeline
            </ViewTab>
            <ViewTab
              active={viewMode === 'causal'}
              onClick={() => setViewMode('causal')}
            >
              Relationship graph
            </ViewTab>
            <ViewTab
              active={viewMode === 'pareto'}
              onClick={() => setViewMode('pareto')}
            >
              Pareto Frontier
            </ViewTab>
          </nav>
        </div>

        <div className="flex items-center gap-3">
          {/* Event stats */}
          <span className="text-xs text-[var(--color-text-muted)]">
            {eventStats.total} events
          </span>

          {/* Connection status */}
          <span className={`status-${connectionInfo.status} text-sm`}>
            {connectionInfo.status === 'connected'
              ? 'Connected'
              : connectionInfo.status === 'connecting'
              ? 'Connecting...'
              : connectionInfo.error || 'Disconnected'}
          </span>

          {/* Connection button */}
          <button
            onClick={handleConnectionToggle}
            className="px-3 py-1.5 bg-[var(--color-accent)] hover:bg-[var(--color-primary)] rounded text-sm transition-colors"
          >
            {connectionInfo.isConnected ? 'Disconnect' : 'Connect'}
          </button>

          {/* Clear button */}
          <button
            onClick={clearEvents}
            className="px-3 py-1.5 border border-[var(--color-accent)] hover:border-[var(--color-primary)] rounded text-sm transition-colors"
          >
            Clear
          </button>

          {/* Sidebar toggle */}
          <button
            onClick={toggleSidebar}
            className="px-2 py-1.5 hover:bg-[var(--color-accent)] rounded transition-colors"
            title={sidebarOpen ? 'Hide sidebar' : 'Show sidebar'}
          >
            <svg
              className="w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              {sidebarOpen ? (
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M13 5l7 7-7 7M5 5l7 7-7 7"
                />
              ) : (
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M11 19l-7-7 7-7m8 14l-7-7 7-7"
                />
              )}
            </svg>
          </button>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 flex gap-4 p-4 min-h-0">
        {/* Visualization panel */}
        <div className="flex-1 min-w-0">
          <ErrorBoundary>
            {viewMode === 'timeline' && <TimelinePanel />}
            {viewMode === 'causal' && <CausalGraphPanel />}
            {viewMode === 'pareto' && <ParetoFrontierPanel />}
          </ErrorBoundary>
        </div>

        {/* Sidebar */}
        {sidebarOpen && (
          <aside className="w-80 flex-shrink-0">
            <EventInspector />
          </aside>
        )}
      </main>
    </div>
  );
}

/**
 * View tab button
 */
function ViewTab({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 rounded text-sm transition-colors ${
        active
          ? 'bg-[var(--color-primary)] text-white'
          : 'hover:bg-[var(--color-accent)]'
      }`}
    >
      {children}
    </button>
  );
}

export default App;
