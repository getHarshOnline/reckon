import { useEffect, useRef, useCallback } from 'react';
import { useDebuggerStore } from '@/store';

import type { DebuggerEvent } from '@rtepl/reckon-components';
import type { RunSummary } from '@/store';

/** Flush full batches immediately rather than dropping queued events. */
const MAX_PENDING_EVENTS = 1000;

interface UseWebSocketOptions {
  /** Whether to automatically connect on mount */
  autoConnect?: boolean;
  /** Reconnect delay in milliseconds (0 to disable) */
  reconnectDelay?: number;
  /** Maximum reconnection attempts (0 for unlimited) */
  maxReconnectAttempts?: number;
}

interface UseWebSocketReturn {
  /** Connect to the WebSocket server */
  connect: () => void;
  /** Disconnect from the WebSocket server */
  disconnect: () => void;
  /** Send a message to the server */
  send: (data: unknown) => void;
  /** Subscribe to a specific run */
  subscribeToRun: (runId: string) => void;
}

/**
 * WebSocket hook for real-time event streaming.
 *
 * Supports both legacy /ws/events and new /v1/stream endpoints.
 * The new endpoint provides:
 * - Initial snapshot with RunSummary + all existing events
 * - Live event streaming as events are appended
 *
 * Integrates with the Zustand store for state management:
 * - Connection status is stored in the global store
 * - Incoming events are automatically added to the store
 * - Handles reconnection with exponential backoff
 *
 * @example
 * ```tsx
 * const { connect, disconnect, send, subscribeToRun } = useWebSocket({
 *   autoConnect: true,
 *   reconnectDelay: 3000,
 * });
 *
 * // Subscribe to a specific run
 * subscribeToRun('fixture_001');
 *
 * // Connection status from store
 * const status = useDebuggerStore((s) => s.connectionStatus);
 * ```
 */
