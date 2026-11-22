"""
WebSocket Routes for Real-Time Event Streaming

Provides WebSocket endpoints for live event streaming to the debugger UI.

Endpoints:
    /ws/events - Legacy endpoint for live CMM event streaming
    /ws/records - Record updates for causal graph view
    /v1/stream?run_id=... - Run-based event streaming (new architecture)
"""

# pylint: disable=duplicate-code

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from reckon.viz.projection import parse_events_jsonl, project_event
from reckon.viz.storage import check_event_duplicates

if TYPE_CHECKING:
    from reckon.viz.storage import RunIndex, RunMeta, RunStore

logger = logging.getLogger(__name__)

router = APIRouter()

# ==============================================================================
# Constants
# ==============================================================================

# Maximum event size in bytes (256 KB)
MAX_EVENT_SIZE = 256 * 1024


@dataclass
class ConnectionManager:
    """Manages active WebSocket connections."""

    # Active connections by subscription type
    connections: dict[str, list[WebSocket]] = field(default_factory=dict)
    # Episode subscriptions
    episode_subscriptions: dict[WebSocket, set[str]] = field(default_factory=dict)

    async def connect(self, websocket: WebSocket, channel: str = "events") -> None:
        """Accept a new WebSocket connection."""
        await websocket.accept()
        if channel not in self.connections:
            self.connections[channel] = []
        self.connections[channel].append(websocket)
        self.episode_subscriptions[websocket] = set()

    def disconnect(self, websocket: WebSocket, channel: str = "events") -> None:
        """Remove a WebSocket connection."""
        if channel in self.connections and websocket in self.connections[channel]:
            self.connections[channel].remove(websocket)
        if websocket in self.episode_subscriptions:
            del self.episode_subscriptions[websocket]

    def subscribe_episode(self, websocket: WebSocket, episode_id: str) -> None:
        """Subscribe a connection to a specific episode."""
        if websocket in self.episode_subscriptions:
            self.episode_subscriptions[websocket].add(episode_id)

    def unsubscribe_episode(self, websocket: WebSocket, episode_id: str) -> None:
        """Unsubscribe a connection from an episode."""
        if websocket in self.episode_subscriptions:
            self.episode_subscriptions[websocket].discard(episode_id)

    async def broadcast(self, message: dict, channel: str = "events") -> None:
        """Broadcast a message to all connections on a channel."""
        if channel not in self.connections:
            return

        disconnected = []
        for websocket in self.connections[channel]:
            try:
                await websocket.send_json(message)
            except Exception:  # pylint: disable=broad-exception-caught
                disconnected.append(websocket)

        # Clean up disconnected clients
        for ws in disconnected:
            self.disconnect(ws, channel)

    async def send_to_episode_subscribers(self, message: dict, episode_id: str) -> None:
        """Send a message to all subscribers of an episode."""
        for websocket, episodes in self.episode_subscriptions.items():
            if episode_id in episodes or not episodes:  # Empty set = all episodes
                with contextlib.suppress(Exception):
                    await websocket.send_json(message)


# Global connection manager
manager = ConnectionManager()


# ==============================================================================
# Run-based Event Fanout (new architecture)
# ==============================================================================


