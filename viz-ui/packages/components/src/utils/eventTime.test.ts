import { expect, it } from 'vitest';
import { timelineCoordinate } from './eventTime';
import { compareCanonical } from './canonicalOrder';
import type { DebuggerEvent } from '../types';

it('keeps the logical clock separate from recorded wall time', () => {
  const event: DebuggerEvent = { eventId: '0', eventType: 3, episodeId: 'test',
    step: 12, sequence: 0, wallTimeMs: 0, timeBasis: 'step', memoryEvents: [],
    exceededDimension: '', snapshot: [] };
  expect(timelineCoordinate(event)).toBe(12);
  expect(timelineCoordinate({ ...event, timeBasis: 'wall', wallTimeMs: 300 })).toBe(300);
});

it('orders tied native keys without dropping zero or rounding large IDs', () => {
  const events = ['18446744073709551615', '10', '0', '2'].map(eventId => ({
    eventId, episodeId: 'test', step: 0, sequence: 0, wallTimeMs: 0,
  }));
  expect(events.sort(compareCanonical).map(event => event.eventId)).toEqual([
    '0', '2', '10', '18446744073709551615',
  ]);
});
