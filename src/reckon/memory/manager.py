"""Store observations under byte, slot, token and operation-rate allowances.

Python holds full records and queries; the required Rust store maintains
compact records, priorities and a bounded event ring. Store/cache mutations
use a reentrant lock. Returned records remain mutable references, and callers
coordinate episode contexts and retrieval/observation sequences separately.
Storage locking does not make that complete sequence atomic.

Use retrieve() to track returned IDs for observe(), or read() for a query
without context tracking. Preserve events before draining or resetting the
finite log; a saved operation alone does not preserve the full record payload.
"""

import json
import operator
import threading
import uuid
from copy import deepcopy
from queue import SimpleQueue
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from datetime import datetime
from typing import Any, Optional, List, Dict, Callable, Iterator

from reckon._rust import EventLogger, RecordStore  # pylint: disable=no-name-in-module
from reckon.core.resources import MemoryBudget
from reckon.core.episode_context import EpisodeContext, get_current_context
from reckon.core.credit import (
    DEFAULT_SHAPED_SCALE,
    CreditPolicy,
    CreditAssignment,
    compute_credit,
    update_utility,
)
from reckon.memory.policies import FIFOPolicy, RetentionPolicy
from reckon.memory.record import MemoryRecord, PayloadType, RecordOrigin, RecordCost
from reckon.memory.rate_limits import OperationLimits


def _kernel_integer(value: int, name: str) -> int:
    """Check a signed 64-bit kernel value before a mutation can depend on it."""
    value = operator.index(value)
    if not -(2**63) <= value < 2**63:
        raise OverflowError(f"{name} exceeds the kernel's signed 64-bit range")
    return value


def _kernel_text(value: str, name: str) -> str:
    """Validate text before a later Rust log call can reject it."""
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    value.encode("utf-8")
    return value


class ReckonJSONEncoder(json.JSONEncoder):
    """JSON encoder that handles common Reckon types.

    Handles:
        - datetime: Converted to ISO format string.
        - dataclasses: Converted to dict via asdict().
        - Objects with __dict__: Converted to their __dict__.
        - Objects with tolist(): Converted to list (numpy arrays).
    """

    def default(self, o):
        """Convert a supported payload value to a JSON-encodable representation.

        Try datetime, dataclass, object attributes and tolist() in that order.
        Delegate unsupported values to JSONEncoder, which raises TypeError.
        """
        if isinstance(o, datetime):
            return o.isoformat()
        if is_dataclass(o) and not isinstance(o, type):
            return asdict(o)
        if hasattr(o, "__dict__"):
            return o.__dict__
        if hasattr(o, "tolist"):  # numpy arrays
            return o.tolist()  # type: ignore[attr-defined]
        return super().default(o)


@dataclass
class MemoryEvent:
    """An event in the memory log for debugging."""

    event_type: str  # write, read, prune, update_score
    timestamp: int
    record_id: str
    details: dict = field(default_factory=dict)


