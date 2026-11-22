"""
Reckon Visualization Module

Debugger and visualization tools for the Causal Memory Manager.

Components:
- server: FastAPI application for the debugger UI
- routes: REST API and WebSocket endpoints
- storage: SQLite index + filesystem storage for runs
- cli: Command-line interface for viz operations

Usage:
    # Start the visualization server
    uvicorn reckon.viz.server:app --reload

    # Or via CLI
    reckon viz serve --port 8000

    # With fixtures loaded for testing
    RECKON_VIZ_LOAD_FIXTURES=1 reckon viz serve

    # Import a run
    reckon viz import ./runs/my_run/

The debugger provides:
1. Timeline View: per-episode memory events
2. Causal Link View: records -> outcomes graph
3. Budget vs Performance Frontier
4. Representation Drift Panel

See docs/10-Debugger.md for full documentation.
"""

from reckon.viz.registry import get_cmm, has_cmm, register_cmm, unregister_cmm
from reckon.viz.server import app, create_app
from reckon.viz.storage import RunIndex, RunMeta, RunStore, create_storage

__all__ = [
    "create_app",
    "app",
    "register_cmm",
    "unregister_cmm",
    "get_cmm",
    "has_cmm",
    "RunIndex",
    "RunStore",
    "RunMeta",
    "create_storage",
]
