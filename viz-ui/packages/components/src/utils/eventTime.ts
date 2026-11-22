import type { DebuggerEvent } from '../types';

/** Use the event's declared clock for placement; kernel steps are not dates. */
export function timelineCoordinate(event: DebuggerEvent): number {
  return event.timeBasis === 'step' ? event.step : event.wallTimeMs;
}
