"""
EpisodeContext for tracking retrieved records and credit assignment.

The EpisodeContext uses Python's ContextVar to provide thread-local/async-local
storage that tracks which records were retrieved during an episode step.
This enables automatic credit assignment when observe() is called.

.. code-block:: python

    # In-process SDK mode (implicit context)
    with EpisodeContext(episode_id="ep_001") as ctx:
        records = manager.retrieve(query)  # auto-tracked
        # ... agent does something with records ...
        credits = manager.observe(outcome=1.0)  # uses ctx.retrieved_record_ids

    # Explicit Python context (the daemon has its own context IDs)
    ctx = EpisodeContext(episode_id="ep_001")
    records = manager.retrieve(query, context=ctx)
    credits = manager.observe(outcome=1.0, context=ctx)
"""

from __future__ import annotations

import uuid
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import List, Optional, Any

__all__ = [
    "EpisodeContext",
    "get_current_context",
    "set_current_context",
    "clear_current_context",
]


# Thread-local/async-local context variable
_current_context: ContextVar[Optional["EpisodeContext"]] = ContextVar(
    "reckon_episode_context", default=None
)


@dataclass
class EpisodeContext:
    """
    Context for tracking episode state and retrieved records.

    The EpisodeContext tracks which records were retrieved during an episode
    step, enabling credit assignment when observe() is called. It supports
    implicit ContextVar use and explicit passing of this context object.
    The daemon has a separate registry addressed by context IDs.

    Attributes:
        id: Unique context identifier (auto-generated UUID)
        episode_id: Episode identifier for grouping
        step: Current step number within the episode
        retrieved_record_ids: IDs of records retrieved in this context
        created_at_ms: Timestamp when context was created
        ttl_ms: Context lifetime; observe refuses expired contexts (default 5 minutes)
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    episode_id: str = ""
    step: int = 0
    retrieved_record_ids: List[str] = field(default_factory=list)
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    ttl_ms: int = 300000  # 5 minutes default

    # Internal: token for context reset
    _token: Any = field(default=None, repr=False, compare=False)

    def __enter__(self) -> "EpisodeContext":
        """Enter context manager, setting this as the current context."""
        self._token = _current_context.set(self)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context manager, restoring previous context."""
        if self._token is not None:
            _current_context.reset(self._token)
            self._token = None

    @classmethod
    def current(cls) -> Optional["EpisodeContext"]:
        """
        Get the current context from ContextVar.

        Returns:
            The current EpisodeContext, or None if not in a context.
        """
        return _current_context.get()

    def is_expired(self) -> bool:
        """
        Check whether elapsed time since creation exceeds this context's TTL.

        Returns:
            True if the context has exceeded its TTL.
        """
        now_ms = int(time.time() * 1000)
        return (now_ms - self.created_at_ms) > self.ttl_ms

    def add_retrieved_record(self, record_id: str) -> None:
        """
        Add a record ID to the retrieved list.

        Args:
            record_id: ID of the retrieved record.
        """
        if record_id not in self.retrieved_record_ids:
            self.retrieved_record_ids.append(record_id)

    def add_retrieved_records(self, record_ids: List[str]) -> None:
        """
        Add multiple record IDs to the retrieved list.

        Args:
            record_ids: IDs of the retrieved records.
        """
        for rid in record_ids:
            self.add_retrieved_record(rid)

    def clear_retrieved_records(self) -> None:
        """Clear the retrieved record IDs list."""
        self.retrieved_record_ids.clear()

    def advance_step(self) -> None:
        """Advance to the next step, clearing retrieved records."""
        self.step += 1
        self.clear_retrieved_records()

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "episode_id": self.episode_id,
            "step": self.step,
            "retrieved_record_ids": self.retrieved_record_ids,
            "created_at_ms": self.created_at_ms,
            "ttl_ms": self.ttl_ms,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EpisodeContext":
        """Create from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            episode_id=data.get("episode_id", ""),
            step=data.get("step", 0),
            retrieved_record_ids=data.get("retrieved_record_ids", []),
            created_at_ms=data.get("created_at_ms", int(time.time() * 1000)),
            ttl_ms=data.get("ttl_ms", 300000),
        )


def get_current_context() -> Optional[EpisodeContext]:
    """
    Get the current episode context.

    Returns:
        The current EpisodeContext, or None if not in a context.
    """
    return _current_context.get()


def set_current_context(ctx: Optional[EpisodeContext]) -> Any:
    """
    Set the current episode context.

    Args:
        ctx: The context to set, or None to clear.

    Returns:
        Token that can be used to reset the context.
    """
    return _current_context.set(ctx)


def clear_current_context() -> None:
    """Clear the current episode context."""
    _current_context.set(None)
