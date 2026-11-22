"""
Event Log API Routes

REST endpoints for querying and managing memory event logs.

When a CausalMemoryManager is registered via the registry, events are read
from the Rust EventLogger. Otherwise, falls back to in-memory storage.
"""

import json
from dataclasses import dataclass, field
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from reckon.viz.registry import get_cmm, has_cmm

router = APIRouter()


# Pydantic models for API responses
class ResourceUsage(BaseModel):
    """Current resource usage snapshot."""
    slot_count: int
    byte_count: int
    token_count: int
    ops_in_window: int


class MemoryEventResponse(BaseModel):
    """A memory operation event."""
    event_id: str
    op_type: str
    timestamp: int
    episode_id: str
    record_id: Optional[str] = None
    prune_reason: Optional[str] = None
    score_type: Optional[str] = None
    old_score: Optional[float] = None
    new_score: Optional[float] = None
    usage_after: Optional[ResourceUsage] = None
    duration_us: int = 0


class DebuggerEventResponse(BaseModel):
    """A high-level debugger event."""
    event_id: str
    event_type: str
    wall_time_ms: int
    episode_id: str
    step: int
    memory_events: list[MemoryEventResponse] = []


class EventsListResponse(BaseModel):
    """Paginated list of events."""
    events: list[DebuggerEventResponse]
    total_count: int
    has_more: bool


class EpisodeSummary(BaseModel):
    """Summary of an episode."""
    episode_id: str
    start_time_ms: int
    end_time_ms: Optional[int] = None
    total_writes: int
    total_reads: int
    total_prunes: int
    final_slots: int
    final_bytes: int


# In-memory event storage (fallback when no CMM is registered)
@dataclass
class EventStore:
    """In-memory event store for standalone operation."""
    events: list[dict] = field(default_factory=list)
    episodes: dict[str, dict] = field(default_factory=dict)


_store = EventStore()


def _get_events_from_cmm() -> list[dict]:
    """Get events from the registered CMM's EventLogger.

    Returns:
        List of event dicts from the Rust EventLogger, or empty list if no CMM.
    """
    cmm = get_cmm()
    if cmm is None:
        return []

    # Get JSONL from EventLogger and parse
    # pylint: disable-next=protected-access
    jsonl = cmm._logger.peek()  # noqa: SLF001
    if not jsonl:
        return []

    events = []
    for line in jsonl.strip().split("\n"):
        if line:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


