"""
Run ingestion and streaming API.

REST endpoints for importing, listing, and retrieving runs.
This is the primary integration point for the viz server - it consumes
RunExport bundles rather than requiring a live CMM in the same process.

Endpoints:
    POST /v1/runs/import - Upload full run bundle (RunExport JSON)
    POST /v1/runs/{run_id}/events - Append events (NDJSON)
    POST /v1/runs/import-path - Import from local path (dev-only)
    GET /v1/runs - List runs
    GET /v1/runs/{run_id} - Get run summary
    GET /v1/runs/{run_id}/events - Get events (paginated)
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException, Query, Request
from pydantic import BaseModel

from reckon.viz.projection import parse_events_jsonl
from reckon.viz.storage import RunMeta, find_events_file, parse_run_export

logger = logging.getLogger(__name__)

router = APIRouter()

# ==============================================================================
# Constants
# ==============================================================================

# Maximum event size in bytes (256 KB)
MAX_EVENT_SIZE = 256 * 1024

# Counters for logging
_counters = {
    "events_received": 0,
    "events_rejected_size": 0,
}


# ==============================================================================
# Pydantic Models
# ==============================================================================


class RunSummaryResponse(BaseModel):
    """Run summary for API responses."""

    # The HTTP model declares its own wire fields, separately from stored metadata.
    # pylint: disable=duplicate-code
    run_id: str
    config_id: str
    notebook_name: str
    task_name: str
    created_at: int
    policy_name: str
    num_episodes: int
    budget_slots: int
    success_rate: Optional[float]
    summary: dict  # Full RunSummary as dict
    # pylint: enable=duplicate-code


class RunListResponse(BaseModel):
    """Paginated list of runs."""

    runs: list[RunSummaryResponse]
    total_count: int
    has_more: bool


class EventsResponse(BaseModel):
    """Paginated events response."""

    events: list[dict]
    total_count: int
    has_more: bool
    run_id: str


class ImportResponse(BaseModel):
    """Response from import operations."""

    run_id: str
    events_count: int
    message: str


class ImportPathRequest(BaseModel):
    """Request to import from local path."""

    path: str  # Path to run directory or RunExport JSON


# ==============================================================================
# Helper Functions
# ==============================================================================


def _get_storage(request: Request):
    """Get storage instances from app state."""
    # These are set in server.py on startup
    run_index = getattr(request.app.state, "run_index", None)
    run_store = getattr(request.app.state, "run_store", None)
    if run_index is None or run_store is None:
        raise HTTPException(
            status_code=503,
            detail="Storage not initialized",
        )
    return run_index, run_store


def _get_fanout(request: Request):
    """Get the event fanout from app state."""
    return getattr(request.app.state, "event_fanout", None)


def _parse_events_jsonl(events_bytes: bytes) -> list[dict]:
    """Validate and convert every event through the shared server projection."""
    try:
        return parse_events_jsonl(events_bytes)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ==============================================================================
# Import Endpoints
# ==============================================================================


@router.post("/runs/import", response_model=ImportResponse)
async def import_run(
    request: Request,
    run_export: dict = Body(..., description="RunExport JSON"),
) -> ImportResponse:
    """
    Import a full run bundle (RunExport JSON).

    Accepts a RunExport containing:
    - run_id: Unique identifier
    - summary: RunSummary with metadata
    - events_jsonl_bytes: Events as JSONL (string or base64)

    The run is stored in the index and artifacts are written to disk.
    """
    run_index, run_store = _get_storage(request)

    try:
        meta, events_bytes = parse_run_export(run_export)
    except (KeyError, TypeError) as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid RunExport format: {e}",
        ) from e

    if not meta.run_id:
        raise HTTPException(
            status_code=400,
            detail="run_id is required",
        )

    events = _parse_events_jsonl(events_bytes)
    try:
        run_store.get_events_path(meta.run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if run_index.get_run(meta.run_id) is not None:
        raise HTTPException(status_code=409, detail="Run already exists; choose a new run_id")

    try:
        run_store.create_run(meta.run_id, events_bytes, meta.summary_json)
    except FileExistsError as exc:
        raise HTTPException(
            status_code=409, detail="Run destination already exists; choose a new run_id"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Add to index
    run_index.add_run(meta)

    return ImportResponse(
        run_id=meta.run_id,
        events_count=len(events),
        message=f"Imported run {meta.run_id} with {len(events)} events",
    )


def _read_import_directory(path: Path):
    """Read HTTP directory metadata without treating config as a run summary."""
    # Look for events.jsonl in the directory
    events_path = find_events_file(path)
    if events_path is None:
        raise HTTPException(
            status_code=400,
            detail="No events.jsonl found in directory",
        )

    events_bytes = events_path.read_bytes()

    # Look for summary.json or config.json
    summary_path = path / "summary.json"
    config_path = path / "config.json"

    summary: dict[str, Any] = {}
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    elif config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            summary = {"config_json": json.dumps(config)}
        except json.JSONDecodeError:
            pass

    # Create RunMeta from directory name
    run_id = path.name
    meta = RunMeta.from_summary(run_id, summary, path.name, omit_empty=True)
    return meta, events_bytes


@router.post("/runs/import-path", response_model=ImportResponse)
async def import_run_from_path(
    request: Request,
    import_request: ImportPathRequest,
) -> ImportResponse:
    """
    Import a run from a local filesystem path (development only).

    Accepts either:
    - Path to a RunExport JSON file
    - Path to a run directory containing events.jsonl

    This endpoint is intended for development/testing only.
    """
    run_index, run_store = _get_storage(request)

    path = Path(import_request.path)
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Path not found: {path}",
        )

    # Determine if it's a file or directory
    if path.is_file():
        # Assume it's a RunExport JSON
        try:
            run_export = json.loads(path.read_text(encoding="utf-8"))
            meta, events_bytes = parse_run_export(run_export)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid RunExport JSON: {e}",
            ) from e
    elif path.is_dir():
        meta, events_bytes = _read_import_directory(path)
    else:
        raise HTTPException(
            status_code=400,
            detail="Path must be a file or directory",
        )

    events = _parse_events_jsonl(events_bytes)
    try:
        run_store.get_events_path(meta.run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if run_index.get_run(meta.run_id) is not None:
        raise HTTPException(status_code=409, detail="Run already exists; choose a new run_id")

    try:
        run_store.create_run(meta.run_id, events_bytes, meta.summary_json)
    except FileExistsError as exc:
        raise HTTPException(
            status_code=409, detail="Run destination already exists; choose a new run_id"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    run_index.add_run(meta)

    return ImportResponse(
        run_id=meta.run_id,
        events_count=len(events),
        message=f"Imported run from {path} with {len(events)} events",
    )


# ==============================================================================
# Event Streaming Endpoint
# ==============================================================================


@router.post("/runs/{run_id}/events")
async def append_events(
    request: Request,
    run_id: str,
    events: list[dict] = Body(..., description="Events as array of objects"),
) -> dict:
    """
    Append events to an existing run.

    Events are appended to the run's events.jsonl file and
    broadcast to WebSocket subscribers via fanout.

    Events larger than MAX_EVENT_SIZE (256KB) are rejected with 413.
    Exact repeats of an event identity are skipped; changed content is refused.
    """
    run_index, run_store = _get_storage(request)

    # Verify run exists
    meta = run_index.get_run(run_id)
    if meta is None:
        raise HTTPException(
            status_code=404,
            detail=f"Run {run_id} not found",
        )

    # Validate the whole batch before storage or broadcast.
    _parse_events_jsonl("\n".join(json.dumps(e) for e in events).encode())

    # Check event sizes and filter oversized events
    accepted_events = []
    for event in events:
        _counters["events_received"] += 1
        event_json = json.dumps(event)
        if len(event_json.encode("utf-8")) > MAX_EVENT_SIZE:
            _counters["events_rejected_size"] += 1
            logger.warning(
                "Event rejected: size %d exceeds MAX_EVENT_SIZE %d",
                len(event_json.encode("utf-8")),
                MAX_EVENT_SIZE,
            )
            raise HTTPException(
                status_code=413,
                detail=f"Event size exceeds maximum allowed ({MAX_EVENT_SIZE} bytes)",
            )
        accepted_events.append(event)

    fanout = _get_fanout(request)
    if fanout is None:
        raise HTTPException(status_code=503, detail="Event streaming not initialized")
    try:
        accepted_events = await fanout.append_events(run_store, run_id, accepted_events)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    logger.info(
        "Events appended: run=%s count=%d (received=%d rejected_size=%d)",
        run_id,
        len(accepted_events),
        _counters["events_received"],
        _counters["events_rejected_size"],
    )

    return {
        "run_id": run_id,
        "appended": len(accepted_events),
    }


# ==============================================================================
# Query Endpoints
# ==============================================================================


@router.get("/runs", response_model=RunListResponse)
async def list_runs(
    request: Request,
    limit: int = Query(50, ge=1, le=100, description="Maximum runs to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    config_id: Optional[str] = Query(None, description="Filter by config_id"),
    task_name: Optional[str] = Query(None, description="Filter by task_name"),
) -> RunListResponse:
    """
    List runs with optional filtering.

    Returns runs ordered by creation time (newest first).
    """
    run_index, _run_store = _get_storage(request)

    runs = run_index.list_runs(
        limit=limit + 1,  # Fetch one extra to detect has_more
        offset=offset,
        config_id=config_id,
        task_name=task_name,
    )

    has_more = len(runs) > limit
    if has_more:
        runs = runs[:limit]

    total_count = run_index.count_runs()

    return RunListResponse(
        runs=[
            RunSummaryResponse(
                run_id=r.run_id,
                config_id=r.config_id,
                notebook_name=r.notebook_name,
                task_name=r.task_name,
                created_at=r.created_at,
                policy_name=r.policy_name,
                num_episodes=r.num_episodes,
                budget_slots=r.budget_slots,
                success_rate=r.success_rate,
                summary=json.loads(r.summary_json) if r.summary_json else {},
            )
            for r in runs
        ],
        total_count=total_count,
        has_more=has_more,
    )


@router.get("/runs/{run_id}", response_model=RunSummaryResponse)
async def get_run(
    request: Request,
    run_id: str,
) -> RunSummaryResponse:
    """Get a run by ID."""
    run_index, _run_store = _get_storage(request)

    meta = run_index.get_run(run_id)
    if meta is None:
        raise HTTPException(
            status_code=404,
            detail=f"Run {run_id} not found",
        )

    return RunSummaryResponse(
        run_id=meta.run_id,
        config_id=meta.config_id,
        notebook_name=meta.notebook_name,
        task_name=meta.task_name,
        created_at=meta.created_at,
        policy_name=meta.policy_name,
        num_episodes=meta.num_episodes,
        budget_slots=meta.budget_slots,
        success_rate=meta.success_rate,
        summary=json.loads(meta.summary_json) if meta.summary_json else {},
    )


@router.get("/runs/{run_id}/events", response_model=EventsResponse)
# FastAPI declares these independent path and query parameters in the HTTP contract.
async def get_events(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    request: Request,
    run_id: str,
    limit: int = Query(1000, ge=1, le=10000, description="Maximum events to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    episode_id: Optional[str] = Query(None, description="Filter by episode_id"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
) -> EventsResponse:
    """
    Get events for a run with pagination.

    Events are returned in chronological order (by timestamp).
    """
    run_index, run_store = _get_storage(request)

    # Verify run exists
    meta = run_index.get_run(run_id)
    if meta is None:
        raise HTTPException(
            status_code=404,
            detail=f"Run {run_id} not found",
        )

    # Get events from store
    try:
        events_bytes = run_store.get_events(run_id)
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail=f"Events not found for run {run_id}",
        ) from e

    # Parse and filter
    events = _parse_events_jsonl(events_bytes)

    if episode_id:
        events = [e for e in events if e.get("episodeId") == episode_id]
    if event_type:
        events = [
            e
            for e in events
            if str(e.get("eventType")) == event_type
            or e.get("kernelEvent", {}).get("op_type") == event_type
        ]

    total_count = len(events)
    paginated = events[offset : offset + limit]
    has_more = offset + limit < total_count

    return EventsResponse(
        events=paginated,
        total_count=total_count,
        has_more=has_more,
        run_id=run_id,
    )
