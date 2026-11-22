# pylint: disable=all
# type: ignore[override]
"""Type stubs for the Rust extension module (reckon._rust).

This module provides high-performance Rust implementations for:
- RecordStore: Memory record storage with O(1) lookup and O(log n) pruning
- EventLogger: High-frequency event ring buffer
- RetentionPolicy: Pluggable retention policies
"""


__version__: str
__doc__: str

from typing import Any

def payload_types() -> dict[str, str]: ...
def record_schema() -> str: ...

class _RecordValue:
    @staticmethod
    def _field_names() -> list[str]: ...
    def _field_values(self) -> dict[str, Any]: ...

class RecordCost(_RecordValue):
    bytes: int
    tokens: int | None
    slots: int
    def __new__(cls, bytes: int = 1, tokens: int | None = None, slots: int = 1) -> RecordCost: ...

class RecordOrigin(_RecordValue):
    source_op: str
    input_ids: list[str]
    hash: str
    def __new__(cls, source_op: str = "", input_ids: list[str] | None = None, hash: str = "") -> RecordOrigin: ...

class UtilityEstimate(_RecordValue):
    value: float
    uncertainty: float
    last_used: int
    use_count: int
    def __new__(cls, value: float = 0.0, uncertainty: float = 1.0, last_used: int = -1, use_count: int = 0) -> UtilityEstimate: ...

class CausalScore(_RecordValue):
    ablation_delta: float | None
    counterfactual_delta: float | None
    influence_proxy: float | None
    last_evaluated: int
    def __new__(cls, ablation_delta: float | None = None, counterfactual_delta: float | None = None,
                influence_proxy: float | None = None, last_evaluated: int = -1) -> CausalScore: ...

class MemoryRecord(_RecordValue):
    id: str
    timestamp: int
    payload_type: Any
    payload: Any
    cost: Any
    tags: list[str]
    provenance: Any
    utility: Any
    causal_score: Any
    episode_id: str
    metadata: dict[str, Any]
    compressed: bool
    encoding: str
    created_at_step: int | None
    created_at_sequence: int | None
    def __new__(cls, id: str, timestamp: int, payload_type: Any, payload: Any, cost: Any,
                tags: list[str], provenance: Any, utility: Any, causal_score: Any,
                episode_id: str, metadata: dict[str, Any], compressed: bool = False,
                encoding: str = "", created_at_step: int | None = None,
                created_at_sequence: int | None = None) -> MemoryRecord: ...
    def _snapshot_json(self, payload: bytes, metadata: bytes) -> str: ...
    def _snapshot_wire(self, payload: bytes, metadata: bytes) -> bytes: ...

DEFAULT_ETA: float
DEFAULT_U_MIN: float
DEFAULT_U_MAX: float
DEFAULT_SHAPED_SCALE: float

def select_retention(
    inputs: list[tuple[str, int, int, int, float, float | None, float | None, float | None, str, int]],
    policy: str,
    overflow_bytes: int,
    overflow_slots: int = 0,
    weight: float = 0.5,
    min_per_type: int = 1,
    overflow_tokens: int = 0,
) -> list[str]:
    """Select IDs from ranking inputs under byte, slot and token pressure."""
    ...

def compute_credit(
    inputs: list[tuple[float, float | None]],
    outcome: float,
    policy: str,
    shaped_scale: float,
) -> list[float]:
    """Return kernel credit weights for ordered (utility, ablation delta) inputs."""
    ...

def update_utility(
    current: float,
    credit: float,
    outcome: float,
    eta: float,
    u_min: float,
    u_max: float,
) -> float:
    """Apply the kernel's validated and bounded moving-average update."""
    ...

class Record:
    """A native record; laboratory wire conversions preserve opaque bytes."""

    @staticmethod
    def from_wire(data: bytes) -> Record:
        """Decode a complete laboratory record, refusing missing messages or unknown kinds."""
        ...

    def to_wire(self) -> bytes:
        """Encode every supplied field of the current native laboratory value."""
        ...

    @property
    def id(self) -> str:
        """Unique record identifier (UUID)."""
        ...
    @property
    def timestamp(self) -> int:
        """Creation timestep."""
        ...
    @property
    def episode_id(self) -> str:
        """Episode this record belongs to."""
        ...
    @property
    def payload_type(self) -> str:
        """Type of payload (observation, action, etc.)."""
        ...
    @property
    def cost_bytes(self) -> int:
        """Storage cost in bytes."""
        ...
    @property
    def cost_tokens(self) -> int:
        """Declared token cost."""
        ...
    @property
    def utility(self) -> float:
        """Current utility estimate."""
        ...
    @property
    def last_used(self) -> int:
        """Timestep when last accessed."""
        ...
    @property
    def use_count(self) -> int:
        """Number of times this record was read."""
        ...