export function useWebSocket({
  autoConnect = false,
  reconnectDelay = 3000,
  maxReconnectAttempts = 10,
}: UseWebSocketOptions = {}): UseWebSocketReturn {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptsRef = useRef(0);

  // RAF batching refs
  const pendingEventsRef = useRef<DebuggerEvent[]>([]);
  const rafIdRef = useRef<number | null>(null);

  // Store state and actions
  const setConnectionStatus = useDebuggerStore((s) => s.setConnectionStatus);
  const addEvents = useDebuggerStore((s) => s.addEvents);
  const setCurrentRunSummary = useDebuggerStore((s) => s.setCurrentRunSummary);

  // Clear reconnect timeout
  const clearReconnectTimeout = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  }, []);

  // Cancel pending RAF
  const cancelPendingRaf = useCallback(() => {
    if (rafIdRef.current !== null) {
      cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }
  }, []);

  // Flush pending events to store (called by RAF)
  const flushPendingEvents = useCallback(() => {
    rafIdRef.current = null;
    if (pendingEventsRef.current.length > 0) {
      addEvents(pendingEventsRef.current);
      pendingEventsRef.current = [];
    }
  }, [addEvents]);

  // Schedule RAF flush if not already scheduled
  const scheduleFlush = useCallback(() => {
    if (rafIdRef.current === null) {
      rafIdRef.current = requestAnimationFrame(flushPendingEvents);
    }
  }, [flushPendingEvents]);

  // Process events from WebSocket message
  const processEvents = useCallback((events: DebuggerEvent[]) => {
    // Skip RAF processing when document is hidden (background tab)
    if (document.hidden) {
      // Process directly without animation frame
      addEvents(events);
      return;
    }

    // Collect events in pending array (RAF batching)
    pendingEventsRef.current.push(...events);

    if (pendingEventsRef.current.length >= MAX_PENDING_EVENTS) {
      addEvents(pendingEventsRef.current);
      pendingEventsRef.current = [];
    }

    // Schedule flush before next paint
    scheduleFlush();
  }, [addEvents, scheduleFlush]);

  // Handle incoming WebSocket messages
  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const message = JSON.parse(event.data);

      // Handle ping/pong keep-alive
      if (message.type === 'ping') {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: 'pong' }));
        }
        return;
      }

      // Handle subscription confirmations
      if (message.type === 'subscribed' || message.type === 'unsubscribed') {
        return;
      }

      // Handle errors
      if (message.type === 'error') {
        setConnectionStatus('error', String(message.message));
        return;
      }

      if (message.run_id && message.run_id !== useDebuggerStore.getState().selectedRunId) return;

      // Handle run snapshot (new v1 architecture)
      if (message.type === 'snapshot') {
        cancelPendingRaf();
        pendingEventsRef.current = [];
        useDebuggerStore.getState().clearEvents();
        // Store run summary
        if (message.summary) {
          const summary: RunSummary = {
            run_id: message.run_id,
            config_id: message.summary.config_id || '',
            notebook_name: message.summary.notebook_name || '',
            task_name: message.summary.task_name || '',
            created_at: message.summary.started_at_ms || 0,
            policy_name: message.summary.policy_name || '',
            num_episodes: message.summary.num_episodes || 0,
            budget_slots: message.summary.budget_slots || 0,
            success_rate: message.success_rate !== undefined
              ? message.success_rate
              : message.summary.metrics?.success_rate ?? null,
            summary: message.summary,
          };
          setCurrentRunSummary(summary);
        }

        // Process initial events
        if (message.events && Array.isArray(message.events)) {
          const events = readViewerEvents(message.events);
          if (events.length > 0) {
            addEvents(events);
          }
        }
        return;
      }

      // Handle streaming events (new v1 architecture)
      if (message.type === 'events') {
        if (message.events && Array.isArray(message.events)) {
          const events = readViewerEvents(message.events);
          processEvents(events);
        }
        return;
      }

      // Handle legacy event format
      // Server sends: {"type": "event", "data": {...}} for events
      let events: DebuggerEvent[];
      if (message.type === 'event' && message.data) {
        // Wrapped event
        events = [message.data as DebuggerEvent];
      } else if (Array.isArray(message)) {
        // Array of events (batch)
        events = message as DebuggerEvent[];
      } else if (message.eventId) {
        // Legacy: direct event object (has eventId field)
        events = [message as DebuggerEvent];
      } else {
        // Unknown message format
        console.warn('Unknown WebSocket message format:', message);
        return;
      }

      processEvents(events);
    } catch (e) {
      setConnectionStatus('error', `Cannot display event: ${String(e)}`);
    }
  }, [addEvents, setCurrentRunSummary, processEvents, setConnectionStatus, cancelPendingRaf]);

  // Connect to WebSocket
  const connect = useCallback(() => {
    // Don't connect if already connected or connecting
    if (
      wsRef.current?.readyState === WebSocket.OPEN ||
      wsRef.current?.readyState === WebSocket.CONNECTING
    ) {
      return;
    }

    clearReconnectTimeout();
    setConnectionStatus('connecting');

    try {
      // Build URL with run_id if selected
      const { wsUrl, selectedRunId } = useDebuggerStore.getState();
      let url = wsUrl;
      if (selectedRunId) {
        const separator = url.includes('?') ? '&' : '?';
        url = `${url}${separator}run_id=${encodeURIComponent(selectedRunId)}`;
      }

      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (wsRef.current !== ws) return;
        const desiredRun = useDebuggerStore.getState().selectedRunId;
        if (desiredRun && desiredRun !== selectedRunId) ws.send(JSON.stringify({ type: 'subscribe', run_id: desiredRun }));
        setConnectionStatus('connected');
        reconnectAttemptsRef.current = 0;
      };

      ws.onclose = (event) => {
        if (wsRef.current !== ws) return;
        wsRef.current = null;

        // Only attempt reconnect if not closed intentionally
        if (event.code !== 1000 && reconnectDelay > 0) {
          const attempts = reconnectAttemptsRef.current;

          if (maxReconnectAttempts === 0 || attempts < maxReconnectAttempts) {
            // Exponential backoff
            const delay = Math.min(
              reconnectDelay * Math.pow(1.5, attempts),
              30000
            );

            setConnectionStatus('disconnected', `Reconnecting in ${Math.round(delay / 1000)}s...`);

            reconnectTimeoutRef.current = setTimeout(() => {
              reconnectAttemptsRef.current += 1;
              connect();
            }, delay);
          } else {
            setConnectionStatus('error', 'Max reconnection attempts reached');
          }
        } else {
          setConnectionStatus('disconnected');
        }
      };

      ws.onerror = (event) => {
        console.error('WebSocket error:', event);
        setConnectionStatus('error', 'Connection error');
      };

      ws.onmessage = handleMessage;
    } catch (e) {
      console.error('Failed to create WebSocket:', e);
      setConnectionStatus('error', 'Failed to create connection');
    }
  }, [setConnectionStatus, reconnectDelay, maxReconnectAttempts, clearReconnectTimeout, handleMessage]);

  // Disconnect from WebSocket
  const disconnect = useCallback(() => {
    clearReconnectTimeout();
    cancelPendingRaf();
    reconnectAttemptsRef.current = 0;

    // Flush any remaining pending events before disconnect
    if (pendingEventsRef.current.length > 0) {
      addEvents(pendingEventsRef.current);
      pendingEventsRef.current = [];
    }

    if (wsRef.current) {
      const ws = wsRef.current;
      wsRef.current = null;
      ws.close(1000, 'User disconnected');
      setConnectionStatus('disconnected');
    }
  }, [clearReconnectTimeout, cancelPendingRaf, addEvents, setConnectionStatus]);

  // Subscribe to a specific run
  const subscribeToRun = useCallback((runId: string) => {
    cancelPendingRaf();
    pendingEventsRef.current = [];
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'subscribe', run_id: runId }));
    }
  }, [cancelPendingRaf]);

  // Send a message
  const send = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    } else {
      console.warn('WebSocket is not connected');
    }
  }, []);

  // Auto-connect on mount
  useEffect(() => {
    if (autoConnect) {
      connect();
    }

    return () => {
      clearReconnectTimeout();
      cancelPendingRaf();
      if (wsRef.current) {
        wsRef.current.close(1000, 'Component unmounted');
        wsRef.current = null;
      }
    };
  }, [autoConnect, connect, clearReconnectTimeout, cancelPendingRaf]);

  return { connect, disconnect, send, subscribeToRun };
}

/** Validate the server's viewer format without reinterpreting raw operations. */
function readViewerEvents(rawEvents: unknown[]): DebuggerEvent[] {
  return rawEvents.map(raw => {
    if (!raw || typeof raw !== 'object') throw new Error('Expected a viewer event');
    const event = raw as Record<string, unknown>;
    if (typeof event.eventId !== 'string' || typeof event.episodeId !== 'string'
        || typeof event.step !== 'number' || !Array.isArray(event.memoryEvents)
        || !Array.isArray(event.snapshot)) {
      throw new Error('Server supplied an unsupported event format');
    }
    return event as unknown as DebuggerEvent;
  });
}

export default useWebSocket;
