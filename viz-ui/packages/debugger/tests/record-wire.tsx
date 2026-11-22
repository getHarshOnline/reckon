import React from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRecord as WireRecord } from '../../../generated/reckon/record';
import { laboratoryRecord, laboratoryWireRecord } from '../src/hooks/laboratoryRecord';
import type { LaboratoryRecord } from '@rtepl/reckon-components';
import { EventInspector } from '../src/features/event-inspector/EventInspector';
import { useDebuggerStore } from '../src/store';
import '../src/styles/globals.css';

declare global {
  interface Window {
    inspectNativeRecord: (bytes: number[]) => {
      encoded: number[]; record?: ReturnType<typeof laboratoryRecord>; error?: string;
    };
    checkNativeIntegerLimits: (bytes: number[]) => { field: string; error: string }[];
    inspectPublicRecord: (record: LaboratoryRecord) => ReturnType<typeof laboratoryRecord>;
  }
}

window.inspectNativeRecord = (bytes: number[]) => {
  const wire = WireRecord.fromBinary(new Uint8Array(bytes));
  const encoded = Array.from(WireRecord.toBinary(wire));
  try {
    const record = laboratoryWireRecord(wire);
    useDebuggerStore.setState({
      recordsMap: new Map([[record.id, record]]), selectedRecordId: record.id,
    });
    return { encoded, record };
  } catch (error) {
    return { encoded, error: String(error) };
  }
};

window.checkNativeIntegerLimits = (bytes: number[]) => {
  const unsafe = '9007199254740993';
  const fields: [string, (record: WireRecord) => void][] = [
    ['timestamp', record => { record.timestamp = unsafe; }],
    ['cost.bytes', record => { record.cost!.bytes = unsafe; }],
    ['cost.tokens', record => { record.cost!.tokens = unsafe; }],
    ['utility.lastUsed', record => { record.utility!.lastUsed = unsafe; }],
    ['causalScore.lastEvaluated', record => { record.causalScore!.lastEvaluated = unsafe; }],
    ['createdAtStep', record => { record.createdAtStep = unsafe; }],
    ['createdAtSequence', record => { record.createdAtSequence = unsafe; }],
  ];
  return fields.map(([field, change]) => {
    const record = WireRecord.fromBinary(new Uint8Array(bytes));
    change(record);
    try {
      laboratoryWireRecord(record);
      return { field, error: '' };
    } catch (error) {
      return { field, error: String(error) };
    }
  });
};

window.inspectPublicRecord = (value) => {
  const record = laboratoryRecord(value);
  useDebuggerStore.setState({
    recordsMap: new Map([[record.id, record]]), selectedRecordId: record.id,
  });
  return record;
};

createRoot(document.getElementById('root')!).render(<EventInspector />);
