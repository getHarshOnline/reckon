"""
Reckon Visualization Server

FastAPI application serving the memory debugger UI and event streaming API.

Architecture:
    The viz server consumes RunExport bundles (summary + events JSONL)
    rather than requiring a live CMM instance. This enables:
    - Loading fixture data for CI/testing
    - Importing runs from notebooks
    - Streaming events in real-time via WebSocket

Usage:
    uvicorn reckon.viz.server:app --reload

    # Or via CLI
    reckon viz --port 8000

    # With fixtures loaded
    RECKON_VIZ_LOAD_FIXTURES=1 python -m reckon.viz.server

Environment Variables:
    RECKON_VIZ_LOAD_FIXTURES: Set to "1" to load fixture data on startup
    RECKON_VIZ_DATA_DIR: Override default data directory
"""

# Standard library
import argparse
import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

# Third party
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

try:
    import uvicorn

    HAS_UVICORN = True
except ImportError:
    uvicorn = None  # type: ignore[assignment]
    HAS_UVICORN = False

# Local
from reckon import __version__
from reckon.viz.routes import events, ws
from reckon.viz.routes import runs
from reckon.viz.routes.ws import RunEventFanout, ping_clients
from reckon.viz.storage import create_storage, parse_run_export
from reckon.viz.projection import parse_events_jsonl
from reckon.viz.live import follow_registered_manager

# Path to bundled React app (built from viz-ui/)
STATIC_DIR = Path(__file__).parent / "static"

# Path to fixtures
FIXTURES_DIR = Path(__file__).parents[3] / "runs" / "_fixtures"

logger = logging.getLogger(__name__)


def _load_fixtures(application: FastAPI) -> None:
    """Load fixture data into storage.

    Called on startup when RECKON_VIZ_LOAD_FIXTURES=1.
    """
    run_index = getattr(application.state, "run_index", None)
    run_store = getattr(application.state, "run_store", None)

    if run_index is None or run_store is None:
        logger.warning("Storage not initialized, skipping fixture loading")
        return

    for fixture_path in FIXTURES_DIR.glob("*.json"):
        try:
            export_data = json.loads(fixture_path.read_text())
            if "run_id" not in export_data:
                continue
            meta, events_bytes = parse_run_export(export_data)
            parse_events_jsonl(events_bytes)
            if run_index.get_run(meta.run_id) is not None:
                continue
            run_store.store_events(meta.run_id, events_bytes)
            if meta.summary_json:
                run_store.store_summary(meta.run_id, meta.summary_json)
            run_index.add_run(meta)
            logger.info("Loaded fixture: %s", meta.run_id)
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("Skipping fixture %s: %s", fixture_path.name, exc)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Application lifespan handler.

    Initializes storage and loads fixtures on startup.
    """
    # Initialize storage
    run_index, run_store = create_storage()
    application.state.run_index = run_index
    application.state.run_store = run_store

    # Set up event fanout for WebSocket streaming
    application.state.event_fanout = RunEventFanout()

    logger.info(
        "Storage initialized: %s",
        run_index.db_path.parent,
    )

    # Load fixtures if enabled
    if os.environ.get("RECKON_VIZ_LOAD_FIXTURES") == "1":
        _load_fixtures(application)
        logger.info("Fixtures loaded")

    application.state.live_error = None
    application.state.live_stop = asyncio.Event()
    live_task = asyncio.create_task(follow_registered_manager(application))
    ping_task = asyncio.create_task(ping_clients(application.state.event_fanout))

    yield

    # Stop subscriptions before releasing the application.
    application.state.live_stop.set()
    await live_task
    ping_task.cancel()
    try:
        await ping_task
    except asyncio.CancelledError:
        pass


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(
        title="Reckon Memory Debugger",
        description="Visualization and debugging server for Causal Memory Management",
        version=__version__,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        lifespan=lifespan,
    )

    # CORS for development
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes (legacy)
    application.include_router(events.router, prefix="/api", tags=["events"])

    # API routes (v1 - new architecture)
    application.include_router(runs.router, prefix="/v1", tags=["runs"])

    # WebSocket routes
    # Legacy: /ws/events, /ws/records
    application.include_router(ws.router, prefix="/ws", tags=["websocket"])
    # New: /v1/stream (mounted under root to support /v1/stream?run_id=...)
    application.include_router(ws.router, prefix="", tags=["websocket-v1"])

    # Health check
    @application.get("/health")
    async def health_check():
        run_index = getattr(application.state, "run_index", None)
        run_count = run_index.count_runs() if run_index else 0
        return {
            "status": "ok",
            "service": "reckon viz",
            "version": __version__,
            "runs_count": run_count,
            "live_error": application.state.live_error,
        }

    # Serve static files (bundled React app) if available
    if STATIC_DIR.exists():
        application.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return application


# Application instance
app = create_app()


def main(args: Optional[list[str]] = None) -> int:
    """CLI entry point for the visualization server."""
    parser = argparse.ArgumentParser(
        description="Reckon Memory Debugger Server",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind to",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="Logging level",
    )
    parser.add_argument(
        "--load-fixtures",
        action="store_true",
        help="Load fixture data on startup",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Override data directory",
    )

    parsed = parser.parse_args(args)

    # Set environment variables for app configuration
    if parsed.load_fixtures:
        os.environ["RECKON_VIZ_LOAD_FIXTURES"] = "1"
    if parsed.data_dir:
        os.environ["RECKON_VIZ_DATA_DIR"] = parsed.data_dir

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, parsed.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    if not HAS_UVICORN or uvicorn is None:
        print("Error: uvicorn is required. Install with: pip install reckon[viz]")
        return 1

    uvicorn.run(
        "reckon.viz.server:app",
        host=parsed.host,
        port=parsed.port,
        reload=parsed.reload,
        log_level=parsed.log_level,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
