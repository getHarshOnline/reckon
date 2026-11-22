import {
  DebuggerEventType,
  MemoryOpType,
  PayloadType,
  formatBytes,
  formatDuration,
  recordScoreSource,
  proxyOnlyRecordIds,
  type DebuggerEvent,
  type MemoryRecord,
  type MemoryEvent,
} from '@rtepl/reckon-components';
import { useDebuggerStore, selectSelectedEvent, selectSelectedRecord } from '@/store';

/**
 * Format event type for display
 */
function formatEventType(type: DebuggerEventType): string {
  const labels: Record<DebuggerEventType, string> = {
    [DebuggerEventType.UNSPECIFIED]: 'Unknown',
    [DebuggerEventType.EPISODE_START]: 'Episode Start',
    [DebuggerEventType.EPISODE_END]: 'Episode End',
    [DebuggerEventType.STEP]: 'Step',
    [DebuggerEventType.POLICY_CHANGE]: 'Policy Change',
    [DebuggerEventType.BUDGET_EXCEEDED]: 'Budget Exceeded',
    [DebuggerEventType.CAUSAL_UPDATE]: 'Causal Update',
    [DebuggerEventType.CHECKPOINT]: 'Checkpoint',
  };
  return labels[type] ?? 'Unknown';
}

/**
 * Format memory operation type
 */
function formatOpType(type: MemoryOpType): string {
  const labels: Record<MemoryOpType, string> = {
    [MemoryOpType.UNSPECIFIED]: 'Unknown',
    [MemoryOpType.WRITE]: 'Write',
    [MemoryOpType.READ]: 'Read',
    [MemoryOpType.PRUNE]: 'Prune',
    [MemoryOpType.UPDATE_SCORE]: 'Update Score',
    [MemoryOpType.COMPRESS]: 'Compress',
    [MemoryOpType.BUDGET_CHECK]: 'Budget Check',
  };
  return labels[type] ?? 'Unknown';
}

/**
 * Format payload type
 */
function formatPayloadType(type: PayloadType): string {
  const labels: Record<PayloadType, string> = {
    [PayloadType.UNSPECIFIED]: 'Unknown',
    [PayloadType.OBSERVATION]: 'Observation',
    [PayloadType.ACTION]: 'Action',
    [PayloadType.REWARD]: 'Reward',
    [PayloadType.CUE]: 'Cue',
    [PayloadType.TRACE]: 'Trace',
    [PayloadType.REPRESENTATION]: 'Representation',
    [PayloadType.CUSTOM]: 'Custom',
  };
  return labels[type] ?? 'Unknown';
}

/**
 * Event details section
 */