@dataclass
class RunEventFanout:
    """Serialize snapshot subscription and appends for each run in this server.

    Slow connections close after ten seconds; their persisted events are available
    in the next snapshot. No queue silently drops old operations.
    """

    run_connections: dict[str, list[WebSocket]] = field(default_factory=dict)
    all_connections: set[WebSocket] = field(default_factory=set)
    run_locks: dict[str, asyncio.Lock] = field(default_factory=dict)
    send_locks: dict[WebSocket, asyncio.Lock] = field(default_factory=dict)

    def run_lock(self, run_id: str) -> asyncio.Lock:
        """Return the lock shared by snapshot registration and persisted appends."""
        return self.run_locks.setdefault(run_id, asyncio.Lock())

    def subscribe(self, websocket: WebSocket, run_id: str) -> None:
        """Register after sending a snapshot while holding the run lock."""
        connections = self.run_connections.setdefault(run_id, [])
        if websocket not in connections:
            connections.append(websocket)
        self.all_connections.add(websocket)

    def unsubscribe(self, websocket: WebSocket, run_id: str) -> None:
        """Remove a run subscription."""
        connections = self.run_connections.get(run_id, [])
        if websocket in connections:
            connections.remove(websocket)
        if not connections:
            self.run_connections.pop(run_id, None)
        self.all_connections.discard(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Release every subscription and send lock for a connection."""
        for run_id in list(self.run_connections):
            self.unsubscribe(websocket, run_id)
        self.send_locks.pop(websocket, None)

    async def send(self, websocket: WebSocket, message: dict) -> None:
        """Send one message without interleaving concurrent writes."""
        lock = self.send_locks.setdefault(websocket, asyncio.Lock())
        try:
            async with lock:
                await asyncio.wait_for(websocket.send_json(message), timeout=10)
        except Exception:
            self.disconnect(websocket)
            with contextlib.suppress(Exception):
                await asyncio.wait_for(
                    websocket.close(1013, "Reconnect to reload stored events"), timeout=1
                )
            raise

    async def broadcast_events(self, run_id: str, events: list[dict]) -> None:
        """Deliver a persisted batch; disconnected clients recover by snapshot."""
        message = {
            "type": "events",
            "run_id": run_id,
            "events": [project_event(event) for event in events],
        }
        await asyncio.gather(
            *(
                self.send(websocket, message)
                for websocket in list(self.run_connections.get(run_id, []))
            ),
            return_exceptions=True,
        )

    async def append_events(self, store: "RunStore", run_id: str, events: list[dict]) -> list[dict]:
        """Deduplicate, persist and broadcast without a snapshot/append gap."""
        async with self.run_lock(run_id):
            try:
                existing = store.get_events(run_id)
            except FileNotFoundError:
                existing = b""
            accepted = check_event_duplicates(events, existing)
            if accepted:
                store.append_events(
                    run_id, "\n".join(json.dumps(event) for event in accepted).encode()
                )
                await self.broadcast_events(run_id, accepted)
            return accepted

    async def send_snapshot(
        self, websocket: WebSocket, meta: "RunMeta", events: list[dict]
    ) -> None:
        """Send every recorded event in the server's shared viewer format."""
        await self.send(
            websocket,
            {
                "type": "snapshot",
                "run_id": meta.run_id,
                "summary": json.loads(meta.summary_json) if meta.summary_json else {},
                "success_rate": meta.success_rate,
                "events": [project_event(event) for event in events],
            },
        )


@router.websocket("/events")
async def websocket_events(
    websocket: WebSocket,
    episode_id: Optional[str] = Query(None, description="Subscribe to specific episode"),
) -> None:
    """
    WebSocket endpoint for real-time event streaming.

    Connect to receive live debugger events. Optionally filter by episode ID.

    Example (JavaScript):
    ```js
    const ws = new WebSocket('ws://localhost:8000/ws/events?episode_id=ep1');
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log('Event:', data);
    };
    ```

    Message Types Received:
    - `event`: A new debugger event
    - `ping`: Keep-alive message (send `pong` in response)
    - `subscribed`: Confirmation of episode subscription

    Messages to Send:
    - `{"type": "subscribe", "episode_id": "..."}`: Subscribe to episode
    - `{"type": "unsubscribe", "episode_id": "..."}`: Unsubscribe from episode
    - `{"type": "pong"}`: Response to ping
    """
    await manager.connect(websocket, "events")

    # Subscribe to specific episode if provided
    if episode_id:
        manager.subscribe_episode(websocket, episode_id)
        await websocket.send_json(
            {
                "type": "subscribed",
                "episode_id": episode_id,
            }
        )

    try:
        while True:
            # Wait for messages from client
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                msg_type = message.get("type")

                if msg_type == "subscribe":
                    ep_id = message.get("episode_id")
                    if ep_id:
                        manager.subscribe_episode(websocket, ep_id)
                        await websocket.send_json(
                            {
                                "type": "subscribed",
                                "episode_id": ep_id,
                            }
                        )

                elif msg_type == "unsubscribe":
                    ep_id = message.get("episode_id")
                    if ep_id:
                        manager.unsubscribe_episode(websocket, ep_id)
                        await websocket.send_json(
                            {
                                "type": "unsubscribed",
                                "episode_id": ep_id,
                            }
                        )

                elif msg_type == "pong":
                    pass  # Client responding to ping

            except json.JSONDecodeError:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Invalid JSON",
                    }
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket, "events")


