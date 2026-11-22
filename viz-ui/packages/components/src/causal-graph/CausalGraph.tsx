import { useMemo, useCallback, useEffect } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import type { CausalGraphProps } from './types';
import { collectGraphRecords, projectCausalEdges } from './edgeProjection';
import type { MemoryRecord, CausalNode, CausalEdge } from '../types';
import { PayloadType, PAYLOAD_TYPE_COLORS, EdgeType } from '../types';
import { sortedCanonical } from '../utils/canonicalOrder';

function createGraphNodes(records: Iterable<MemoryRecord>): CausalNode[] {
  const uniqueRecords = Array.from(records);

  // Create nodes with canonical ordering fields
  return uniqueRecords.map((record, index) => {
    // Extract createdAtStep/createdAtSequence from record if available
    // These are creation-time snapshots, not authoritative identity
    const step = record.createdAtStep;
    const sequence = record.createdAtSequence ?? index;

    // Build node, conditionally including optional fields
    const node: CausalNode = {
      id: record.id,
      label: formatRecordLabel(record),
      type: record.payloadType,
      utility: record.utility?.value ?? 0,
      timestamp: record.timestamp,
      episodeId: record.episodeId,
    };

    // Only set optional fields if they have values (exactOptionalPropertyTypes)
    if (step !== undefined) {
      node.step = step;
    }
    node.sequence = sequence;

    return node;
  });
}

/**
 * Format record as a short label
 */
function formatRecordLabel(record: MemoryRecord): string {
  const typeNames: Record<PayloadType, string> = {
    [PayloadType.UNSPECIFIED]: '?',
    [PayloadType.OBSERVATION]: 'Obs',
    [PayloadType.ACTION]: 'Act',
    [PayloadType.REWARD]: 'Rew',
    [PayloadType.CUE]: 'Cue',
    [PayloadType.TRACE]: 'Trc',
    [PayloadType.REPRESENTATION]: 'Rep',
    [PayloadType.CUSTOM]: 'Cst',
  };
  const typeName = typeNames[record.payloadType] ?? '?';
  const shortId = record.id.slice(0, 6);
  return `${typeName}\n${shortId}`;
}

/**
 * Simple layout algorithm - positions nodes in a grid with canonical ordering.
 * Uses (episodeId, step, sequence) when available, falls back to timestamp.
 */
function layoutNodes(nodes: CausalNode[], width: number): Node[] {
  // Sort by canonical ordering: (episodeId, step, sequence) or timestamp fallback
  const sorted = sortedCanonical(nodes);

  // Grid layout
  const columns = Math.ceil(Math.sqrt(sorted.length));
  const spacing = Math.max(150, width / (columns + 1));

  return sorted.map((node, index): Node => {
    const col = index % columns;
    const row = Math.floor(index / columns);

    return {
      id: node.id,
      type: 'default',
      position: {
        x: col * spacing + spacing / 2,
        y: row * spacing + spacing / 2,
      },
      data: {
        label: node.label,
      },
      style: {
        background: PAYLOAD_TYPE_COLORS[node.type] ?? PAYLOAD_TYPE_COLORS[PayloadType.UNSPECIFIED],
        color: '#ffffff',
        border: 'none',
        borderRadius: 8,
        padding: 10,
        fontSize: 12,
        fontFamily: 'system-ui, sans-serif',
        textAlign: 'center' as const,
        whiteSpace: 'pre-wrap' as const,
        minWidth: 80,
      },
    };
  });
}

/**
 * Get edge color based on type
 */
function getEdgeColor(edgeType: EdgeType): string {
  switch (edgeType) {
    case EdgeType.MEASURED:
      return 'var(--graph-measured-edge-color, #10b981)';
    case EdgeType.INFERRED:
      return 'var(--graph-inferred-edge-color, #f59e0b)';
    case EdgeType.PROXY:
      return 'var(--graph-proxy-edge-color, #3b82f6)';
    default:
      return 'var(--graph-edge-color, #64748b)';
  }
}

/**
 * Get edge dash pattern based on type
 */
function getEdgeDashPattern(edgeType: EdgeType): string | undefined {
  switch (edgeType) {
    case EdgeType.MEASURED:
      return undefined; // solid
    case EdgeType.INFERRED:
      return '8,4'; // dashed
    case EdgeType.PROXY:
      return '3,3'; // dotted
    default:
      return undefined;
  }
}

/**
 * Convert causal edges to React Flow edges
 */
function createFlowEdges(edges: CausalEdge[], selectedEdgeId?: string | null): Edge[] {
  return edges.map((edge) => {
    const color = getEdgeColor(edge.edgeType);
    const isSelected = edge.id === selectedEdgeId;

    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      animated: edge.edgeType === EdgeType.MEASURED,
      style: {
        stroke: color,
        strokeWidth: isSelected ? 4 : (edge.weight ? Math.min(4, 1 + edge.weight * 3) : 2),
        strokeDasharray: getEdgeDashPattern(edge.edgeType),
        cursor: 'pointer',
        filter: isSelected ? 'drop-shadow(0 0 4px rgba(255,255,255,0.5))' : undefined,
      },
      markerEnd: {
        type: 'arrowclosed' as const,
        color,
      },
      data: {
        edgeType: edge.edgeType,
        weight: edge.weight,
      },
    };
  });
}