class RecordStore:
    @property
    def _record_objects(self) -> dict[str, Any]: ...

    def prepare_object(self, record: MemoryRecord, payload: bytes) -> Record:
        """Validate a fixed admission snapshot before any removal is chosen."""
        ...

    def insert_object(self, record: MemoryRecord, admission: Record) -> None:
        """Keep the live native object separately from its fixed admission costs."""
        ...

    def touch_object(self, id: str, timestamp: int) -> bool:
        """Update live and admission access counts, refusing overflow before either changes."""
        ...
    """High-performance record storage with priority indexing.

    Uses hashbrown HashMap for O(1) lookup and BinaryHeap for O(log n)
    priority-based pruning selection.

    Example:
        >>> store = RecordStore(max_slots=10000)
        >>> store.insert("r1", 0, "ep1", "observation", b'{"x": 1}', 100)
        >>> record = store.get("r1")
        >>> print(record.id)
        r1
    """

    def __init__(self, max_slots: int = 10000) -> None:
        """Create a new record store.

        Args:
            max_slots: Capacity reported to the caller, which enforces admission limits.
        """
        ...

    def insert_record(self, record: Record) -> None:
        """Store a complete byte value; refuse an object-backed ID with ValueError.

        Refusal preserves both views and accounting, as do the admission checks.
        """
        ...

    def fork(self) -> RecordStore:
        """Copy records, priorities and accounting into an independent store."""
        ...

    def insert(
        self,
        id: str,
        timestamp: int,
        episode_id: str,
        payload_type: str,
        payload: bytes,
        cost_bytes: int,
        cost_tokens: int = 0,
    ) -> None:
        """Insert a new record.

        Args:
            id: Unique record identifier.
            timestamp: Creation timestamp (step).
            episode_id: Episode identifier.
            payload_type: Type of payload.
            payload: Payload bytes (JSON encoded).
            cost_bytes: Non-negative byte cost; zero is allowed in the native store.
            cost_tokens: Non-negative declared token count; defaults to zero.

        Raises:
            ValueError: The ID is object-backed, or a byte or token cost is negative.
            OverflowError: The final retained byte or token total exceeds signed 64-bit range.

        Refusal preserves records, priorities and accounting. Replacement deducts
        the old cost before checking the final total.
        """
        ...

    def get(self, id: str) -> Record | None:
        """Get a record by ID.

        Args:
            id: Record identifier.

        Returns:
            The record if found, None otherwise.
        """
        ...

    def update_utility(self, id: str, utility: float) -> bool:
        """Update utility value for a record.

        Args:
            id: Record identifier.
            utility: New utility value.

        Returns:
            True if record was found and updated.
        """
        ...

    def touch(self, id: str, timestamp: int) -> bool:
        """Mark record as accessed.

        Args:
            id: Record identifier.
            timestamp: Access timestamp.

        Returns:
            True if updated, or False if the record is missing.

        Raises:
            OverflowError: The access count is already at its signed 32-bit maximum.
                Neither the timestamp nor count changes on refusal.
        """
        ...

    def remove(self, id: str) -> Record | None:
        """Remove a record.

        Args:
            id: Record identifier.

        Returns:
            The removed record if found, None otherwise.
        """
        ...

    def select_for_pruning(self, target_bytes: int) -> list[str]:
        """Select records for pruning.

        Uses the priority index without removing any records.

        Args:
            target_bytes: Target bytes to free.

        Returns:
            List of record IDs to prune.
        """
        ...

    def ids(self) -> list[str]:
        """Get all record IDs."""
        ...

    @property
    def current_bytes(self) -> int:
        """Current byte usage."""
        ...

    @property
    def current_tokens(self) -> int:
        """Sum of declared token costs."""
        ...

    @property
    def capacity(self) -> int:
        """Maximum slot capacity."""
        ...

    def __len__(self) -> int:
        """Number of records stored."""
        ...

    def __repr__(self) -> str: ...