# pylint: disable=too-many-instance-attributes
class CausalMemoryManager:
    """The Causal Memory Manager (CMM).

    Enforces memory budgets, manages record lifecycle, and logs
    all decisions for the debugger.

    Uses Rust extensions for performance:
    - RecordStore: O(1) lookup, O(log n) pruning selection
    - EventLogger: High-frequency event ring buffer

    .. code-block:: python

        budget = MemoryBudget(max_slots=100, max_bytes=10000)
        cmm = CausalMemoryManager(budget)

        # Store a record
        record_id = cmm.write(
            payload=observation,
            payload_type=PayloadType.OBSERVATION,
            tags=["cue"],
        )

        # Retrieve records
        hits = cmm.read(query={"tags": ["cue"]})

        # Get event log for debugging
        events = cmm.get_event_log()
    """

    def __init__(
        self,
        budget: MemoryBudget,
        retention_policy: Optional[RetentionPolicy] = None,
        episode_id: str = "",
    ):
        """Initialize the memory manager.

        Args:
            budget: Memory budget constraints
            retention_policy: Policy for selecting records to prune
            episode_id: Current episode identifier
        """
        self.budget = budget
        self.retention_policy = retention_policy or FIFOPolicy()
        self.episode_id = episode_id

        # Thread safety lock (reentrant for nested calls)
        self._lock = threading.RLock()

        # Rust-backed storage (high performance)
        self._store = RecordStore(max_slots=budget.max_slots)
        self._logger = EventLogger(capacity=10000)
        self._logger.set_episode(episode_id)
        self._event_source_id = uuid.uuid4().hex
        self._event_sinks: list[SimpleQueue] = []

        self._current_step: int = 0
        self._episode_start_step: int = 0
        self._read_intervention: Optional[Callable[[list[MemoryRecord]], None]] = None
        self._operation_limits = OperationLimits(budget)
        self._uncounted_tokens: set[str] = set()

    @property
    def _records(self) -> dict[str, MemoryRecord]:
        """Live native objects, independent of their fixed admission costs."""
        return self._store._record_objects

    @contextmanager
    def subscribe_events(self) -> Iterator[SimpleQueue]:
        """Receive source identity and each actual kernel event without draining it.

        Existing retained events are included atomically with subscription. An
        earlier ring overflow is refused. The subscriber must consume its queue;
        these diagnostic copies are separate from the task's memory budget.
        """
        queue: SimpleQueue = SimpleQueue()
        with self._lock:
            if self._logger.dropped_count:
                raise RuntimeError("Cannot stream a complete run after the event ring overflowed")
            for line in self._logger.to_jsonl().splitlines():
                queue.put((self._event_source_id, json.loads(line)))
            self._event_sinks.append(queue)
        try:
            yield queue
        finally:
            with self._lock:
                self._event_sinks.remove(queue)

    def _log_event(self, method: str, *args) -> int:
        """Copy the exact newly logged event to active diagnostic subscriptions."""
        event_id = getattr(self._logger, method)(*args)
        if self._event_sinks:
            serialized = self._logger.get_event(event_id)
            if serialized is None:
                raise RuntimeError("The newly logged event is unavailable")
            for queue in self._event_sinks:
                queue.put((self._event_source_id, json.loads(serialized)))
        return event_id

    @contextmanager
    def before_read(self, intervention: Callable[[list[MemoryRecord]], None]) -> Iterator[None]:
        """Install a trial intervention at each read's candidate boundary.

        The callback sees the records the query would return, before access or
        credit is recorded. It may prune records; the query is then resolved
        again. The scope holds this manager's lock, survives episode resets,
        and removes the callback even if the task raises. Callbacks must not
        initiate another read, and nested intervention scopes are refused.
        """
        with self._lock:
            if self._read_intervention is not None:
                raise RuntimeError("A read intervention is already installed")
            self._read_intervention = intervention
            try:
                yield
            finally:
                self._read_intervention = None

    @property
    def current_usage_bytes(self) -> int:
        """Current memory usage in bytes."""
        with self._lock:
            return self._store.current_bytes

    def fork_for_trial(self, retention_policy: RetentionPolicy) -> "CausalMemoryManager":
        """Copy stored memory and its timeline for an independent trial.

        The caller supplies a fresh trial policy. Records, costs, utilities and
        native priorities are copied under the manager lock. The trial starts
        with fresh operation windows and an empty event log; callbacks,
        subscriptions and the caller's episode context are not copied. This is
        a new experiment from retained memory, not replay of an active task.
        """
        # Both instances belong to this class; include the complete native state.
        # pylint: disable=protected-access
        with self._lock:
            trial = CausalMemoryManager(deepcopy(self.budget), retention_policy)
            trial._store = self._store.fork()
            trial._uncounted_tokens = self._uncounted_tokens.copy()
            trial._current_step = self._current_step
            trial._episode_start_step = self._episode_start_step
            trial.episode_id = self.episode_id
            trial._logger.set_episode(self.episode_id)
            return trial

    @property
    def current_usage_slots(self) -> int:
        """Current number of records stored."""
        with self._lock:
            return len(self._store)

    @property
    def current_usage_tokens(self) -> Optional[int]:
        """Declared tokens, or unavailable while any retained count is missing."""
        with self._lock:
            return None if self._uncounted_tokens else self._store.current_tokens

    def set_step(self, step: int) -> None:
        """Set an integer episode-relative step, preserving the old step on overflow."""
        with self._lock:
            next_step = _kernel_integer(self._episode_start_step + operator.index(step), "Step")
            self._operation_limits.check_step(self._current_step, next_step)
            self._current_step = next_step

    def set_episode(self, episode_id: str, *, reset_memory: bool = True) -> None:
        """Begin an episode, optionally keeping records, scores and events.

        With reset_memory=False, episode-relative steps advance beyond the
        previous episode so FIFO and LRU can order retained records correctly.
        """
        with self._lock:
            _kernel_text(episode_id, "Episode ID")
            next_step = 0 if reset_memory else _kernel_integer(self._current_step + 1, "Step")
            self._operation_limits.check_step(self._current_step, next_step, reset=reset_memory)
            limits = OperationLimits(self.budget) if reset_memory else self._operation_limits
            self.episode_id = episode_id
            if reset_memory:
                self._store = RecordStore(max_slots=self.budget.max_slots)
                self._logger = EventLogger(capacity=10000)
                self._event_source_id = uuid.uuid4().hex
                self._records.clear()
                self._uncounted_tokens.clear()
                self._operation_limits = limits
            self._episode_start_step = next_step
            self._current_step = next_step
            self._logger.set_episode(episode_id)

    # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    def write(
        self,
        payload: Any,
        payload_type: PayloadType,
        tags: Optional[list[str]] = None,
        cost_bytes: Optional[int] = None,
        source_op: str = "",
        input_ids: Optional[list[str]] = None,
        initial_utility: float = 0.0,
        metadata: Optional[dict] = None,
        *,
        cost_tokens: Optional[int] = None,
    ) -> str:
        """Store a new record.

        Args:
            payload: The data to store
            payload_type: Type of payload
            tags: Categorical tags
            cost_bytes: Integer byte count, floored at one; estimated when omitted
            source_op: Operation that created this record
            input_ids: IDs of records this depends on
            initial_utility: Initial utility estimate
            metadata: Additional metadata
            cost_tokens: Caller-counted tokens; required when a token limit is set.

        Returns:
            The ID of the stored record

        Raises:
            TypeError: The supplied byte count is not an integer.
            OverflowError: A cost or retained total exceeds the kernel's signed 64-bit range.
        """
        with self._lock, self._operation_limits.consume("write", self._current_step, self.budget):
            self.budget.__post_init__()
            if cost_tokens is not None:
                # Boolean values are not token counts.
                # pylint: disable=unidiomatic-typecheck
                if type(cost_tokens) is not int or cost_tokens < 0:
                    raise ValueError("Record token cost must be a non-negative integer")
                _kernel_integer(cost_tokens, "Record token cost")
            if self.budget.max_tokens is not None:
                if cost_tokens is None or self._uncounted_tokens:
                    raise ValueError(
                        "A token budget requires counts for every retained and new record"
                    )
                if cost_tokens > self.budget.max_tokens:
                    raise ValueError(
                        "Record exceeds the token budget; existing records are unchanged"
                    )
            # Generate ID (full UUID to prevent collisions at scale)
            record_id = str(uuid.uuid4())

            # Serialize payload using custom encoder for complex types
            payload_bytes = json.dumps(payload, cls=ReckonJSONEncoder).encode("utf-8")

            # Estimate cost if not provided (minimum 1 byte)
            cost_bytes = (
                max(1, len(payload_bytes))
                if cost_bytes is None
                else max(1, operator.index(cost_bytes))
            )
            cost_bytes = _kernel_integer(cost_bytes, "Record byte cost")

            if self.budget.max_bytes is not None and cost_bytes > self.budget.max_bytes:
                raise ValueError("Record exceeds the byte budget; existing records are unchanged")

            # Create Python record with full metadata
            record = MemoryRecord(
                id=record_id,
                timestamp=self._current_step,
                payload_type=payload_type,
                payload=payload,
                cost=RecordCost(bytes=cost_bytes, tokens=cost_tokens, slots=1),
                tags=tags or [],
                provenance=RecordOrigin(
                    source_op=source_op,
                    input_ids=input_ids or [],
                ),
                episode_id=self.episode_id,
                metadata=metadata or {},
            )
            record.utility.value = initial_utility
            # Validate all native fields before a policy can remove existing records.
            admission = self._store.prepare_object(record, payload_bytes)

            # Atomic budget enforcement: calculate total overflow ONCE
            new_bytes = self._store.current_bytes + cost_bytes
            new_slots = len(self._store) + 1
            new_tokens = self._store.current_tokens + (cost_tokens or 0)
            overflow_tokens = (
                max(0, new_tokens - self.budget.max_tokens)
                if self.budget.max_tokens is not None
                else 0
            )

            overflow_bytes = 0
            overflow_slots = 0

            if self.budget.max_bytes and new_bytes > self.budget.max_bytes:
                overflow_bytes = new_bytes - self.budget.max_bytes

            if self.budget.max_slots and new_slots > self.budget.max_slots:
                overflow_slots = new_slots - self.budget.max_slots

            # Single pruning pass for combined overflow
            if overflow_bytes > 0 or overflow_slots > 0 or overflow_tokens > 0:
                self._enforce_budget_combined(
                    overflow_bytes, overflow_slots, new_bytes, overflow_tokens, new_tokens
                )
            else:
                _kernel_integer(new_bytes, "Stored byte total")
                _kernel_integer(new_tokens, "Stored token total")

            # Native storage retains the live object and its admitted cost snapshot.
            self._store.insert_object(record, admission)
            if cost_tokens is None:
                self._uncounted_tokens.add(record_id)

            # Log event (Rust logger)
            self._log_event("log_write", self._current_step, record_id, self._store.current_bytes)

            return record_id

    def read(
        self,
        query: Optional[dict] = None,
        record_ids: Optional[list[str]] = None,
        limit: int = 10,
    ) -> list[MemoryRecord]:
        """Retrieve records matching query.

        Args:
            query: Query dict with optional keys: tags, payload_type, min_utility
            record_ids: Specific record IDs to retrieve
            limit: Maximum number of records to return

        Returns:
            List of matching records
        """
        with self._lock, self._operation_limits.consume("read", self._current_step, self.budget):
            if record_ids:
                hits = [self._records[rid] for rid in record_ids if rid in self._records]
            else:
                hits = self._query_records(query or {})

            hits = hits[:limit]

            if self._read_intervention is not None:
                self._read_intervention(hits.copy())
                # Pruning can expose the next ranked candidate in a limited query.
                hits = (
                    [self._records[rid] for rid in record_ids if rid in self._records]
                    if record_ids
                    else self._query_records(query or {})
                )[:limit]

            # Refuse count overflow before either access view changes.
            for record in hits:
                self._store.touch_object(record.id, self._current_step)

            # Log event (Rust logger)
            hit_ids = [r.id for r in hits]
            self._log_event("log_read", self._current_step, hit_ids)

            return hits

    def prune(self, record_id: str, reason: str = "manual") -> bool:
        """Explicitly remove a record.

        Args:
            record_id: ID of record to remove
            reason: Reason for pruning

        Returns:
            True if record was found and removed
        """
        with self._lock:
            if record_id not in self._records:
                return False

            _kernel_text(reason, "Pruning reason")
            # Remove from Rust store
            self._store.remove(record_id)

            self._uncounted_tokens.discard(record_id)

            # Log event (Rust logger)
            self._log_event("log_prune", self._current_step, record_id, reason)

            return True

    def update_score(
        self,
        record_id: str,
        score_type: str,
        value: float,
        signal_source: str = "",
    ) -> bool:
        """Update causal or utility score for a record.

        Args:
            record_id: ID of record to update
            score_type: One of 'utility', 'ablation_delta', 'counterfactual_delta',
                'influence_proxy'
            value: New score value
            signal_source: What triggered the update

        Returns:
            True if record was found and updated
        """
        with self._lock:
            if record_id not in self._records:
                return False

            record = self._records[record_id]
            old_value: Optional[float] = None

            if score_type == "utility":
                old_value = record.utility.value
                record.utility.value = value
                # Update Rust store utility for priority index
                self._store.update_utility(record_id, value)
            elif score_type == "ablation_delta":
                old_value = record.causal_score.ablation_delta
                record.causal_score.ablation_delta = value
                record.causal_score.last_evaluated = self._current_step
            elif score_type == "counterfactual_delta":
                old_value = record.causal_score.counterfactual_delta
                record.causal_score.counterfactual_delta = value
                record.causal_score.last_evaluated = self._current_step
            elif score_type == "influence_proxy":
                old_value = record.causal_score.influence_proxy
                record.causal_score.influence_proxy = value
                record.causal_score.last_evaluated = self._current_step
            else:
                return False

            # Log event (Rust logger)
            self._log_event(
                "log_update_score",
                self._current_step,
                record_id,
                score_type,
                old_value if old_value is not None else 0.0,
                value,
                signal_source,
            )

            return True

    def get_record(self, record_id: str) -> Optional[MemoryRecord]:
        """Get a specific record by ID."""
        with self._lock:
            return self._records.get(record_id)

    def get_all_records(self) -> list[MemoryRecord]:
        """Get all records currently in memory."""
        with self._lock:
            return list(self._records.values())

    def get_event_log(self) -> list[dict]:
        """Get the full event log for debugging.

        Returns:
            List of event dicts from the Rust EventLogger.
        """
        with self._lock:
            return self._logger.drain()

    def get_event_log_jsonl(self) -> str:
        """Get event log as JSON lines (for streaming to debugger).

        Returns:
            JSONL string of all events.
        """
        with self._lock:
            return self._logger.to_jsonl()

    def _query_records(self, query: dict) -> list[MemoryRecord]:
        """Execute a query against stored records."""
        results = list(self._records.values())

        if "tags" in query:
            query_tags = set(query["tags"])
            results = [r for r in results if query_tags & set(r.tags)]

        if "payload_type" in query:
            pt = query["payload_type"]
            if isinstance(pt, str):
                pt = PayloadType(pt)
            results = [r for r in results if r.payload_type == pt]

        if "min_utility" in query:
            min_u = query["min_utility"]
            results = [r for r in results if r.utility.value >= min_u]

        # Sort by utility (highest first)
        results.sort(key=lambda r: r.utility.value, reverse=True)

        return results

    def _enforce_budget_combined(
        self,
        overflow_bytes: int,
        overflow_slots: int,
        pending_bytes: int,
        overflow_tokens: int,
        pending_tokens: int,
    ) -> None:
        """Validate the selected removals against all three storage dimensions.

        Args:
            overflow_bytes: Bytes that need to be freed (0 if no overflow).
            overflow_slots: Slots that need to be freed (0 if no overflow).
            pending_bytes: Total bytes including the incoming record, before pruning.
            overflow_tokens: Tokens that need to be freed.
            pending_tokens: Declared tokens including the incoming record.
        """
        if overflow_bytes <= 0 and overflow_slots <= 0 and overflow_tokens <= 0:
            return

        # Cost metadata returned to callers is mutable; admission uses the
        # original native costs, independent of edits to those Python objects.
        records = []
        costs = {}
        for record in self._records.values():
            stored = self._store.get(record.id)
            if stored is None:
                raise RuntimeError("Stored record is unavailable for budget selection")
            costs[record.id] = (stored.cost_bytes, stored.cost_tokens)
            records.append(
                replace(
                    record,
                    cost=RecordCost(bytes=stored.cost_bytes, tokens=stored.cost_tokens, slots=1),
                )
            )

        to_prune = self.retention_policy.select_for_pruning(
            records, overflow_bytes, overflow_slots, overflow_tokens
        )
        if len(set(to_prune)) != len(to_prune) or any(
            record_id not in self._records for record_id in to_prune
        ):
            raise ValueError("Retention policy must select distinct existing records")
        freed_bytes = sum(costs[record_id][0] for record_id in to_prune)
        freed_tokens = sum(costs[record_id][1] for record_id in to_prune)
        if (
            freed_bytes < overflow_bytes
            or len(to_prune) < overflow_slots
            or freed_tokens < overflow_tokens
        ):
            raise ValueError(
                "Retention policy did not free the required bytes and slots and tokens"
            )
        _kernel_integer(pending_bytes - freed_bytes, "Stored byte total")
        _kernel_integer(pending_tokens - freed_tokens, "Stored token total")

        reason = _kernel_text(self.retention_policy.reason(), "Retention policy reason")
        for record_id in to_prune:
            # Use internal prune logic without re-acquiring lock
            if record_id in self._records:
                self._store.remove(record_id)
                self._uncounted_tokens.discard(record_id)
                self._log_event("log_prune", self._current_step, record_id, reason)

    # =========================================================================
    # v1.0 API: retrieve() and observe()
    # =========================================================================

    def retrieve(
        self,
        query: Optional[dict] = None,
        record_ids: Optional[List[str]] = None,
        limit: int = 10,
        context: Optional[EpisodeContext] = None,
    ) -> List[MemoryRecord]:
        """Retrieve records and track them for credit assignment.

        This is the v1.0 API method that replaces read(). It tracks retrieved
        records in the EpisodeContext for later credit assignment via observe().

        Args:
            query: Query dict with optional keys: tags, payload_type, min_utility
            record_ids: Specific record IDs to retrieve
            limit: Maximum number of records to return
            context: EpisodeContext for tracking (uses implicit context if None)

        Returns:
            List of matching records

        .. code-block:: python

            with EpisodeContext(episode_id="ep_001") as ctx:
                records = manager.retrieve(query={"tags": ["cue"]})
                # ... agent uses records ...
                credits = manager.observe(outcome=1.0)
        """
        # Use provided context, or get from ContextVar
        ctx = context or get_current_context()

        # Perform the read
        hits = self.read(query=query, record_ids=record_ids, limit=limit)

        # Track retrieved record IDs in context
        if ctx is not None:
            ctx.add_retrieved_records([r.id for r in hits])

        return hits

    def observe(
        self,
        outcome: float,
        policy: CreditPolicy = CreditPolicy.SIMPLE,
        context: Optional[EpisodeContext] = None,
    ) -> List[CreditAssignment]:
        """Observe an outcome and assign credit to retrieved records.

        Distributes credit to records that were retrieved in the current
        context, then updates their utility scores.

        Args:
            outcome: Outcome value (e.g., reward, success indicator)
            policy: Credit assignment policy
            context: EpisodeContext to use (uses implicit context if None)

        Returns:
            List of CreditAssignment objects showing credit distribution

        .. code-block:: python

            with EpisodeContext(episode_id="ep_001") as ctx:
                records = manager.retrieve(query={"tags": ["cue"]})
                # ... agent uses records and gets reward ...
                assignments = manager.observe(outcome=1.0, policy=CreditPolicy.SIMPLE)
        """
        with self._lock:
            # Use provided context, or get from ContextVar
            ctx = context or get_current_context()

            # Degenerate mode: no context or no retrieved records
            if ctx is None or not ctx.retrieved_record_ids:
                return []

            # Refuse attribution through an expired context.
            if ctx.is_expired():
                return []

            # Get utilities for SHAPED policy
            utilities: Dict[str, float] = {}
            ablation_deltas: Dict[str, float] = {}
            for rid in ctx.retrieved_record_ids:
                record = self._records.get(rid)
                if record:
                    utilities[rid] = record.utility.value
                    if record.causal_score.ablation_delta is not None:
                        ablation_deltas[rid] = record.causal_score.ablation_delta

            # Compute credit assignments
            assignments = compute_credit(
                record_ids=ctx.retrieved_record_ids,
                outcome=outcome,
                policy=policy,
                utilities=utilities,
                ablation_deltas=ablation_deltas,
                shaped_scale=DEFAULT_SHAPED_SCALE,
            )

            signal_source = f"observe:{policy.value}"
            if policy == CreditPolicy.SHAPED:
                signal_source = f"{signal_source}:softplus:scale={DEFAULT_SHAPED_SCALE}"

            # Validate every update before changing either store.
            updates = []
            for ca in assignments:
                record = self._records.get(ca.record_id)
                if record:
                    old_utility = record.utility.value
                    new_utility = update_utility(
                        current_utility=old_utility,
                        credit=ca.credit,
                        outcome=outcome,
                    )
                    updates.append((record, old_utility, new_utility))
            for record, old_utility, new_utility in updates:
                record.utility.value = new_utility
                self._store.update_utility(record.id, new_utility)
                self._log_event(
                    "log_update_score",
                    self._current_step,
                    record.id,
                    "utility",
                    old_utility,
                    new_utility,
                    signal_source,
                )

            return assignments

    def get_utilities(self) -> Dict[str, float]:
        """Get current utility values for all records.

        Returns:
            Dict mapping record_id to utility value
        """
        with self._lock:
            return {rid: record.utility.value for rid, record in self._records.items()}
