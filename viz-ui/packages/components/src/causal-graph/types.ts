import type { DebuggerEvent, MemoryRecord, CausalNode, CausalEdge, EdgeStatus, TruthMode } from '../types';
import { EdgeDisplayMode } from '../types';

/**
 * CausalGraph component props
 */
export interface CausalGraphProps {
  /** Array of debugger events containing memory records */
  events: DebuggerEvent[];

  /** Callback when a node (record) is clicked */
  onNodeClick?: (record: MemoryRecord) => void;

  /** Callback when a node is hovered */
  onNodeHover?: (record: MemoryRecord | null) => void;

  /** Callback when an edge is clicked */
  onEdgeClick?: (edge: CausalEdge) => void;

  /** Currently selected record ID */
  selectedRecordId?: string | null;

  /** Currently selected edge ID */
  selectedEdgeId?: string | null;

  /** Layout algorithm to use */
  layout?: 'dagre' | 'force' | 'hierarchical';

  /** Show minimap navigation */
  showMinimap?: boolean;

  /** Show controls (zoom, fit) */
  showControls?: boolean;

  /** Enable node dragging */
  draggable?: boolean;

  /** Show proxy edges (default: false, only measured shown) */
  showProxyEdges?: boolean;

  /** Show caller-supplied inferred edges */
  showInferredEdges?: boolean;

  /** Choose which supplied edges to display */
  edgeDisplayMode?: EdgeDisplayMode;

  /** Restrict product mode to direct probe evidence */
  truthMode?: TruthMode;

  /** Additional edges to display (e.g., inferred edges computed externally) */
  additionalEdges?: CausalEdge[];

  /** Edge status information for detailed rendering */
  edgeStatuses?: Map<string, EdgeStatus>;

  /** Custom class name */
  className?: string;

  /** Custom inline styles */
  style?: React.CSSProperties;
}

/**
 * Extract nodes and edges from events
 */
export interface GraphData {
  nodes: CausalNode[];
  edges: CausalEdge[];
}
