import { EdgeDisplayMode, EdgeType, TruthMode } from '../types';
import type { CausalEdge, DebuggerEvent, EdgeStatus, MemoryRecord } from '../types';

type EdgeOptions = {
  additionalEdges?: CausalEdge[] | undefined;
  edgeStatuses?: Map<string, EdgeStatus> | undefined;
  edgeDisplayMode?: EdgeDisplayMode | undefined;
  truthMode?: TruthMode | undefined;
  showProxyEdges?: boolean | undefined;
  showInferredEdges?: boolean | undefined;
};

export function collectGraphRecords(events: DebuggerEvent[]): Map<string, MemoryRecord> {
  const records = new Map<string, MemoryRecord>();
  for (const event of events) {
    for (const record of event.snapshot ?? []) records.set(record.id, record);
  }
  return records;
}

function isVisible(type: EdgeType, options: EdgeOptions): boolean {
  if (type === EdgeType.MEASURED) return true;
  if (options.truthMode === TruthMode.PRODUCT) return false;
  if (options.edgeDisplayMode === EdgeDisplayMode.MEASURED_ONLY || options.edgeDisplayMode === EdgeDisplayMode.PROBE_STATUS) {
    return false;
  }
  if (type === EdgeType.PROXY) return options.showProxyEdges === true;
  return options.edgeDisplayMode === EdgeDisplayMode.INCLUDE_UNMEASURED || options.showInferredEdges === true;
}

export function projectCausalEdges(records: Map<string, MemoryRecord>, options: EdgeOptions) {
  const candidates = new Map<string, CausalEdge>();
  for (const record of records.values()) {
    for (const source of record.provenance?.inputIds ?? []) {
      if (!records.has(source)) continue;
      const id = `${source}->${record.id}`;
      candidates.set(id, {
        id, source, target: record.id, edgeType: EdgeType.PROXY,
        weight: record.causalScore?.influenceProxy ?? 0,
      });
    }
  }

  for (const edge of options.additionalEdges ?? []) {
    if (!records.has(edge.source) || !records.has(edge.target)) continue;
    const previous = candidates.get(edge.id);
    if (previous && (previous.source !== edge.source || previous.target !== edge.target)) continue;
    if (!previous || edge.edgeType === EdgeType.INFERRED) candidates.set(edge.id, edge);
  }

  const visible: (CausalEdge & { status: EdgeStatus })[] = [];
  const hidden = { [EdgeType.MEASURED]: 0, [EdgeType.INFERRED]: 0, [EdgeType.PROXY]: 0 };
  for (const edge of candidates.values()) {
    const supplied = options.edgeStatuses?.get(edge.id);
    const status = supplied?.source === edge.source && supplied.target === edge.target
      ? supplied : undefined;
    const probe = status?.edgeType === EdgeType.MEASURED ? status.probeEvidence : undefined;
    if (!probe && edge.edgeType === EdgeType.MEASURED) continue;

    const edgeType = probe ? EdgeType.MEASURED : edge.edgeType;
    const weight = probe ? Math.abs(probe.effectSize) : edge.weight;
    const { source, target } = edge;
    if (isVisible(edgeType, options)) {
      visible.push({
        ...edge,
        ...(weight === undefined ? {} : { weight }),
        edgeType,
        status: status?.edgeType === edgeType ? status : { source, target, edgeType },
      });
    } else {
      hidden[edgeType] += 1;
    }
  }
  return { visible, hidden };
}
