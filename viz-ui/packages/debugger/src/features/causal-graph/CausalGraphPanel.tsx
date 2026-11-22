import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  CausalGraph,
  collectGraphRecords,
  projectCausalEdges,
  EdgeDrawer,
  ViolationsPanel,
  ComputeLedger,
  EdgeDisplayControl,
  TruthModeSwitch,
  EdgeLegend,
  type MemoryRecord,
  type CausalEdge,
  EdgeType,
  TruthMode,
} from '@rtepl/reckon-components';
import { useShallow } from 'zustand/react/shallow';
import { useDebuggerStore, selectCausalGraphState } from '@/store';

/** Threshold for large graph warning */
const LARGE_GRAPH_THRESHOLD = 100;
/** Threshold for very large graph (auto-filter recommendation) */
const VERY_LARGE_GRAPH_THRESHOLD = 500;

/**
 * Relationship graph feature panel.
 *
 * Wraps the CausalGraph component with store integration and provides:
 * - Edge display control
 * - Truth mode switch
 * - Edge legend
 * - Violations panel
 * - Compute ledger
 * - Edge detail drawer
 */
export function CausalGraphPanel() {
  // Select state from store
  const events = useDebuggerStore((s) => s.events);
  const selectedRecordId = useDebuggerStore((s) => s.selectedRecordId);
  const inferredEdges = useDebuggerStore((s) => s.inferredEdges);
  const transitivityReport = useDebuggerStore((s) => s.transitivityReport);
  const computeLedger = useDebuggerStore((s) => s.computeLedger);
  const edgeStatuses = useDebuggerStore((s) => s.edgeStatuses);

  // Use selectors for derived state - wrap with useShallow for object-returning selectors
  const causalGraphState = useDebuggerStore(useShallow(selectCausalGraphState));

  // Focus mode state
  const focusMode = useDebuggerStore((s) => s.focusMode);
  const setFocusMode = useDebuggerStore((s) => s.setFocusMode);
  const toggleFocusMode = useDebuggerStore((s) => s.toggleFocusMode);
  const verificationQueue = useDebuggerStore((s) => s.verificationQueue);

  // Get actions
  const selectRecord = useDebuggerStore((s) => s.selectRecord);
  const selectEdge = useDebuggerStore((s) => s.selectEdge);
  const openEdgeDrawer = useDebuggerStore((s) => s.openEdgeDrawer);
  const closeEdgeDrawer = useDebuggerStore((s) => s.closeEdgeDrawer);
  const setEdgeDisplayMode = useDebuggerStore((s) => s.setEdgeDisplayMode);
  const setTruthMode = useDebuggerStore((s) => s.setTruthMode);

  // Legend visibility state (for PRODUCT mode floating button)
  const [showLegendPopover, setShowLegendPopover] = useState(false);

  // Event handlers
  const handleNodeClick = useCallback(
    (record: MemoryRecord) => {
      selectRecord(record.id);
    },
    [selectRecord]
  );

  const handleEdgeClick = useCallback(
    (edge: CausalEdge) => {
      selectEdge(edge.id);
      openEdgeDrawer();
    },
    [selectEdge, openEdgeDrawer]
  );

  const handleEdgeDrawerClose = useCallback(() => {
    closeEdgeDrawer();
  }, [closeEdgeDrawer]);

  const { edgeDisplayMode, truthMode, selectedEdgeId } = causalGraphState;
  const isResearchMode = truthMode === TruthMode.RESEARCH;
  const records = useMemo(() => collectGraphRecords(events), [events]);
  const { visible, hidden } = useMemo(
    () => projectCausalEdges(records, {
      additionalEdges: inferredEdges, edgeStatuses, edgeDisplayMode, truthMode, showProxyEdges: isResearchMode,
    }),
    [records, inferredEdges, edgeStatuses, edgeDisplayMode, truthMode, isResearchMode]
  );
  const edgeCounts = { [EdgeType.MEASURED]: 0, [EdgeType.INFERRED]: 0, [EdgeType.PROXY]: 0 };
  for (const edge of visible) edgeCounts[edge.edgeType] += 1;
  const visibleEdgeTypes = [EdgeType.MEASURED, EdgeType.INFERRED, EdgeType.PROXY]
    .filter(type => type === EdgeType.MEASURED || edgeCounts[type] > 0);
  const selectedEdgeStatus = visible.find(edge => edge.id === selectedEdgeId)?.status ?? null;
  const nodeCount = records.size;

  useEffect(() => {
    if (causalGraphState.edgeDrawerOpen && !selectedEdgeStatus) closeEdgeDrawer();
  }, [causalGraphState.edgeDrawerOpen, selectedEdgeStatus, closeEdgeDrawer]);

  return (
    <div className="flex flex-col h-full gap-4">
      {/* Main graph area */}
      <div className="flex-1 flex gap-4 min-h-0">
        {/* Graph panel */}
        <div className="flex-1 flex flex-col bg-[var(--color-bg-secondary)] rounded-lg overflow-hidden">
          {/* Header with controls */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-accent)]">
            <div className="flex items-center gap-4">
              <span className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                Relationship graph
              </span>
              <span className="text-xs text-[var(--color-text-dim)]">
                {nodeCount} nodes
              </span>
              {/* Focus mode toggle */}
              <button
                onClick={toggleFocusMode}
                className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                  focusMode.enabled
                    ? 'bg-[var(--color-primary)] text-white'
                    : 'bg-[var(--color-accent)] text-[var(--color-text)]'
                }`}
                title={focusMode.enabled ? 'Exit focus mode' : 'Focus on selected node'}
              >
                Focus {focusMode.enabled ? `(${focusMode.hops} hop)` : ''}
              </button>
              {focusMode.enabled && (
                <select
                  value={focusMode.hops}
                  onChange={(e) => setFocusMode({ hops: Number(e.target.value) })}
                  className="px-2 py-1 rounded text-xs bg-[var(--color-accent)] text-[var(--color-text)] border-none"
                >
                  <option value={1}>1 hop</option>
                  <option value={2}>2 hops</option>
                  <option value={3}>3 hops</option>
                </select>
              )}
            </div>
            <div className="flex items-center gap-4">
              {/* Edge display control */}
              <EdgeDisplayControl
                mode={causalGraphState.edgeDisplayMode}
                onModeChange={setEdgeDisplayMode}
                inferredEdgeCount={edgeCounts[EdgeType.INFERRED]}
                isVerifying={causalGraphState.isVerifying}
                verificationQueue={verificationQueue}
              />
            </div>
          </div>

          {/* Large graph warning */}
          {nodeCount > LARGE_GRAPH_THRESHOLD && (
            <div
              className="px-4 py-2 border-b border-[var(--color-accent)]"
              style={{
                background: nodeCount > VERY_LARGE_GRAPH_THRESHOLD
                  ? 'var(--color-error, #ef4444)22'
                  : 'var(--color-warning, #f59e0b)22',
                color: nodeCount > VERY_LARGE_GRAPH_THRESHOLD
                  ? 'var(--color-error, #ef4444)'
                  : 'var(--color-warning, #f59e0b)',
              }}
            >
              <span className="text-xs font-medium">
                {nodeCount > VERY_LARGE_GRAPH_THRESHOLD
                  ? `Large graph (${nodeCount} nodes) - consider filtering or using Focus mode`
                  : `${nodeCount} nodes - use Focus mode for better performance`}
              </span>
            </div>
          )}

          {/* Legend - always visible in RESEARCH mode, floating button in PRODUCT mode */}
          {isResearchMode ? (
            <div className="px-4 py-2 border-b border-[var(--color-accent)]">
              <EdgeLegend
                visibleTypes={visibleEdgeTypes}
                counts={edgeCounts}
                layout="horizontal"
              />
            </div>
          ) : (
            <div className="px-4 py-2 border-b border-[var(--color-accent)] relative">
              <button
                onClick={() => setShowLegendPopover(!showLegendPopover)}
                className="px-3 py-1 rounded text-xs font-medium bg-[var(--color-accent)] text-[var(--color-text)] hover:bg-[var(--color-primary)] transition-colors"
              >
                {showLegendPopover ? 'Hide Legend' : 'Show Legend'}
              </button>
              {showLegendPopover && (
                <div
                  className="absolute left-4 top-full mt-1 z-10 shadow-lg rounded"
                  style={{ background: 'var(--color-bg-secondary)' }}
                >
                  <EdgeLegend
                    visibleTypes={visibleEdgeTypes}
                    counts={edgeCounts}
                    layout="vertical"
                  />
                </div>
              )}
            </div>
          )}

          {nodeCount > 0 && visible.length === 0 && (
            <p className="px-4 text-xs text-[var(--color-text-muted)]">
              No edges match this view's evidence filters.
            </p>
          )}

          {/* Graph */}
          <div className="flex-1 min-h-0">
            <CausalGraph
              events={events}
              selectedRecordId={selectedRecordId}
              selectedEdgeId={causalGraphState.selectedEdgeId}
              onNodeClick={handleNodeClick}
              onEdgeClick={handleEdgeClick}
              edgeDisplayMode={edgeDisplayMode}
              truthMode={truthMode}
              showProxyEdges={isResearchMode}
              additionalEdges={inferredEdges}
              edgeStatuses={edgeStatuses}
              showMinimap
              showControls
            />
          </div>
        </div>

        {/* Right sidebar: Truth mode + Violations */}
        <div className="w-80 flex flex-col gap-4 flex-shrink-0">
          {/* Truth mode switch */}
          <TruthModeSwitch
            mode={causalGraphState.truthMode}
            onModeChange={setTruthMode}
            inferredEdgeCount={hidden[EdgeType.INFERRED]}
            proxyEdgeCount={hidden[EdgeType.PROXY]}
          />

          {/* Violations panel */}
          <div className="flex-1 min-h-0">
            <ViolationsPanel
              report={transitivityReport}
              onViolationSelect={(v) => {
                // Optionally highlight the violation in the graph
                console.log('Selected violation:', v.id);
              }}
            />
          </div>
        </div>
      </div>

      {/* Bottom HUD: Compute ledger */}
      <ComputeLedger
        ledger={computeLedger}
        compact
        style={{ flexShrink: 0 }}
      />

      {/* Edge detail drawer */}
      <EdgeDrawer
        edge={selectedEdgeStatus}
        isOpen={causalGraphState.edgeDrawerOpen}
        onClose={handleEdgeDrawerClose}
      />
    </div>
  );
}

export default CausalGraphPanel;