function EventDetails({ event }: { event: DebuggerEvent }) {
  const proxyCount = proxyOnlyRecordIds(event.snapshot).length;
  const scoreCount = event.snapshot.filter(record => record.causalScore != null).length;
  const proxySummary = !event.snapshot.length
    ? 'Not recorded'
    : scoreCount < event.snapshot.length
      ? `Not fully recorded (${proxyCount} proxy-only identified)`
      : String(proxyCount);
  return (
    <div className="space-y-3 text-sm">
      <InfoRow label="Event ID" value={event.eventId} />
      <InfoRow label="Type" value={formatEventType(event.eventType)} />
      <InfoRow label="Step" value={event.step.toString()} />
      <InfoRow label="Sequence" value={event.sequence?.toString() ?? "Not recorded"} />
      <InfoRow label="Episode" value={event.episodeId || 'N/A'} />
      <InfoRow
        label="Proxy-only records in snapshot"
        value={proxySummary}
      />
      <InfoRow
        label="Time"
        value={event.timeBasis === 'step' ? 'Not recorded (logical steps)' : new Date(event.wallTimeMs).toLocaleTimeString()}
      />

      {event.kernelEvent && (
        <details>
          <summary>Source operation</summary>
          <pre className="overflow-auto text-xs">{JSON.stringify(event.kernelEvent, null, 2)}</pre>
        </details>
      )}

      {event.finalUsage && (
        <div className="pt-2 border-t border-[var(--color-accent)]">
          <span className="text-xs text-[var(--color-text-dim)] uppercase">
            Resource Usage
          </span>
          <div className="mt-2 space-y-1">
            <InfoRow label="Slots" value={event.finalUsage.slotCount.toString()} />
            <InfoRow label="Bytes" value={formatBytes(event.finalUsage.byteCount)} />
            <InfoRow label="Tokens" value={event.finalUsage.tokenCount.toString()} />
          </div>
        </div>
      )}

      {event.memoryEvents && event.memoryEvents.length > 0 && (
        <div className="pt-2 border-t border-[var(--color-accent)]">
          <span className="text-xs text-[var(--color-text-dim)] uppercase">
            Memory Operations ({event.memoryEvents.length})
          </span>
          <div className="mt-2 space-y-2 max-h-48 overflow-y-auto">
            {event.memoryEvents.slice(0, 20).map((me) => (
              <MemoryEventItem key={me.eventId} memoryEvent={me} />
            ))}
            {event.memoryEvents.length > 20 && (
              <p className="text-xs text-[var(--color-text-dim)]">
                +{event.memoryEvents.length - 20} more...
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Memory event item
 */
function MemoryEventItem({ memoryEvent }: { memoryEvent: MemoryEvent }) {
  return (
    <div className="p-2 bg-[var(--color-bg-tertiary)] rounded text-xs">
      <div className="flex items-center justify-between">
        <span className="font-medium">{formatOpType(memoryEvent.opType)}</span>
        <span className="text-[var(--color-text-dim)]">
          {formatDuration(memoryEvent.durationUs / 1000)}
        </span>
      </div>
      {memoryEvent.resultIds.length > 0 && <InfoRow label="Retrieved records" value={memoryEvent.resultIds.join(', ')} />}
      {memoryEvent.pruneReason && <InfoRow label="Removal reason" value={memoryEvent.pruneReason} />}
      {memoryEvent.oldScore !== undefined && <InfoRow label="Previous score" value={String(memoryEvent.oldScore)} />}
      {memoryEvent.newScore !== undefined && <InfoRow label="New score" value={String(memoryEvent.newScore)} />}
      {memoryEvent.recordId && (
        <p className="mt-1 text-[var(--color-text-muted)] truncate">
          {memoryEvent.recordId}
        </p>
      )}
    </div>
  );
}

/**
 * Record details section
 */
function RecordDetails({ record }: { record: MemoryRecord }) {
  // Safely extract nested fields with defaults
  const costTokens = record.cost?.tokens;
  const costBytes = record.cost?.bytes ?? 0;
  const costSlots = record.cost?.slots ?? 0;
  const utilityValue = record.utility?.value ?? 0;
  const utilityUncertainty = record.utility?.uncertainty ?? 0;
  const utilityUseCount = record.utility?.useCount ?? 0;
  const tags = record.tags ?? [];

  return (
    <div className="space-y-3 text-sm">
      <InfoRow label="Record ID" value={record.id ?? 'N/A'} />
      <InfoRow label="Type" value={formatPayloadType(record.payloadType ?? PayloadType.UNSPECIFIED)} />
      <InfoRow label="Episode" value={record.episodeId ?? 'N/A'} />
      <InfoRow label="Attribution source" value={recordScoreSource(record.causalScore)} />
      <InfoRow
        label="Timestamp"
        value={record.timestamp != null ? String(record.timestamp) : 'N/A'}
      />

      <div className="pt-2 border-t border-[var(--color-accent)]">
        <span className="text-xs text-[var(--color-text-dim)] uppercase">Cost</span>
        <div className="mt-2 space-y-1">
          <InfoRow label="Bytes" value={formatBytes(costBytes)} />
          <InfoRow label="Tokens" value={costTokens == null ? 'Not recorded' : String(costTokens)} />
          <InfoRow label="Slots" value={String(costSlots)} />
        </div>
      </div>

      <div className="pt-2 border-t border-[var(--color-accent)]">
        <span className="text-xs text-[var(--color-text-dim)] uppercase">Utility</span>
        <div className="mt-2 space-y-1">
          <InfoRow label="Value" value={Number(utilityValue).toFixed(4)} />
          <InfoRow label="Uncertainty" value={Number(utilityUncertainty).toFixed(4)} />
          <InfoRow label="Use Count" value={String(utilityUseCount)} />
        </div>
      </div>

      {record.causalScore && (
        <div className="pt-2 border-t border-[var(--color-accent)]">
          <span className="text-xs text-[var(--color-text-dim)] uppercase">
            Record attribution
          </span>
          <div className="mt-2 space-y-1">
            {record.causalScore.ablationDelta != null && (
              <InfoRow
                label="Ablation Delta"
                value={Number(record.causalScore.ablationDelta).toFixed(4)}
              />
            )}
            {record.causalScore.counterfactualDelta != null && (
              <InfoRow
                label="Counterfactual Delta"
                value={Number(record.causalScore.counterfactualDelta).toFixed(4)}
              />
            )}
            {record.causalScore.influenceProxy != null && (
              <InfoRow
                label="Influence (proxy)"
                value={Number(record.causalScore.influenceProxy).toFixed(4)}
              />
            )}
          </div>
        </div>
      )}

      {tags.length > 0 && (
        <div className="pt-2 border-t border-[var(--color-accent)]">
          <span className="text-xs text-[var(--color-text-dim)] uppercase">Tags</span>
          <div className="mt-2 flex flex-wrap gap-1">
            {tags.map((tag, index) => (
              <span
                key={index}
                className="px-2 py-0.5 bg-[var(--color-accent)] rounded text-xs"
              >
                {tag}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Info row component
 */
function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-2 gap-2">
      <span className="text-[var(--color-text-muted)]">{label}</span>
      <span className="font-mono text-right min-w-0" style={{ overflowWrap: 'anywhere' }}>{value}</span>
    </div>
  );
}

/**
 * Event Inspector sidebar panel.
 *
 * Shows details for selected event and record.
 */
export function EventInspector() {
  const selectedEvent = useDebuggerStore(selectSelectedEvent);
  const selectedRecord = useDebuggerStore(selectSelectedRecord);

  return (
    <div className="h-full bg-[var(--color-bg-secondary)] rounded-lg overflow-hidden">
      <div className="px-4 py-3 border-b border-[var(--color-accent)]">
        <span className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Inspector
        </span>
      </div>

      <div className="p-4 overflow-y-auto h-[calc(100%-48px)]">
        {selectedEvent || selectedRecord ? (
          <div className="space-y-6">
            {/* Event section */}
            {selectedEvent && (
              <div>
                <h3 className="text-xs font-semibold uppercase text-[var(--color-text-dim)] mb-3">
                  Selected Event
                </h3>
                <EventDetails event={selectedEvent} />
              </div>
            )}

            {/* Record section */}
            {selectedRecord && (
              <div className={selectedEvent ? "pt-4 border-t border-[var(--color-accent)]" : ""}>
                <h3 className="text-xs font-semibold uppercase text-[var(--color-text-dim)] mb-3">
                  Selected Record
                </h3>
                <RecordDetails record={selectedRecord} />
              </div>
            )}
          </div>
        ) : (
          <p className="text-sm text-[var(--color-text-muted)]">
            Select an event or record to view details
          </p>
        )}
      </div>
    </div>
  );
}

export default EventInspector;