/**
 * Causal Graph Component
 *
 * Visualizes causal relationships between memory records as a directed graph.
 * Uses React Flow for interactive node-based visualization.
 *
 * Features:
 * - Nodes represent memory records
 * - Edges represent causal dependencies (from provenance.inputIds)
 * - Node color indicates payload type
 * - Edge thickness indicates causal influence strength
 *
 * @example
 * ```tsx
 * <CausalGraph
 *   events={debuggerEvents}
 *   onNodeClick={(record) => console.log('Selected:', record)}
 * />
 * ```
 */
export function CausalGraph({
  events,
  onNodeClick,
  onNodeHover,
  onEdgeClick,
  selectedRecordId,
  selectedEdgeId,
  layout: _layout = 'hierarchical',
  showMinimap = true,
  showControls = true,
  draggable = true,
  showProxyEdges = false,
  showInferredEdges = false,
  edgeDisplayMode,
  additionalEdges,
  truthMode,
  edgeStatuses,
  className,
  style,
}: CausalGraphProps) {
  // TODO: Use _layout to switch between layout algorithms
  void _layout;
  const recordMap = useMemo(() => collectGraphRecords(events), [events]);
  const graphNodes = useMemo(() => createGraphNodes(recordMap.values()), [recordMap]);
  const { visible: filteredEdges } = useMemo(
    () => projectCausalEdges(recordMap, {
      additionalEdges, edgeStatuses, edgeDisplayMode, truthMode, showProxyEdges, showInferredEdges,
    }),
    [recordMap, additionalEdges, edgeStatuses, edgeDisplayMode, truthMode, showProxyEdges, showInferredEdges]
  );

  const initialNodes = useMemo(() => layoutNodes(graphNodes, 800), [graphNodes]);
  const initialEdges = useMemo(
    () => createFlowEdges(filteredEdges, selectedEdgeId),
    [filteredEdges, selectedEdgeId]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Update edges when selection changes
  useEffect(() => {
    setEdges(createFlowEdges(filteredEdges, selectedEdgeId));
  }, [filteredEdges, selectedEdgeId, setEdges]);

  // Handle node click
  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      const record = recordMap.get(node.id);
      if (record && onNodeClick) {
        onNodeClick(record);
      }
    },
    [recordMap, onNodeClick]
  );

  // Handle node hover
  const handleNodeMouseEnter = useCallback(
    (_: React.MouseEvent, node: Node) => {
      const record = recordMap.get(node.id);
      if (record && onNodeHover) {
        onNodeHover(record);
      }
    },
    [recordMap, onNodeHover]
  );

  const handleNodeMouseLeave = useCallback(() => {
    onNodeHover?.(null);
  }, [onNodeHover]);

  // Handle edge click
  const handleEdgeClick = useCallback(
    (_: React.MouseEvent, edge: Edge) => {
      // Find the original CausalEdge
      const causalEdge = filteredEdges.find((e) => e.id === edge.id);
      if (causalEdge && onEdgeClick) {
        onEdgeClick(causalEdge);
      }
    },
    [filteredEdges, onEdgeClick]
  );

  useEffect(() => {
    setNodes(previous => {
      const byId = new Map(previous.map(node => [node.id, node]));
      return initialNodes.map(node => ({
        ...node,
        position: byId.get(node.id)?.position ?? node.position,
        style: {
          ...node.style,
          boxShadow: node.id === selectedRecordId
            ? '0 0 0 3px #ffffff, 0 0 20px rgba(255,255,255,0.4)'
            : undefined,
        },
      }));
    });
  }, [initialNodes, selectedRecordId, setNodes]);

  if (graphNodes.length === 0) {
    return (
      <div
        className={className}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '100%',
          height: '100%',
          color: 'var(--graph-text-muted, #a0a0a0)',
          fontFamily: 'system-ui, sans-serif',
          fontSize: 14,
          ...style,
        }}
      >
        No records to display. Connect to a running Reckon session.
      </div>
    );
  }

  return (
    <div
      className={className}
      style={{
        width: '100%',
        height: '100%',
        ...style,
      }}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        onNodeMouseEnter={handleNodeMouseEnter}
        onNodeMouseLeave={handleNodeMouseLeave}
        onEdgeClick={handleEdgeClick}
        nodesDraggable={draggable}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background
          color="var(--graph-grid-color, #374151)"
          gap={20}
        />
        {showControls && <Controls />}
        {showMinimap && (
          <MiniMap
            style={{
              background: 'var(--graph-minimap-bg, #1f2937)',
            }}
            nodeColor={(node) =>
              (node.style?.background as string) ?? '#666'
            }
          />
        )}
      </ReactFlow>
    </div>
  );
}

export default CausalGraph;