@router.websocket("/records")
async def websocket_records(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for real-time record updates.

    Streams record create/update/delete events for the causal graph view.
    """
    await manager.connect(websocket, "records")

    try:
        while True:
            data = await websocket.receive_text()
            # Echo for now - would handle record queries
            await websocket.send_json({"type": "ack", "data": data})

    except WebSocketDisconnect:
        manager.disconnect(websocket, "records")


# Internal functions for pushing events from CMM


async def push_event(event: dict) -> None:
    """Push an event to all connected clients."""
    message = {
        "type": "event",
        "data": event,
    }

    episode_id = event.get("episode_id")
    if episode_id:
        await manager.send_to_episode_subscribers(message, episode_id)
    else:
        await manager.broadcast(message, "events")


async def push_record_update(record_id: str, action: str, data: dict) -> None:
    """Push a record update to connected clients."""
    message = {
        "type": "record_update",
        "action": action,  # "create", "update", "delete"
        "record_id": record_id,
        "data": data,
    }
    await manager.broadcast(message, "records")


# Background task for keep-alive pings
async def ping_clients(run_fanout: RunEventFanout) -> None:
    """Send periodic pings to keep connections alive."""
    while True:
        await asyncio.sleep(30)
        # Ping legacy connections
        for _channel, connections in manager.connections.items():
            for websocket in connections:
                with contextlib.suppress(Exception):
                    await websocket.send_json({"type": "ping"})
        # Ping run stream connections
        for websocket in list(run_fanout.all_connections):
            with contextlib.suppress(Exception):
                await run_fanout.send(websocket, {"type": "ping"})


# ==============================================================================
# Run-based Stream Endpoint (new architecture)
# ==============================================================================


@router.websocket("/v1/stream")
async def websocket_run_stream(
    websocket: WebSocket,
    run_id: Optional[str] = Query(None, description="Run ID to stream"),
) -> None:
    """
    WebSocket endpoint for run-based event streaming.

    This is the primary endpoint for the new viz architecture:
    - Connect with ?run_id=... to subscribe to a specific run
    - On connect: receive snapshot with RunSummary + all existing events
    - Then receive live events as they are appended via POST /v1/runs/{run_id}/events

    Example (JavaScript):
    ```js
    const ws = new WebSocket('ws://localhost:8000/v1/stream?run_id=fixture_001');
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'snapshot') {
            // Initial data: data.summary, data.events
        } else if (data.type === 'events') {
            // New events: data.events
        }
    };
    ```

    Message Types Received:
    - `snapshot`: Initial data with summary and all events
    - `events`: New events appended to the run
    - `ping`: Keep-alive message (send `pong` in response)
    - `error`: Error message

    Messages to Send:
    - `{"type": "pong"}`: Response to ping
    - `{"type": "subscribe", "run_id": "..."}`: Subscribe to a different run
    """
    await websocket.accept()

    # Get storage from app state
    run_index = getattr(websocket.app.state, "run_index", None)
    run_store = getattr(websocket.app.state, "run_store", None)

    if run_index is None or run_store is None:
        await websocket.send_json(
            {
                "type": "error",
                "message": "Storage not initialized",
            }
        )
        await websocket.close(1011, "Storage not initialized")
        return

    run_fanout = websocket.app.state.event_fanout
    current_run_id = run_id

    # Send initial snapshot if run_id provided
    if current_run_id:
        await _send_run_snapshot(websocket, current_run_id, run_index, run_store)

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                msg_type = message.get("type")

                if msg_type != "subscribe" or not message.get("run_id"):
                    continue
                if current_run_id:
                    run_fanout.unsubscribe(websocket, current_run_id)
                current_run_id = message["run_id"]
                await _send_run_snapshot(websocket, current_run_id, run_index, run_store)

            except json.JSONDecodeError:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Invalid JSON",
                    }
                )

    except WebSocketDisconnect:
        pass
    finally:
        run_fanout.disconnect(websocket)


async def _send_run_snapshot(
    websocket: WebSocket,
    run_id: str,
    run_index: "RunIndex",
    run_store: "RunStore",
) -> None:
    """Send initial snapshot for a run to a WebSocket client."""
    run_fanout = websocket.app.state.event_fanout
    async with run_fanout.run_lock(run_id):
        meta = run_index.get_run(run_id)
        if meta is None:
            await run_fanout.send(
                websocket, {"type": "error", "message": f"Run {run_id} not found"}
            )
            return
        try:
            events = parse_events_jsonl(run_store.get_events(run_id))
        except FileNotFoundError:
            events = []
        except ValueError as exc:
            await run_fanout.send(websocket, {"type": "error", "message": str(exc)})
            return
        await run_fanout.send_snapshot(websocket, meta, events)
        run_fanout.subscribe(websocket, run_id)