class EventLogger:
    """High-frequency event ring buffer.

    Provides a fixed-size buffer that overwrites oldest events when full.
    Thread-safe with minimal contention.

    Example:
        >>> logger = EventLogger(capacity=10000)
        >>> logger.set_episode("ep1")
        >>> event_id = logger.log_write(0, "r1", 100)
    """

    def __init__(self, capacity: int = 10000) -> None:
        """Create a new event logger.

        Args:
            capacity: Maximum number of events to buffer.
        """
        ...

    def set_episode(self, episode_id: str) -> None:
        """Set the current episode ID."""
        ...

    def log_write(self, timestamp: int, record_id: str, bytes: int) -> int:
        """Log a write event.

        Args:
            timestamp: Event timestamp.
            record_id: ID of written record.
            bytes: Current byte usage.

        Returns:
            Event ID.
        """
        ...

    def log_read(self, timestamp: int, record_ids: list[str]) -> int:
        """Log a read event.

        Args:
            timestamp: Event timestamp.
            record_ids: IDs of records read.

        Returns:
            Event ID.
        """
        ...

    def log_prune(self, timestamp: int, record_id: str, reason: str) -> int:
        """Log a prune event.

        Args:
            timestamp: Event timestamp.
            record_id: ID of pruned record.
            reason: Reason for pruning.

        Returns:
            Event ID.
        """
        ...

    def log_update_score(
        self,
        timestamp: int,
        record_id: str,
        score_type: str,
        old_value: float,
        new_value: float,
        signal_source: str = "",
    ) -> int:
        """Log a score update event.

        Args:
            timestamp: Event timestamp.
            record_id: ID of updated record.
            score_type: Type of score updated.
            old_value: Previous score value.
            new_value: New score value.
            signal_source: What triggered this update (e.g., "reward", "ablation").

        Returns:
            Event ID.
        """
        ...

    def get_event(self, event_id: int) -> Optional[str]:
        """Return one retained event as JSON without draining the ring."""
        ...

    def drain(self) -> list[dict]:
        """Drain all events from the buffer.

        Returns:
            List of event dicts.
        """
        ...

    def since(self, event_id: int) -> str:
        """Get events since a given event ID as JSON lines.

        Args:
            event_id: Get events after this ID.

        Returns:
            JSONL string of events.
        """
        ...

    def recent(self, n: int) -> str:
        """Get recent events as JSON lines.

        Args:
            n: Number of recent events.

        Returns:
            JSONL string of events.
        """
        ...

    def clear(self) -> None:
        """Clear the buffer."""
        ...

    def to_jsonl(self) -> str:
        """Export all events as JSON lines."""
        ...

    def peek(self) -> str:
        """Peek at all events without draining.

        Returns:
            JSONL string of all events in buffer.
        """
        ...

    @property
    def capacity(self) -> int:
        """Buffer capacity."""
        ...

    @property
    def dropped_count(self) -> int:
        """Number of events dropped due to buffer overflow."""
        ...

    def __len__(self) -> int:
        """Number of events in buffer."""
        ...

    def __repr__(self) -> str: ...

class RetentionPolicy:
    """Retention-policy description; selection uses select_retention.

    Example:
        >>> policy = RetentionPolicy.evidence_per_byte(evidence_weight=0.7)
        >>> print(policy.name)
        EvidencePerByte
    """

    @staticmethod
    def fifo() -> RetentionPolicy:
        """Create a FIFO (first-in-first-out) policy."""
        ...

    @staticmethod
    def lru() -> RetentionPolicy:
        """Create an LRU (least-recently-used) policy."""
        ...

    @staticmethod
    def utility() -> RetentionPolicy:
        """Create a utility-based policy."""
        ...

    @staticmethod
    def evidence_per_byte(evidence_weight: float = 0.5) -> RetentionPolicy:
        """Describe the evidence-per-byte rule.

        Args:
            evidence_weight: Weight for a supplied effect or proxy versus utility (0-1).
        """
        ...

    @staticmethod
    def diversity(min_per_type: int = 1) -> RetentionPolicy:
        """Create a diversity-preserving policy.

        Args:
            min_per_type: Minimum records per payload type to protect.
        """
        ...

    @property
    def name(self) -> str:
        """Policy name."""
        ...

    def __repr__(self) -> str: ...
