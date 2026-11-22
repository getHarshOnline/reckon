"""
Reckon Visualization Server Routes

API endpoints for the memory debugger.

Routes:
    events: Legacy event log API (reads from live CMM)
    runs: Run ingestion and streaming API (v1 architecture)
    ws: WebSocket endpoints for real-time streaming
"""

from reckon.viz.routes import events, runs, ws

__all__ = ["events", "runs", "ws"]