# pylint: disable=too-many-arguments,too-many-positional-arguments
@router.get("/events", response_model=EventsListResponse)
async def list_events(
    episode_id: Optional[str] = Query(None, description="Filter by episode ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    from_step: Optional[int] = Query(None, description="Events from this step"),
    to_step: Optional[int] = Query(None, description="Events until this step"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum events to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
) -> EventsListResponse:
    """
    List debugger events with optional filtering.

    Returns events in chronological order with pagination support.
    Uses registered CMM's EventLogger when available, falls back to in-memory store.
    """
    # Get events from CMM if registered, otherwise use fallback store
    if has_cmm():
        raw_events = _get_events_from_cmm()
        # Convert Rust EventLogger format to expected format
        filtered = [
            {
                "event_id": str(e.get("event_id", "")),
                "event_type": e.get("op_type", ""),
                "wall_time_ms": 0,
                "episode_id": e.get("episode_id", ""),
                "step": e.get("timestamp", 0),
            }
            for e in raw_events
        ]
    else:
        filtered = _store.events

    if episode_id:
        filtered = [e for e in filtered if e.get("episode_id") == episode_id]
    if event_type:
        filtered = [e for e in filtered if e.get("event_type") == event_type]
    if from_step is not None:
        filtered = [e for e in filtered if e.get("step", 0) >= from_step]
    if to_step is not None:
        filtered = [e for e in filtered if e.get("step", 0) <= to_step]

    total_count = len(filtered)
    paginated = filtered[offset : offset + limit]
    has_more = offset + limit < total_count

    # Convert to response models
    events = []
    for e in paginated:
        events.append(
            DebuggerEventResponse(
                event_id=e.get("event_id", ""),
                event_type=e.get("event_type", ""),
                wall_time_ms=e.get("wall_time_ms", 0),
                episode_id=e.get("episode_id", ""),
                step=e.get("step", 0),
                memory_events=[],
            )
        )

    return EventsListResponse(
        events=events,
        total_count=total_count,
        has_more=has_more,
    )


@router.get("/events/{event_id}", response_model=DebuggerEventResponse)
async def get_event(event_id: str) -> DebuggerEventResponse:
    """
    Get a specific event by ID.
    """
    for e in _store.events:
        if e.get("event_id") == event_id:
            return DebuggerEventResponse(
                event_id=e.get("event_id", ""),
                event_type=e.get("event_type", ""),
                wall_time_ms=e.get("wall_time_ms", 0),
                episode_id=e.get("episode_id", ""),
                step=e.get("step", 0),
                memory_events=[],
            )

    raise HTTPException(status_code=404, detail=f"Event {event_id} not found")


@router.get("/episodes", response_model=list[EpisodeSummary])
async def list_episodes(
    limit: int = Query(50, ge=1, le=100, description="Maximum episodes to return"),
) -> list[EpisodeSummary]:
    """
    List all episodes with summary statistics.
    """
    summaries = []
    for ep_id, ep_data in list(_store.episodes.items())[:limit]:
        summaries.append(
            EpisodeSummary(
                episode_id=ep_id,
                start_time_ms=ep_data.get("start_time_ms", 0),
                end_time_ms=ep_data.get("end_time_ms"),
                total_writes=ep_data.get("total_writes", 0),
                total_reads=ep_data.get("total_reads", 0),
                total_prunes=ep_data.get("total_prunes", 0),
                final_slots=ep_data.get("final_slots", 0),
                final_bytes=ep_data.get("final_bytes", 0),
            )
        )
    return summaries


@router.get("/episodes/{episode_id}", response_model=EpisodeSummary)
async def get_episode(episode_id: str) -> EpisodeSummary:
    """
    Get summary for a specific episode.
    """
    ep_data = _store.episodes.get(episode_id)
    if not ep_data:
        raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")

    return EpisodeSummary(
        episode_id=episode_id,
        start_time_ms=ep_data.get("start_time_ms", 0),
        end_time_ms=ep_data.get("end_time_ms"),
        total_writes=ep_data.get("total_writes", 0),
        total_reads=ep_data.get("total_reads", 0),
        total_prunes=ep_data.get("total_prunes", 0),
        final_slots=ep_data.get("final_slots", 0),
        final_bytes=ep_data.get("final_bytes", 0),
    )


@router.delete("/events")
async def clear_events() -> dict:
    """
    Clear all events from the store.

    Use with caution - this cannot be undone.
    """
    count = len(_store.events)
    _store.events.clear()
    _store.episodes.clear()
    return {"cleared": count}


# Internal function to add events (called by the CMM integration)
def add_event(event: dict) -> None:
    """Add an event to the store (internal use)."""
    _store.events.append(event)

    # Update episode tracking
    episode_id = event.get("episode_id")
    if episode_id:
        if episode_id not in _store.episodes:
            _store.episodes[episode_id] = {
                "start_time_ms": event.get("wall_time_ms", 0),
                "total_writes": 0,
                "total_reads": 0,
                "total_prunes": 0,
                "final_slots": 0,
                "final_bytes": 0,
            }

        ep = _store.episodes[episode_id]
        event_type = event.get("event_type", "")

        if event_type == "EPISODE_END":
            ep["end_time_ms"] = event.get("wall_time_ms", 0)
            if "final_usage" in event:
                ep["final_slots"] = event["final_usage"].get("slot_count", 0)
                ep["final_bytes"] = event["final_usage"].get("byte_count", 0)
            ep["total_writes"] = event.get("total_writes", 0)
            ep["total_prunes"] = event.get("total_prunes", 0)
