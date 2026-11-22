import React from 'react';
import { createRoot } from 'react-dom/client';
import { DebuggerEventType, type DebuggerEvent, type MemoryRecord } from '@rtepl/reckon-components';
import { EventInspector } from '../src/features/event-inspector/EventInspector';
import { useDebuggerStore } from '../src/store';
import '../src/styles/globals.css';

type ScoreCase = { id: string; score?: MemoryRecord['causalScore'] };
declare global {
  interface Window {
    showScoreCases: (cases: ScoreCase[], selected: string | null) => void;
  }
}

window.showScoreCases = (cases, selected) => {
  const records = cases.map(sample => ({
    id: sample.id, timestamp: 0, episodeId: 'scores', causalScore: sample.score,
  } as MemoryRecord));
  const event: DebuggerEvent = {
    eventId: '0', eventType: DebuggerEventType.STEP, wallTimeMs: 0,
    episodeId: 'scores', step: 0, sequence: 0, snapshot: records,
    memoryEvents: [], exceededDimension: '',
  };
  useDebuggerStore.setState({
    events: [event], eventsMap: new Map([['0', event]]),
    recordsMap: new Map(records.map(record => [record.id, record])),
    selectedEventId: '0', selectedRecordId: selected,
  });
};

createRoot(document.getElementById('root')!).render(<EventInspector />);
window.showScoreCases([], null);
